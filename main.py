"""Keyboard Layout Switcher — програма в треї, що конвертує текст,
набраний не в тій розкладці, і перемикає розкладку на наступну.
Також: зміна регістру, транслітерація і нагадування 20-20-20 для очей."""
import ctypes
import dataclasses
import logging
import os
import re
import sys
import time

import actions
import autocorrect
import config
import eyecare
import i18n
from i18n import tr
import hotkey as hk
import icon
import keyboard_io as kio
import layouts
import stats
import textcase
import translit
import winapi as w
from clipboard import Clipboard

log = logging.getLogger("kls")

# Дії. Номер дії — це й id її гарячої клавіші: вбудовані 1–3, плагіни з _PLUGIN_BASE.
HOTKEY_LAYOUT, HOTKEY_CASE, HOTKEY_TRANSLIT = 1, 2, 3
# номер -> (ключ, поле config з гарячою клавішею, ключ назви в i18n, колір у треї)
_BUILTIN = {
    HOTKEY_LAYOUT: ("layout", "hotkey", "action.layout", icon.FLASH_COLOR),
    HOTKEY_CASE: ("case", "case_hotkey", "action.case", icon.CASE_FLASH_COLOR),
    HOTKEY_TRANSLIT: ("translit", "translit_hotkey", "action.translit", icon.TRANSLIT_FLASH_COLOR),
}
_BUILTIN_FIELDS = {key: field for key, field, _, _ in _BUILTIN.values()}
_PLUGIN_BASE = 100
_HOTKEY_ALIAS = 0x1000   # id + 0x1000 — додатковий код тієї ж комбінації (Ctrl+Pause = VK_CANCEL)
FLASH_TIMER_ID = 1
EYE_TIMER_ID = 2
EYE_HIDE_TIMER_ID = 3
RECONVERT_TIMER_ID = 4
_SWALLOW_ID = 0x3000   # тимчасові «голі» клавіші під час утримання модифікатора
_FOCUS_TIMEOUT = 1.0   # с — чекати, поки вікно знову стане активним після меню
_HOLD_TIMEOUT = 10.0   # с без натискань — завершити утримання
_FLASH_MS = 350          # скільки іконка в треї світиться кольором дії після обробки гарячої клавіші
WM_TRAY = w.WM_APP + 1
(ID_ENABLED, ID_SETTINGS, ID_OPEN_INI, ID_RELOAD, ID_EXIT, ID_EYES, ID_AUTOCORRECT, ID_PLUGINS,
 ID_WORK, ID_FORCED, ID_STATS) = range(100, 111)
ID_ACTION_BASE = 1000    # пункт меню «Дії» = ID_ACTION_BASE + номер дії
# Вікна, які не є «робочими»: панель задач, область сповіщень, робочий стіл
_SHELL_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow",
                  "TopLevelWindowForOverflowXamlIsland", "Progman", "WorkerW"}
EXCEPTIONS_PATH = os.path.join(config.app_dir(), "autocorrect_exceptions.txt")
FORCED_PATH = os.path.join(config.app_dir(), "autocorrect_words.txt")
_RAW_KEYBOARD, _RAW_MOUSE = 0x06, 0x02   # Generic Desktop: клавіатура, миша
_WS = re.compile(r"\s")
_MAX_WORD_STEPS = 8      # скільки разів Ctrl+Shift+Left шукати початок слова
_MAX_RESELECT = 5000     # не виділяти назад надто довгий текст
_PASTE_THRESHOLD = 300   # довший або багаторядковий текст вставляємо через буфер
_PASTE_SETTLE = 0.3      # дати програмі прочитати буфер перед відновленням
_RECONVERT_MS = 10_000   # повторна конвертація щойно перетвореного тексту (по колу) не рахується


def _looks_like_line_copy(text):
    """Так виглядає Ctrl+C без виділення у VS Code, JetBrains тощо: увесь рядок + \\n."""
    return text.endswith("\n") and text.count("\n") == 1


def _abort(reason):
    """Перервати конвертацію, нічого не змінюючи в тексті."""
    log.warning("conversion aborted: %s", reason)
    w.MessageBeep(0)


