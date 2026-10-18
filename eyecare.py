"""Нагадування 20-20-20 (кожні N хвилин роботи за екраном — подивитися вдалину)
і про перерву після кількох годин безперервної роботи.

Не показуються в повноекранному режимі / презентації / «Не турбувати» і поки
мікрофон чи камера зайняті (дзвінок) — тоді відкладається до їх завершення.
Якщо користувач відійшов від комп'ютера (або той спав), відлік починається заново.
"""
import ctypes
import time
import winreg

import winapi as w

TICK_MS = 60_000                 # як часто перевіряти
_IDLE_RESET = 5 * 60             # стільки без введення = перерва вже була
_WATCH_AFTER = _IDLE_RESET - 2 * TICK_MS // 1000  # з такої бездіяльності чекати на повернення
WORK_REPEAT = 30 * 60            # якщо перерви так і не було — нагадати знову через стільки
_QUNS_ACCEPTS_NOTIFICATIONS = 5
_QUNS_FULLSCREEN = (2, 3, 4)     # BUSY, RUNNING_D3D_FULL_SCREEN, PRESENTATION_MODE
_CONSENT = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"


def _input_ticks():
    """(GetTickCount зараз, GetTickCount останнього введення), мс; None — якщо невідомо."""
    lii = w.LASTINPUTINFO(cbSize=ctypes.sizeof(w.LASTINPUTINFO))
    if not w.GetLastInputInfo(ctypes.byref(lii)):
        return None
    return w.GetTickCount(), lii.dwTime


def _elapsed_ms(now, then):
    return (now - then) & 0xFFFFFFFF  # GetTickCount переповнюється раз на ~49 днів


def idle_seconds():
    ticks = _input_ticks()
    return _elapsed_ms(*ticks) / 1000.0 if ticks else 0.0


def notifications_blocked():
    """Повноекранна програма, презентація, «Не турбувати», заблокований екран тощо."""
    state = ctypes.c_int()
    if w.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
        return False
    return state.value != _QUNS_ACCEPTS_NOTIFICATIONS


def fullscreen_app():
    """Повноекранна програма (гра, відео), Direct3D на весь екран або презентація."""
    state = ctypes.c_int()
    if w.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
        return False
    return state.value in _QUNS_FULLSCREEN


def _key_in_use(key, depth):
    try:
        start = winreg.QueryValueEx(key, "LastUsedTimeStart")[0]
        stop = winreg.QueryValueEx(key, "LastUsedTimeStop")[0]
        if start and not stop:
            return True
    except OSError:
        pass
    if depth:
        i = 0
        while True:
            try:
                name = winreg.EnumKey(key, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(key, name) as sub:
                    if _key_in_use(sub, depth - 1):
                        return True
            except OSError:
                pass
    return False


def call_in_progress():
    """Мікрофон або камера зараз використовуються якоюсь програмою.

    Windows записує LastUsedTimeStart/Stop для кожної програми (для звичайних exe —
    у підрозділі NonPackaged); Stop = 0 означає, що пристрій досі зайнятий.
    """
    for device in ("microphone", "webcam"):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CONSENT + "\\" + device) as k:
                if _key_in_use(k, 2):
                    return True
        except OSError:
            pass
    return False


class BreakDetector:
    """Чи була перерва: _IDLE_RESET без введення або сон.

    GetLastInputInfo пам'ятає лише останнє введення: коли користувач повернувся,
    тривалість паузи перед цим уже не дізнатися, а будь-яка перевірка за таймером
    може запізнитися. Тому, коли бездіяльність перевищує _WATCH_AFTER, програма
    підписується на Raw Input клавіатури й миші (watch()); перше ж введення приходить
    як повідомлення з часом, коли воно сталося (GetMessageTime), — returned(час)
    порівнює його з часом останнього введення перед паузою. Поки користувача немає,
    подій немає, тож це нічого не коштує.
    """

    def __init__(self):
        self.last_check = time.monotonic()
        self.watching = None  # GetTickCount останнього введення перед паузою, поки чекаємо на повернення

    def observe(self):
        """Викликати щохвилини. True — перерва вже є: сон або _IDLE_RESET без введення зараз."""
        now = time.monotonic()
        slept = now - self.last_check > 3 * TICK_MS / 1000
        self.last_check = now
        return slept or idle_seconds() >= _IDLE_RESET

    @staticmethod
    def should_watch():
        return idle_seconds() >= _WATCH_AFTER

    def watch(self):
        ticks = _input_ticks()
        self.watching = ticks[1] if ticks else None
        return self.watching is not None

    def stale(self):
        """Після watch() було введення, яке не прийшло як повідомлення (підписка
        запізнилася або це сенсорний екран / перо). None — ні, інакше його час."""
        ticks = _input_ticks()
        if ticks and ticks[1] != self.watching:
            return ticks[1]
        return None

    def returned(self, input_tick):
        """Перше введення після паузи (input_tick — його GetTickCount). True — пауза
        тривала щонайменше _IDLE_RESET."""
        gap = _elapsed_ms(input_tick & 0xFFFFFFFF, self.watching)
        self.watching = None
        return _IDLE_RESET * 1000 <= gap < 0x80000000  # «від'ємна» різниця — не пауза

    def stop(self):
        self.watching = None


class _Tracker:
    def __init__(self):
        self.reset()

    def reset(self):
        self.since = time.monotonic()


class EyeBreaks(_Tracker):
    def tick(self, interval_minutes):
        """Викликати щохвилини (після перерви — reset()). True — час показати нагадування."""
        now = time.monotonic()
        if now - self.since < interval_minutes * 60:
            return False
        if notifications_blocked() or call_in_progress():
            return False  # відкладаємо до наступної перевірки
        self.since = now
        return True


class WorkBreaks(_Tracker):
    """Безперервна робота: відлік від останньої перерви (_IDLE_RESET без введення або сон)."""

    def reset(self):
        super().reset()
        self.reminded = None  # скільки секунд роботи було на момент останнього нагадування

    def tick(self, interval_minutes):
        """Викликати щохвилини (після перерви — reset()). Повертає тривалість роботи
        в секундах, якщо час нагадати, інакше None."""
        now = time.monotonic()
        worked = now - self.since
        due = interval_minutes * 60 if self.reminded is None else self.reminded + WORK_REPEAT
        if worked < due:
            return None
        if notifications_blocked() or call_in_progress():
            return None  # відкладаємо до наступної перевірки
        self.reminded = worked
        return worked


def _plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def format_duration(seconds):
    """Тривалість у знахідному відмінку: «2 години», «1 годину 30 хвилин», «45 хвилин»."""
    minutes = int(seconds // 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append("%d %s" % (hours, _plural(hours, "годину", "години", "годин")))
    if minutes or not hours:
        parts.append("%d %s" % (minutes, _plural(minutes, "хвилину", "хвилини", "хвилин")))
    return " ".join(parts)
