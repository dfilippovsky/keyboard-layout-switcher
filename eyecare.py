"""Нагадування 20-20-20: кожні N хвилин роботи за екраном — подивитися вдалину.

Не показується в повноекранному режимі / презентації / «Не турбувати» і поки
мікрофон чи камера зайняті (дзвінок) — тоді відкладається до їх завершення.
Якщо користувач відійшов від комп'ютера (або той спав), відлік починається заново.
"""
import ctypes
import time
import winreg

import winapi as w

TICK_MS = 60_000                 # як часто перевіряти
_IDLE_RESET = 5 * 60             # стільки без введення = перерва вже була
_QUNS_ACCEPTS_NOTIFICATIONS = 5
_QUNS_FULLSCREEN = (2, 3, 4)     # BUSY, RUNNING_D3D_FULL_SCREEN, PRESENTATION_MODE
_CONSENT = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"


def idle_seconds():
    lii = w.LASTINPUTINFO(cbSize=ctypes.sizeof(w.LASTINPUTINFO))
    if not w.GetLastInputInfo(ctypes.byref(lii)):
        return 0.0
    return ((w.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) / 1000.0


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


class EyeBreaks:
    def __init__(self):
        self.reset()

    def reset(self):
        self.since = self.last_tick = time.monotonic()

    def tick(self, interval_minutes):
        """Викликати щохвилини. True — час показати нагадування."""
        now = time.monotonic()
        slept = now - self.last_tick > 3 * TICK_MS / 1000
        self.last_tick = now
        if slept or idle_seconds() >= _IDLE_RESET:
            self.since = now
            return False
        if now - self.since < interval_minutes * 60:
            return False
        if notifications_blocked() or call_in_progress():
            return False  # відкладаємо до наступної перевірки
        self.since = now
        return True