class App:
    def __init__(self):
        self.cfg = config.Config.load()
        i18n.set_language(self.cfg.language)
        self.busy = False
        self.hotkey_ok = False
        self.registered = {}     # дія -> (mods, vk) — лише комбінації, що справді зареєстровані
        self.settings_root = None
        self.exit_pending = False
        self.hicon = None
        self.flash_icons = {}    # колір -> іконка
        self.flashing = None     # колір, яким зараз світиться іконка
        self.actions = {}        # номер -> actions.Action
        self.case_cycler = textcase.CaseCycler()
        self.translit = translit.Transliterator(lambda: autocorrect.model("uk"))
        self.away = eyecare.BreakDetector()
        self.eyes = eyecare.EyeBreaks()
        self.eye_icon = None
        self.work = eyecare.WorkBreaks()
        self.work_icon = None
        self.tracker = autocorrect.Tracker()
        self.ac_exceptions = autocorrect.load_words(EXCEPTIONS_PATH)
        self.forced_words = autocorrect.ForcedWords(FORCED_PATH)
        self.stats = stats.Stats()
        self._last_conv = None  # (вікно, результат) останньої конвертації — див. _count_conversion
        self.raw = {_RAW_KEYBOARD: False, _RAW_MOUSE: False}  # що зараз зареєстровано в Raw Input
        self.ac_tracking = False  # автовиправлення стежить за клавіатурою (Raw Input — ще й для перерв)
        self._raw_buf = (ctypes.c_byte * 64)()  # з запасом: RAWINPUT більший за заголовок + дані
        self._draining = False

        self.msg_taskbar_created = w.RegisterWindowMessageW("TaskbarCreated")
        self._wndproc = w.WNDPROC(self._wnd_proc)  # тримаємо посилання від GC
        hinst = w.GetModuleHandleW(None)
        wc = w.WNDCLASSEXW(cbSize=ctypes.sizeof(w.WNDCLASSEXW), lpfnWndProc=self._wndproc,
                           hInstance=hinst, lpszClassName="KeyboardLayoutSwitcherWnd")
        w.RegisterClassExW(ctypes.byref(wc))
        self.hwnd = w.CreateWindowExW(0, wc.lpszClassName, config.APP_NAME, 0, 0, 0, 0, 0,
                                      None, None, hinst, None)
        self.clip = Clipboard(self.hwnd)

        failed_plugins = self._load_actions()
        self._update_icon()
        self._tray(w.NIM_ADD)
        self._warn_failed(self._register_hotkeys(), failed_plugins)
        # Останнє активне вікно — для дій з меню трею (WinEvent, без хуків клавіатури)
        self.last_window = None
        self._remember_window(w.GetForegroundWindow())
        self._win_event = w.WINEVENTPROC(self._on_foreground)  # тримаємо посилання від GC
        self._win_event_hook = w.SetWinEventHook(w.EVENT_SYSTEM_FOREGROUND, w.EVENT_SYSTEM_FOREGROUND,
                                                 None, self._win_event, 0, 0, w.WINEVENT_OUTOFCONTEXT)
        self._update_raw_input()
        w.SetTimer(self.hwnd, EYE_TIMER_ID, eyecare.TICK_MS, None)

    # ---------- трей ----------

    def _tooltip(self):
        tip = "Keyboard Layout Switcher — " + self.cfg.hotkey
        if not self.cfg.enabled:
            tip += tr("tray.disabled")
        elif not self.hotkey_ok:
            tip += tr("tray.busy")
        return tip[:127]

    def _tray(self, action, info=None, warning=False, title=None, quiet=False, balloon_icon=None):
        nid = w.NOTIFYICONDATAW(cbSize=ctypes.sizeof(w.NOTIFYICONDATAW), hWnd=self.hwnd, uID=1)
        if action != w.NIM_DELETE:
            nid.uFlags = w.NIF_MESSAGE | w.NIF_ICON | w.NIF_TIP
            nid.uCallbackMessage = WM_TRAY
            nid.hIcon = self.flash_icons.get(self.flashing) or self.hicon
            nid.szTip = self._tooltip()
            if info is not None:  # "" — прибрати показане сповіщення
                nid.uFlags |= w.NIF_INFO
                nid.szInfo = info[:255]
                nid.szInfoTitle = (title or "Keyboard Layout Switcher")[:63]
                nid.dwInfoFlags = w.NIIF_WARNING if warning else w.NIIF_INFO
                if balloon_icon:
                    nid.dwInfoFlags = w.NIIF_USER | w.NIIF_LARGE_ICON
                    nid.hBalloonIcon = balloon_icon
                if quiet:
                    nid.dwInfoFlags |= w.NIIF_NOSOUND | w.NIIF_RESPECT_QUIET_TIME
        w.Shell_NotifyIconW(action, ctypes.byref(nid))

    def _update_icon(self):
        old = (self.hicon, *self.flash_icons.values())
        size = w.GetSystemMetrics(w.SM_CXSMICON) or 16
        self.hicon = icon.create_hicon(size, icon.tray_color(self.cfg.enabled))
        self.flash_icons = {c: icon.create_hicon(size, c) for c in {a.color for a in self.actions.values()}}
        if old[0]:
            self._tray(w.NIM_MODIFY)
            for h in old:
                w.DestroyIcon(h)

    def flash(self, action):
        """Коротко підсвітити іконку в треї кольором дії."""
        self.flashing = self.actions[action].color
        self._tray(w.NIM_MODIFY)
        w.SetTimer(self.hwnd, FLASH_TIMER_ID, _FLASH_MS, None)
        log.debug("tray flash on")

    def _end_flash(self):
        log.debug("tray flash off")
        w.KillTimer(self.hwnd, FLASH_TIMER_ID)
        self.flashing = None
        self._tray(w.NIM_MODIFY)

    def refresh_tray(self):
        self._update_icon()
        self._tray(w.NIM_MODIFY)

    def notify(self, text, warning=False, title=None, quiet=False, balloon_icon=None):
        self._tray(w.NIM_MODIFY, info=text, warning=warning, title=title, quiet=quiet,
                   balloon_icon=balloon_icon)

    def show_menu(self):
        # Клік по треї активує панель задач, тож дії з меню виконуються для вікна,
        # яке було активним до цього
        target = self.last_window
        m = w.CreatePopupMenu()
        sub = w.CreatePopupMenu()
        for num, action in self.actions.items():
            if action.menu:
                text = self.hotkey_text(action)
                w.AppendMenuW(sub, w.MF_STRING, ID_ACTION_BASE + num,
                              action.label + ("\t" + text if text else ""))
        w.AppendMenuW(m, w.MF_POPUP, sub, tr("menu.actions"))
        w.AppendMenuW(m, w.MF_SEPARATOR, 0, None)
        w.AppendMenuW(m, w.MF_STRING | (w.MF_CHECKED if self.cfg.enabled else 0), ID_ENABLED, tr("menu.enabled"))
        w.AppendMenuW(m, w.MF_STRING | (w.MF_CHECKED if self.cfg.autocorrect else 0), ID_AUTOCORRECT,
                      tr("menu.autocorrect"))
        w.AppendMenuW(m, w.MF_STRING | (w.MF_CHECKED if self.cfg.eye_breaks else 0), ID_EYES,
                      tr("menu.eyes"))
        w.AppendMenuW(m, w.MF_STRING | (w.MF_CHECKED if self.cfg.work_breaks else 0), ID_WORK,
                      tr("menu.work"))
        w.AppendMenuW(m, w.MF_STRING, ID_STATS, tr("menu.stats"))
        w.AppendMenuW(m, w.MF_STRING, ID_SETTINGS, tr("menu.settings"))
        w.AppendMenuW(m, w.MF_STRING, ID_OPEN_INI, tr("menu.open_ini"))
        w.AppendMenuW(m, w.MF_STRING, ID_RELOAD, tr("menu.reload"))
        w.AppendMenuW(m, w.MF_STRING, ID_PLUGINS, tr("menu.plugins"))
        w.AppendMenuW(m, w.MF_STRING, ID_FORCED, tr("menu.forced"))
        w.AppendMenuW(m, w.MF_SEPARATOR, 0, None)
        w.AppendMenuW(m, w.MF_STRING, ID_EXIT, tr("menu.exit"))
        w.SetMenuDefaultItem(m, ID_SETTINGS, False)
        pt = w.POINT()
        w.GetCursorPos(ctypes.byref(pt))
        w.SetForegroundWindow(self.hwnd)
        cmd = w.TrackPopupMenu(m, w.TPM_RETURNCMD | w.TPM_RIGHTBUTTON | w.TPM_NONOTIFY,
                               pt.x, pt.y, 0, self.hwnd, None)
        w.PostMessageW(self.hwnd, w.WM_NULL, 0, 0)
        w.DestroyMenu(m)

        if cmd == ID_ENABLED:
            self.cfg.enabled = not self.cfg.enabled
            self.cfg.save()
            self.refresh_tray()
            self._update_raw_input()
        elif cmd == ID_AUTOCORRECT:
            self.cfg.autocorrect = not self.cfg.autocorrect
            self.cfg.save()
            self._update_raw_input()
        elif cmd == ID_EYES:
            self.cfg.eye_breaks = not self.cfg.eye_breaks
            self.cfg.save()
            self.eyes.reset()
        elif cmd == ID_WORK:
            self.cfg.work_breaks = not self.cfg.work_breaks
            self.cfg.save()
            self.work.reset()
        elif cmd == ID_STATS:
            self.show_stats()
        elif cmd == ID_SETTINGS:
            self.open_settings()
        elif cmd == ID_OPEN_INI:
            os.startfile(config.CONFIG_PATH)
        elif cmd == ID_RELOAD:
            self.reload_config()
        elif cmd == ID_PLUGINS:
            directory = actions.plugins_dir(config.app_dir())
            os.makedirs(directory, exist_ok=True)
            os.startfile(directory)
        elif cmd == ID_FORCED:
            try:
                self.forced_words.ensure_file()
                os.startfile(FORCED_PATH)
            except OSError as e:
                self.notify(tr("err.save", FORCED_PATH, e), warning=True)
        elif cmd == ID_EXIT:
            self.exit()
        elif cmd - ID_ACTION_BASE in self.actions:
            self.run_action(cmd - ID_ACTION_BASE, target)

    def _on_foreground(self, _hook, _event, hwnd, id_object, _id_child, _thread, _time):
        """EVENT_SYSTEM_FOREGROUND (WinEvent — не хук клавіатури)."""
        try:
            if id_object == 0:
                self._remember_window(hwnd)
        except Exception:
            log.exception("foreground event failed")

    def _remember_window(self, hwnd):
        """Запам'ятати останнє «робоче» активне вікно — не панель задач, не робочий
        стіл і не вікна самої програми: для нього виконуються дії з меню трею."""
        if not hwnd:
            return
        pid = ctypes.c_ulong()
        w.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != os.getpid() and w.class_name(hwnd) not in _SHELL_CLASSES:
            self.last_window = hwnd

    # ---------- дії ----------

    def _load_actions(self):
        """Вбудовані дії + plugins/*.py. Повертає [(файл, помилка)] плагінів, що не завантажилися."""
        self._unregister_hotkeys()
        registry = actions.Registry()
        steps = {HOTKEY_LAYOUT: self._convert_layout, HOTKEY_CASE: self._toggle_case,
                 HOTKEY_TRANSLIT: self._transliterate}
        for num, (key, _field, title, color) in _BUILTIN.items():
            registry.add(actions.Action(key, i18n.translations(title), steps[num], color=color, num=num))
        failed = actions.load_plugins(registry, actions.plugins_dir(config.app_dir()), self)
        for i, action in enumerate(registry.plugin_actions()):
            action.num = _PLUGIN_BASE + i
        self.actions = {a.num: a for a in registry.actions if a.num < _HOTKEY_ALIAS}
        return failed

    def hotkey_text(self, action, values=None):
        """Комбінація дії: з config (або з `values` вікна налаштувань); для дій плагінів —
        з секції [plugins], а якщо там немає — та, що задав плагін."""
        source = values if values is not None else dataclasses.asdict(self.cfg)
        field = _BUILTIN_FIELDS.get(action.key)
        if field:
            return source[field]
        return source["plugin_hotkeys"].get(action.key, action.hotkey)

    def run_action(self, num, fg):
        """Виконати дію з меню (а не гарячою клавішею): спершу повернути фокус вікну fg."""
        if not fg or not w.IsWindow(fg):
            w.MessageBeep(0)
            return
        if not w.SetForegroundWindow(fg):
            kio.unlock_foreground()
            w.SetForegroundWindow(fg)
        end = time.monotonic() + _FOCUS_TIMEOUT
        while w.GetForegroundWindow() != fg:
            if time.monotonic() > end:
                log.warning("action %d: window %#x did not get focus", num, fg)
                w.MessageBeep(0)
                return
            w.sleep_pumping(0.02)
        w.sleep_pumping(0.05)  # хай вікно поверне курсор у поле
        self.on_hotkey(num, fg)

    def edit_text(self, transform):
        """Для плагінів: замінити виділений текст (або останнє слово) на transform(текст)."""
        return self._edit_text(transform)

    def type_text(self, text):
        """Для плагінів: надрукувати текст у позиції курсора."""
        kio.type_text(text)

    # ---------- гаряча клавіша ----------

    def _register(self, action, text):
        """Зареєструвати комбінацію `text` для дії. True — успішно."""
        try:
            mods, vk = hk.parse(text)
        except ValueError as e:
            log.warning("bad hotkey %r: %s", text, e)
            return False
        for i, v in enumerate(hk.register_vks(mods, vk)):
            if not w.RegisterHotKey(self.hwnd, action + i * _HOTKEY_ALIAS, mods | hk.MOD_NOREPEAT, v):
                for j in range(i):
                    w.UnregisterHotKey(self.hwnd, action + j * _HOTKEY_ALIAS)
                return False
        return True

    def _unregister_hotkeys(self):
        self.registered = {}
        for action in self.actions:
            for i in range(2):
                w.UnregisterHotKey(self.hwnd, action + i * _HOTKEY_ALIAS)

    def _register_hotkeys(self):
        """Повертає список комбінацій, які не вдалося зареєструвати."""
        self._unregister_hotkeys()
        failed = []
        self.hotkey_ok = True
        for num, action in self.actions.items():
            text = self.hotkey_text(action)
            if not text:
                continue
            if self._register(num, text):
                self.registered[num] = hk.parse(text)
            else:
                failed.append(text if num in _BUILTIN else "%s (%s)" % (text, action.label))
                if num == HOTKEY_LAYOUT:
                    self.hotkey_ok = False
        # Натискання гарячої клавіші розкладки не скасовує можливість скасувати автовиправлення
        mods, vk = self.registered.get(HOTKEY_LAYOUT, (0, 0))
        self.tracker.ignore_vks = set(hk.register_vks(mods, vk)) if vk else set()
        self.refresh_tray()
        return failed

    def _warn_failed(self, failed, failed_plugins=()):
        parts = []
        if failed:
            parts.append(tr("warn.hotkeys", ", ".join("«%s»" % t for t in failed)))
        if failed_plugins:
            parts.append(tr("warn.plugins", "; ".join("%s — %s" % item for item in failed_plugins)))
        if parts:
            self.notify(" ".join(parts), warning=True)

    def reload_config(self):
        self.cfg = config.Config.load()
        i18n.set_language(self.cfg.language)
        self.ac_exceptions = autocorrect.load_words(EXCEPTIONS_PATH)
        self.forced_words.refresh(force=True)
        failed_plugins = self._load_actions()
        self._warn_failed(self._register_hotkeys(), failed_plugins)
        self._update_raw_input()

    # ---------- налаштування ----------

    def open_settings(self):
        if self.settings_root is not None:
            self.settings_root.deiconify()
            self.settings_root.lift()
            self.settings_root.focus_force()
            return
        import settings_ui
        self._unregister_hotkeys()  # щоб комбінації можна було «зловити» в полях
        try:
            settings_ui.run(self)
        finally:
            self.settings_root = None
            self._warn_failed(self._register_hotkeys())
            if self.exit_pending:
                w.DestroyWindow(self.hwnd)

    def apply_settings(self, values, autostart):
        """Викликається з вікна налаштувань. Повертає текст помилки або None."""
        error = self._check_hotkeys(values)
        if error:
            return error

        # Зміни застосовуються або всі, або жодна: спершу автозапуск, потім config.ini,
        # а якщо збереження не вдалося — відкочуємо автозапуск і налаштування в пам'яті.
        old_autostart = config.autostart_enabled()
        if autostart != old_autostart:
            try:
                config.set_autostart(autostart)
            except OSError as e:
                return tr("err.autostart", e)
        backup = dataclasses.replace(self.cfg)
        for key, value in values.items():
            setattr(self.cfg, key, value)
        try:
            self.cfg.save()
        except OSError as e:
            self.cfg = backup
            if autostart != old_autostart:
                try:
                    config.set_autostart(old_autostart)
                except OSError:
                    log.exception("autostart rollback failed")
            return tr("err.save", config.CONFIG_PATH, e)
        i18n.set_language(self.cfg.language)
        self.eyes.reset()
        self.refresh_tray()
        self._update_raw_input()
        return None

    def _check_hotkeys(self, values):
        """Перевірити комбінації з вікна налаштувань пробною реєстрацією.
        Остаточно вони зареєструються після закриття вікна."""
        seen = set()
        try:
            for action, entry in self.actions.items():
                text = self.hotkey_text(entry, values)
                if not text:
                    continue
                try:
                    mods, vk = hk.parse(text)
                except ValueError as e:
                    return tr("err.hotkey", text, e)
                key = (mods, hk.normalize_vk(vk))
                if key in seen:
                    return tr("err.hotkey_twice", text)
                seen.add(key)
                if not self._register(action, text):
                    return tr("err.hotkey_taken", text)
            return None
        finally:
            self._unregister_hotkeys()

    def exit(self):
        if self.settings_root is not None:
            self.exit_pending = True
            self.settings_root.after(0, self.settings_root.destroy)
        else:
            w.DestroyWindow(self.hwnd)

    # ---------- дії з текстом ----------

    def on_hotkey(self, action, fg=None):
        """Виконати дію: за гарячою клавішею (fg=None — для активного вікна) або з меню
        (fg — вікно, якому вже повернуто фокус; «Увімкнено» тоді не діє — це явний вибір)."""
        from_menu = fg is not None
        if self.busy or action not in self.actions or not (from_menu or self.cfg.enabled):
            return
        fg = fg or w.GetForegroundWindow()
        if not fg or fg == self.hwnd:
            return
        # Текст зараз зміниться — набране до цього вже не відповідає полю
        correction, correction_fg = self.tracker.correction, self.tracker.fg
        self.tracker.reset()
        self.busy = True
        try:
            if action == HOTKEY_LAYOUT and correction and fg == correction_fg:
                self._undo_autocorrect(correction, fg)
            else:
                self._run_action(action, fg, from_menu)
        except Exception as e:
            log.exception("action %s failed", self.actions[action].key)
            if self.actions[action].plugin:
                self.notify(tr("err.action", self.actions[action].label, self.actions[action].plugin, e),
                            warning=True)
        finally:
            self.busy = False
            # Події модифікаторів під час дії міг забрати PhysicalKeys.poll(), а свої
            # натискання ми не враховуємо — беремо стан, у якому їх лишила дія
            self.tracker.sync_mods(vk for vk in kio.SIDED_MODIFIER_VKS if kio.is_down(vk))
            self.tracker.caps = None  # і Caps Lock звіримо заново перед наступним словом
            self._watch_after_conversion()
            # Після обробки: потік одразу повертається до циклу повідомлень,
            # тож WM_TIMER прийде вчасно й іконка світиться рівно _FLASH_MS.
            self.flash(action)

    def _run_action(self, action, fg, from_menu=False):
        step = self.actions[action].run
        if from_menu:
            if kio.wait_modifiers_released(3.0):
                step(fg)
            return
        if action not in self.registered:
            return  # комбінація цієї дії не зареєстрована (невалідна чи зайнята)
        mods, vk = self.registered[action]
        groups = hk.modifier_groups(mods)
        keys = None
        if groups:
            try:
                keys = kio.PhysicalKeys(self.hwnd, keep=self.raw[_RAW_KEYBOARD], on_input=self._on_user_input)
            except OSError:
                log.exception("raw input is unavailable")
        try:
            if keys and keys.held(groups):
                self._hold_session(action, fg, step, keys, groups, hk.register_vks(mods, vk))
                return
            # Комбінацію вже відпустили (або модифікаторів немає) — один крок
            kio.neutralize_alt_win()
            if kio.wait_modifiers_released(3.0):
                step(fg)
        finally:
            if keys:
                keys.close()

    def _hold_session(self, action, fg, step, keys, groups, vks):
        """Як Alt+Tab: поки модифікатори комбінації фізично утримуються, кожне натискання
        клавіші (Alt + Pause, Pause, Pause) — ще один крок по колу, одразу видно результат.

        Надсилати Ctrl+C і друкувати, поки утримується Alt, не можна — програма отримала б
        Ctrl+Alt+C тощо. Тому модифікатори логічно відпускаємо, а фізичний стан стежимо
        через Raw Input. Для Windows наступні натискання — це вже клавіша без модифікаторів:
        її на цей час теж реєструємо (щоб «голий» Pause/F12 не дійшов до програми).
        Через це id і модифікатори у WM_HOTKEY показують логічний стан, а не те, що
        натиснув користувач, тож дію визначаємо за фізичними модифікаторами на момент
        натискання (_take_hotkeys). Натискання інших дій не губляться: сеанс завершується,
        а вони повертаються в чергу й виконуються після нього.
        """
        combos = self._hotkey_combos()
        deferred = []  # (дія, lParam) — натискання інших дій, по порядку
        swallowed, released = [], []
        try:
            # Усе, що змінює стан (реєстрація, логічне відпускання), — уже під finally
            for i, v in enumerate(vks):
                if w.RegisterHotKey(self.hwnd, _SWALLOW_ID + i, hk.MOD_NOREPEAT, v):
                    swallowed.append(i)
            released = kio.release_modifiers()
            pending, last = 1, time.monotonic()
            log.debug("hold session %d: fg=%#x released=%s swallowed=%s", action, fg, released, swallowed)
            while True:
                if pending:
                    pending -= 1
                    step(fg)
                    last = time.monotonic()
                    self._blink(action)
                keys.poll()
                pending += self._take_hotkeys(action, keys, combos, deferred)
                if pending:
                    continue
                if deferred:
                    log.debug("hold session: another action pressed")
                    break
                if not keys.held(groups):
                    log.debug("hold session: modifiers released")
                    break
                if time.monotonic() - last > _HOLD_TIMEOUT:
                    log.debug("hold session timed out")
                    break
                w.sleep_pumping(0.01)
        finally:
            for i in swallowed:
                w.UnregisterHotKey(self.hwnd, _SWALLOW_ID + i)
            keys.poll()
            self._take_hotkeys(None, keys, combos, deferred)  # після сеансу — усе відкладаємо
            # Що досі фізично утримується — повертаємо логічно, щоб стан не розійшовся
            kio.press_modifiers([vk for vk in released if vk in keys.at(None)])
            for target, lparam in deferred:
                w.PostMessageW(self.hwnd, w.WM_HOTKEY, target, lparam)

    def _hotkey_combos(self):
        """{(mods, vk): дія} для зареєстрованих гарячих клавіш. Невалідні й зайняті
        (зокрема дубль іншої дії) сюди не потрапляють, тож не перехоплять натискання."""
        return {(mods, hk.normalize_vk(vk)): action for action, (mods, vk) in self.registered.items()}

    def _take_hotkeys(self, action, keys, combos, deferred):
        """Забрати з черги WM_HOTKEY і розібрати, яку комбінацію фізично натиснули:
        клавіша — HIWORD(lParam), модифікатори — з Raw Input на момент повідомлення.
        Повертає кількість повторів поточної дії; натискання інших дій (і все, що після
        них) додає в deferred."""
        msg = w.MSG()
        count = 0
        while w.PeekMessageW(ctypes.byref(msg), self.hwnd, w.WM_HOTKEY, w.WM_HOTKEY, w.PM_REMOVE):
            vk = hk.normalize_vk((msg.lParam >> 16) & 0xFFFF)
            mods = hk.mods_from_vks(keys.at(msg.time))
            target = combos.get((mods, vk))
            log.debug("hold session: WM_HOTKEY id=%d -> %s = action %s", msg.wParam, hk.format(mods, vk), target)
            if target is None:
                continue  # голу клавішу без модифікаторів, що не є жодною дією, лише поглинаємо
            if target == action and not deferred:
                count += 1
            else:
                deferred.append((target, (msg.lParam & 0xFFFF0000) | (mods & 0xFFFF)))
        return count

    def _blink(self, action):
        """Миттєво блимнути іконкою — відгук на кожен крок."""
        self.flashing = self.actions[action].color
        self._tray(w.NIM_MODIFY)
        w.sleep_pumping(0.08)
        self.flashing = None
        self._tray(w.NIM_MODIFY)

    def _convert_layout(self, fg):
        hkls = layouts.installed()
        if len(hkls) < 2:
            w.MessageBeep(0)
            return
        current = layouts.current(w.GetWindowThreadProcessId(fg, None))
        log.debug("layout: fg=%#x layout=%#x", fg, current)
        dst = converted = None

        def transform(text):
            nonlocal dst, converted
            src = layouts.detect_source(text, hkls, current)
            dst = layouts.next_after(src, hkls)
            conv = layouts.convert(text, src, dst)
            converted = (text, conv)
            return conv

        if not self._edit_text(transform):
            return
        if dst and self.cfg.switch_layout:
            layouts.switch(fg, dst)
        if converted and converted[0] != converted[1]:
            self._count_conversion(fg, *converted)

    def _count_conversion(self, fg, text, conv):
        """Порахувати конвертацію гарячою клавішею. Повторне натискання на щойно
        перетвореному тексті (наступна розкладка по колу) — та сама помилка, не нова:
        той самий текст у тому самому вікні, а між натисканнями — жодної іншої клавіші
        чи кліку (щоб перейти до іншого поля, без них не обійтися; див. _forget_conversion).
        Стеження за введенням вмикає on_hotkey після дії."""
        last = self._last_conv
        if not (last and last == (fg, text)):
            self.stats.manual(len(conv))
        self._last_conv = (fg, conv)
        w.SetTimer(self.hwnd, RECONVERT_TIMER_ID, _RECONVERT_MS, None)
        # Кліки — вже зараз: під час утримання модифікаторів (_hold_session) їх
        # передасть PhysicalKeys; клавіатуру поки тримає він, її підписку — після дії
        self._update_raw_mouse()

    def _on_user_input(self, vk):
        """Натиснуто клавішу (vk, не модифікатор) або кнопку миші (None) — фізично."""
        if vk is None or vk not in self.tracker.ignore_vks:  # ignore_vks — гаряча клавіша розкладки
            self._forget_conversion()

    def _forget_conversion(self):
        """Наступна конвертація — уже нове виправлення: користувач щось натиснув або
        клацнув, минув час, чи за введенням не вдалося стежити."""
        if self._last_conv is None:
            return
        self._last_conv = None
        w.KillTimer(self.hwnd, RECONVERT_TIMER_ID)
        if not self.busy:  # під час дії підписку оновить on_hotkey (її тримає PhysicalKeys)
            self._update_raw_input()

    def _watch_after_conversion(self):
        """Після дії: поки повтор можливий, стежити за клавіатурою й мишею."""
        self._update_raw_input()
        if self._last_conv is not None and not (self.raw[_RAW_KEYBOARD] and self.raw[_RAW_MOUSE]):
            self._forget_conversion()  # не бачитимемо введення — повтор не розпізнати

    def _toggle_case(self, _fg):
        self._edit_text(self.case_cycler.next)

    def _transliterate(self, _fg):
        self._edit_text(self.translit.next)

    def _edit_text(self, transform):
        """Замінити виділений текст (або останнє слово перед курсором) на transform(текст).

        Повертає True, якщо текст оброблено (навіть якщо він не змінився),
        False — якщо дію перервано без змін.
        """
        timeout = self.cfg.copy_timeout_ms / 1000.0
        # Без знімка буфер не можна чіпати: його вміст було б неможливо повернути.
        snapshot = self.clip.snapshot()
        if snapshot is None:
            _abort("clipboard is busy, cannot save its contents")
            return False
        ok = pasted = False
        try:
            text = self.clip.copy_from(kio.copy, timeout)
            log.debug("selection=%r", text)
            if text and _looks_like_line_copy(text):
                has_selection = self._probe_selection(text, timeout)
                if has_selection is None:
                    return False
                if not has_selection:
                    text = None  # редактор скопіював рядок — виділення насправді немає
            if text:
                ok, pasted = self._convert_selection(text, transform)
            else:
                ok = self._convert_last_word(transform, timeout)
        finally:
            if pasted:
                w.sleep_pumping(_PASTE_SETTLE)
            if not self.clip.restore(snapshot):
                log.warning("clipboard contents were not fully restored")
        return ok

    def _probe_selection(self, text, timeout):
        """Ctrl+C дав «рядок\\n»: це виділення чи редактор скопіював рядок без виділення?

        Зсуваємо активний кінець на символ (Shift+Left) і копіюємо ще раз:
        - було виділення «рядок\\n» -> виходить «рядок» (або «\\nрядок\\n», якщо виділяли
          справа наліво);
        - виділення не було -> виділяється один символ перед курсором.
        Потім Shift+Right повертає все як було. Повертає True/False або None,
        якщо однозначно визначити не вдалося (конвертацію перервано).
        """
        if not text.strip():
            log.debug("only a line break was copied — nothing to convert")
            return None
        probe = self.clip.copy_from(kio.extend_left_and_copy, timeout)
        log.debug("selection probe (left): %r", probe)
        if probe == text:
            # Shift+Left нічого не змінив: активний кінець на початку поля. Або виділення
            # нема, або його виділяли справа наліво до самого початку — пробуємо вправо.
            return self._probe_from_field_start(text, timeout)
        kio.press(kio.VK_RIGHT, (kio.VK_SHIFT,))
        if probe is None:
            return self._classify_probe(None, False)
        return self._classify_probe(probe, probe == text.rstrip("\r\n") or probe.endswith(text))

    def _probe_from_field_start(self, text, timeout):
        """Shift+Right від початку поля: зворотне виділення «рядок\\n» звузиться
        до «ядок\\n», а без виділення виділиться один символ."""
        probe = self.clip.copy_from(kio.extend_right_and_copy, timeout)
        log.debug("selection probe (right): %r", probe)
        if probe == text:
            _abort("selection probe: the caret moves neither left nor right")
            return None
        kio.press(kio.VK_LEFT, (kio.VK_SHIFT,))
        return self._classify_probe(probe, probe == text[1:])

    @staticmethod
    def _classify_probe(probe, looks_selected):
        """True — виділення було, False — ні, None — неоднозначно (перервано)."""
        if probe is None:
            _abort("selection probe copy failed")
            return None
        selected = looks_selected
        single_char = kio.caret_len(probe) == 1
        if selected and single_char:
            _abort("one-character line: cannot tell a selection from a line copy")
            return None
        if selected or single_char:
            return selected
        _abort("unexpected selection probe result")
        return None

    def _convert_selection(self, text, transform):
        """Повертає (оброблено, вставлено через буфер)."""
        conv = transform(text)
        pasted = False
        if conv != text:
            if "\n" in conv or len(conv) > _PASTE_THRESHOLD:
                # Ctrl+V лише якщо в буфері точно наш текст — інакше замінили б
                # виділення чужим вмістом.
                if not self.clip.set_text(conv) or self.clip.get_text() != conv:
                    _abort("could not put converted text into the clipboard")
                    return False, False
                kio.paste()
                pasted = True
            else:
                kio.type_text(conv)
            n = kio.caret_len(conv)
            if self.cfg.reselect and n <= _MAX_RESELECT:
                kio.press(kio.VK_LEFT, (kio.VK_SHIFT,), n)
        return True, pasted

    def _convert_last_word(self, transform, timeout):
        # Розширюємо виділення вліво, доки не впремося в пробіл/початок поля.
        # Ctrl+Shift+Left зупиняється на розділових знаках, а в іншій розкладці
        # це можуть бути літери (б, ю, ж, х, ї, є), тож кроків може бути кілька.
        selected = None
        for _ in range(_MAX_WORD_STEPS):
            t = self.clip.copy_from(kio.select_word_left_and_copy, timeout)
            log.debug("word step: %r", t)
            if not t:
                if selected is not None:
                    # Виділення вже розширене, але його вміст невідомий — замінювати
                    # не можна. Знімаємо виділення: курсор повертається на правий край.
                    kio.press(kio.VK_RIGHT)
                    _abort("copy failed while selecting the last word")
                return False
            if t == selected:
                break  # далі не розширюється — початок поля
            selected = t
            if _WS.search(selected.rstrip()):
                break  # дійшли до пробілу перед словом
        else:
            # Межу слова так і не знайдено — не замінюємо лише частину.
            kio.press(kio.VK_RIGHT)
            _abort("word boundary not found in %d steps" % _MAX_WORD_STEPS)
            return False
        if selected is None:
            return False

        core = selected.rstrip()
        suffix = selected[len(core):]
        spaces = list(_WS.finditer(core))
        prefix = core[:spaces[-1].end()] if spaces else ""
        word = core[len(prefix):]
        if not word or "\n" in suffix:
            # Нічого конвертувати — повертаємо курсор на місце, знімаючи виділення.
            kio.press(kio.VK_RIGHT, (kio.VK_SHIFT,), kio.caret_len(selected))
            return False

        conv = transform(word)
        if conv == word:
            kio.press(kio.VK_RIGHT, (kio.VK_SHIFT,), kio.caret_len(selected))
            return True
        # Активний кінець виділення зліва: зсуваємо його вправо за префікс,
        # лишаючи виділеними тільки слово + пробіли після нього, і передруковуємо їх.
        if prefix:
            kio.press(kio.VK_RIGHT, (kio.VK_SHIFT,), kio.caret_len(prefix))
            # Перевіряємо, що виділено саме те, що збираємося замінити
            # (контрол міг інакше обробити Shift+Right).
            check = self.clip.copy_from(kio.copy, timeout)
            if check != word + suffix:
                log.debug("verify: expected %r, got %r", word + suffix, check)
                kio.press(kio.VK_RIGHT)
                _abort("selection does not match the word to replace")
                return False
        kio.type_text(conv + suffix)
        return True

    # ---------- автовиправлення розкладки ----------

    def _set_raw(self, usage, on):
        if self.raw[usage] == on:
            return
        dev = w.RAWINPUTDEVICE(0x01, usage, w.RIDEV_INPUTSINK if on else w.RIDEV_REMOVE,
                               self.hwnd if on else None)
        if w.RegisterRawInputDevices(ctypes.byref(dev), 1, ctypes.sizeof(dev)):
            self.raw[usage] = on
        else:
            log.warning("RegisterRawInputDevices(%#x, %s) failed: %d", usage, on, ctypes.get_last_error())

    def _update_raw_input(self):
        """Стежити за клавіатурою, поки автовиправлення увімкнене (і поки чекаємо на
        повернення користувача після бездіяльності — див. _watch_away)."""
        on = self.cfg.enabled and self.cfg.autocorrect
        if on != self.ac_tracking:
            self.ac_tracking = on
            self.tracker.reset()
            self.tracker.caps = None  # поки не стежили, Caps Lock могли перемкнути
        if on:  # мовні дані — заздалегідь, щоб перше виправлення не барилося
            for hkl in layouts.installed():
                autocorrect.model(autocorrect.lang_of(hkl))
        self._set_raw(_RAW_KEYBOARD, on or self.away.watching is not None or self._last_conv is not None)
        self._update_raw_mouse()

    def _update_raw_mouse(self):
        """Клік мишею може перенести курсор, тож поки є набране слово (або виправлення,
        яке можна скасувати, чи конвертація, яку можна повторити), стежимо й за кнопками
        миші. Решту часу — ні: рух миші дає сотні подій за секунду (крім очікування
        повернення користувача — тоді подій немає, а перша ж знімає підписку)."""
        self._set_raw(_RAW_MOUSE, (self.ac_tracking and self.tracker.active)
                      or self.away.watching is not None or self._last_conv is not None)

    def _on_raw_input(self, lparam):
        """Обробити WM_INPUT. Повертає True, якщо це дія користувача, після якої
        передруковувати вже не можна (натиснуто клавішу або кнопку миші)."""
        if self.away.watching is not None:
            self._on_return(w.GetMessageTime())
        if not (self.ac_tracking or self._last_conv is not None):
            return False  # підписка лише заради перерв (або запізніла подія після неї)
        buf = self._raw_buf
        size = ctypes.c_uint(ctypes.sizeof(buf))
        got = w.GetRawInputData(lparam, w.RID_INPUT, buf, ctypes.byref(size),
                                ctypes.sizeof(w.RAWINPUTHEADER))
        if got in (0, 0xFFFFFFFF):
            return False
        header = w.RAWINPUTHEADER.from_buffer(buf)
        if header.dwType == w.RIM_TYPEMOUSE:
            buttons = w.RAWINPUT_MOUSE.from_buffer(buf).mouse.ulButtons & 0xFFFF
            if not buttons & w.RI_MOUSE_BUTTONS_DOWN:
                return False
            self._on_user_input(None)
            if self.ac_tracking:
                self.tracker.mouse_click()
            self._update_raw_mouse()
            return True
        if header.dwType != w.RIM_TYPEKEYBOARD:
            return False
        kb = w.RAWINPUT_KEYBOARD.from_buffer(buf).keyboard
        vk = kio.sided(kb.VKey, kb.MakeCode, kb.Flags)
        down = not kb.Flags & w.RI_KEY_BREAK
        injected = not header.hDevice
        if down and not injected and vk not in kio.SIDED_MODIFIER_VKS:
            self._on_user_input(vk)
        if not self.ac_tracking:
            return False
        own = injected and kb.ExtraInformation == kio.OWN_INPUT
        fg = hkl = None
        if down and not injected:
            fg = w.GetForegroundWindow()
            hkl = layouts.current(w.GetWindowThreadProcessId(fg, None))
            self._sync_caps(vk)
        words = self.tracker.key(vk, down, injected, fg, hkl, own)
        if words is not None:
            self._on_word(words, fg, hkl)
        elif self.tracker.appended:
            self._on_typing(fg, hkl)
        self._update_raw_mouse()
        return down and not injected and vk not in kio.SIDED_MODIFIER_VKS

    def _sync_caps(self, vk):
        """Перемикання Caps Lock трекер рахує сам; вихідний стан (на старті й після
        гарячих клавіш він невідомий) беремо перед першою літерою."""
        if vk in layouts.TYPING_VKS and self.tracker.caps is None:
            self.tracker.caps = kio.caps_on()

    def _on_word(self, words, fg, hkl):
        """Після пробілу: виправити слово (і короткі слова перед ним), якщо треба."""
        correction = None
        if not self._draining:
            try:
                correction = self._pick_correction(words, fg, hkl)
            except Exception:
                log.exception("autocorrect failed")
        self.tracker.finished(words, correction is not None)
        if correction is not None:
            self._apply_correction(correction, fg)

    def _on_typing(self, fg, hkl):
        """Слово ще набирається: якщо так починається слово зі списку «завжди у своїй
        розкладці», виправити одразу, не чекаючи пробілу. Лише з перемиканням
        розкладки — інакше решта слова пішла б у старій."""
        if self._draining or not self.cfg.switch_layout:
            return
        self.forced_words.refresh()
        if not self.forced_words:
            return
        try:
            correction = autocorrect.forced(self.tracker.keys, hkl, layouts.installed(),
                                            self.forced_words, partial=True)
            if correction is None or not self._can_correct(fg, hkl):
                return
        except Exception:
            log.exception("autocorrect failed")
            return
        self._apply_correction(correction, fg)

    def _apply_correction(self, correction, fg):
        # Поки ми думали, користувач міг друкувати далі: тоді передрук зіпсував би текст
        if self._drain_input():
            log.debug("autocorrect skipped: input continued")
            return
        if self.tracker.mods - {0xA0, 0xA1}:
            log.debug("autocorrect skipped: modifiers held")  # Ctrl+Backspace стер би слово
            self.tracker.reset()
            return
        if not kio.retype(len(correction.typed) + len(correction.tail), correction.fixed + correction.tail):
            log.warning("autocorrect: SendInput failed")
            self.tracker.reset()
            return
        # Лише тепер його можна скасовувати: воно справді надруковане
        self.tracker.correction = correction
        self.stats.auto(len(correction.typed))
        log.debug("autocorrect: %d chars, layout %#x -> %#x", len(correction.typed),
                  correction.src & 0xFFFFFFFF, correction.dst & 0xFFFFFFFF)
        if self.cfg.switch_layout:
            layouts.switch(fg, correction.dst)
            if not correction.tail:
                self.tracker.switched(correction.dst)  # слово набирається далі
        self.flash(HOTKEY_LAYOUT)

    def _can_correct(self, fg, hkl):
        if self.busy or not fg or not hkl:
            return False
        pid = ctypes.c_ulong()
        w.GetWindowThreadProcessId(fg, ctypes.byref(pid))
        if pid.value == os.getpid():
            return False  # наші власні вікна (налаштування)
        excluded = self.cfg.excluded_apps()
        if excluded and w.process_name(fg).lower() in excluded:
            return False
        return not eyecare.fullscreen_app()  # ігри: WASD + пробіл — не текст

    def _pick_correction(self, words, fg, hkl):
        if not self._can_correct(fg, hkl):
            return None
        self.forced_words.refresh()
        return autocorrect.choose(words, hkl, layouts.installed(), self.ac_exceptions, self.forced_words)

    def _drain_input(self):
        """Обробити WM_INPUT, що вже чекають у черзі. True — серед них є дії користувача."""
        msg = w.MSG()
        activity = False
        self._draining = True
        try:
            while w.PeekMessageW(ctypes.byref(msg), self.hwnd, w.WM_INPUT, w.WM_INPUT, w.PM_REMOVE):
                activity |= self._on_raw_input(msg.lParam)
                w.DefWindowProcW(self.hwnd, w.WM_INPUT, msg.wParam, msg.lParam)
        finally:
            self._draining = False
        return activity

    def _undo_autocorrect(self, correction, fg):
        """Гаряча клавіша розкладки одразу після автовиправлення — повернути як було
        і запам'ятати слово, щоб більше його не чіпати."""
        kio.neutralize_alt_win()
        if not kio.wait_modifiers_released(3.0):
            return
        if not kio.retype(len(correction.fixed) + len(correction.tail), correction.typed + correction.tail):
            return
        self.stats.undo(len(correction.typed))
        if self.cfg.switch_layout:
            layouts.switch(fg, correction.src)
        if correction.word and correction.word not in self.ac_exceptions:
            self.ac_exceptions.add(correction.word)
            try:
                autocorrect.add_exception(EXCEPTIONS_PATH, correction.word)
            except OSError:
                log.exception("cannot save autocorrect exception")

    # ---------- нагадування 20-20-20 і про перерву ----------

    def _eye_tick(self):
        self.stats.save_if_dirty()
        self._check_away()
        worked = None
        if self.cfg.work_breaks:
            worked = self.work.tick(self.cfg.work_break_minutes)
        else:
            self.work.reset()
        if not self.cfg.eye_breaks:
            self.eyes.reset()
        elif self.eyes.tick(self.cfg.eye_break_minutes) and worked is None:
            self.show_eye_break()
        if worked is not None:
            self.eyes.reset()  # перерва в роботі — заразом і для очей
            self.show_work_break(worked)

    def _check_away(self):
        """Перерва (5 хв без введення або сон) — відлік обох нагадувань заново. Щоб не
        пропустити паузу, яка закінчиться між перевірками, після 3 хв бездіяльності
        чекаємо на перше введення (_watch_away)."""
        if self.away.observe():
            self._took_break()
        if self.away.watching is not None:
            stale = self.away.stale()
            if stale is not None:  # введення пройшло повз підписку (сенсорний екран, перо)
                self._on_return(stale)
        elif (self.cfg.eye_breaks or self.cfg.work_breaks) and self.away.should_watch():
            self._watch_away()

    def _took_break(self):
        self.eyes.reset()
        self.work.reset()

    def _watch_away(self):
        """Підписатися на Raw Input клавіатури й миші, поки користувача немає: перше
        введення прийде повідомленням з часом, коли воно сталося."""
        if not self.away.watch():
            return
        self._update_raw_input()
        if not (self.raw[_RAW_KEYBOARD] and self.raw[_RAW_MOUSE]):
            self.away.stop()  # не вдалося — лишається щохвилинна перевірка
            self._update_raw_input()
            return
        stale = self.away.stale()
        if stale is not None:  # повернувся, поки ми підписувалися
            self._on_return(stale)

    def _on_return(self, input_tick):
        """Перше введення після бездіяльності: пауза ≥ 5 хв — перерва. Підписку
        повертаємо до тієї, що потрібна автовиправленню."""
        if self.away.returned(input_tick):
            log.debug("break detected on return")
            self._took_break()
        self._update_raw_input()

    def show_eye_break(self):
        if not self.eye_icon:  # велика іконка сповіщення — малюється при першому показі
            self.eye_icon = icon.create_eye_break_hicon(w.GetSystemMetrics(w.SM_CXICON) or 32)
        self.notify(tr("eye.text"), title=tr("eye.title"), quiet=True, balloon_icon=self.eye_icon)
        # Тайм-аут у NOTIFYICONDATA Windows ігнорує, тож закриваємо самі
        if self.cfg.eye_break_popup_seconds:
            w.SetTimer(self.hwnd, EYE_HIDE_TIMER_ID, self.cfg.eye_break_popup_seconds * 1000, None)

    def show_work_break(self, worked):
        if not self.work_icon:
            self.work_icon = icon.create_work_break_hicon(w.GetSystemMetrics(w.SM_CXICON) or 32)
        # Не закриваємо самі (як нагадування для очей) — його легко пропустити
        w.KillTimer(self.hwnd, EYE_HIDE_TIMER_ID)
        self.notify(tr("work.text", i18n.format_duration(worked)),
                    title=tr("work.title"), quiet=True, balloon_icon=self.work_icon)

    def show_stats(self):
        total, today, since = self.stats.summary()
        w.KillTimer(self.hwnd, EYE_HIDE_TIMER_ID)  # щоб не закрилося таймером нагадування
        self.notify(tr("stats.text", i18n.format_times(total["auto"] + total["manual"]),
                       total["auto"], total["manual"], i18n.format_saved(total["seconds"]),
                       i18n.format_times(today["auto"] + today["manual"]),
                       i18n.format_saved(today["seconds"]), i18n.format_date(since)),
                    title=tr("stats.title"), quiet=True)

    def _hide_eye_break(self):
        w.KillTimer(self.hwnd, EYE_HIDE_TIMER_ID)
        self._tray(w.NIM_MODIFY, info="")

    # ---------- цикл повідомлень ----------

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == w.WM_INPUT:
                self._on_raw_input(lparam)  # далі DefWindowProc — так вимагає Raw Input
            elif msg == w.WM_HOTKEY and wparam % _HOTKEY_ALIAS in self.actions:
                if self.away.watching is not None:  # раніше, ніж PhysicalKeys забере WM_INPUT
                    self._on_return(w.GetMessageTime())
                self.on_hotkey(wparam % _HOTKEY_ALIAS)
                return 0
            if msg == w.WM_TIMER and wparam == FLASH_TIMER_ID:
                self._end_flash()
                return 0
            if msg == w.WM_TIMER and wparam == EYE_TIMER_ID:
                self._eye_tick()
                return 0
            if msg == w.WM_TIMER and wparam == RECONVERT_TIMER_ID:
                self._forget_conversion()
                return 0
            if msg == w.WM_TIMER and wparam == EYE_HIDE_TIMER_ID:
                self._hide_eye_break()
                return 0
            if msg == WM_TRAY:
                event = lparam & 0xFFFF
                if event == w.WM_RBUTTONUP:
                    self.show_menu()
                elif event == w.WM_LBUTTONDBLCLK:
                    self.open_settings()
                return 0
            if msg == self.msg_taskbar_created:  # Explorer перезапустився
                self._tray(w.NIM_ADD)
                return 0
            if msg == w.WM_SETTINGCHANGE:  # зміна теми — перемальовуємо іконку
                self.refresh_tray()
            elif msg == w.WM_ENDSESSION and wparam:  # вихід із Windows: WM_DESTROY може не прийти
                self.stats.save_if_dirty()
            elif msg == w.WM_DESTROY:
                self.stats.save_if_dirty()
                self._tray(w.NIM_DELETE)
                if self._win_event_hook:
                    w.UnhookWinEvent(self._win_event_hook)
                w.PostQuitMessage(0)
                return 0
        except Exception:
            log.exception("wndproc error (msg=0x%04X)", msg)
        return w.DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self):
        msg = w.MSG()
        while w.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            w.TranslateMessage(ctypes.byref(msg))
            w.DispatchMessageW(ctypes.byref(msg))


def _setup_logging():
    if sys.stderr is None:  # --windowed збірка
        sys.stderr = open(os.devnull, "w")
    try:
        handler = logging.FileHandler(os.path.join(config.app_dir(), "layout_switcher.log"),
                                      encoding="utf-8", delay=True)
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    level = logging.DEBUG if os.environ.get("KLS_DEBUG") else logging.WARNING
    logging.basicConfig(level=level, handlers=[handler])


def main():
    _setup_logging()
    mutex = w.CreateMutexW(None, False, "Local\\KeyboardLayoutSwitcher.SingleInstance")
    if ctypes.get_last_error() == w.ERROR_ALREADY_EXISTS:
        i18n.set_language(config.Config.load().language)
        w.MessageBoxW(None, tr("already_running"), "Keyboard Layout Switcher", 0x40)
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App().run()
    del mutex


if __name__ == "__main__":
    main()
