"""Keyboard Layout Switcher — програма в треї, що конвертує текст,
набраний не в тій розкладці, і перемикає розкладку на наступну."""
import ctypes
import logging
import os
import re
import sys

import config
import hotkey as hk
import icon
import keyboard_io as kio
import layouts
import winapi as w
from clipboard import Clipboard

log = logging.getLogger("kls")

HOTKEY_ID = 1
WM_TRAY = w.WM_APP + 1
ID_ENABLED, ID_SETTINGS, ID_OPEN_INI, ID_RELOAD, ID_EXIT = range(100, 105)
_WS = re.compile(r"\s")
_MAX_WORD_STEPS = 8      # скільки разів Ctrl+Shift+Left шукати початок слова
_MAX_RESELECT = 5000     # не виділяти назад надто довгий текст
_PASTE_THRESHOLD = 300   # довший або багаторядковий текст вставляємо через буфер
_PASTE_SETTLE = 0.3      # дати програмі прочитати буфер перед відновленням


def _is_line_copy(text):
    """VS Code, JetBrains тощо без виділення копіюють увесь рядок разом із \\n."""
    return text.endswith("\n") and text.count("\n") == 1


class App:
    def __init__(self):
        self.cfg = config.Config.load()
        self.busy = False
        self.hotkey_ok = False
        self.settings_root = None
        self.exit_pending = False
        self.hicon = None

        self.msg_taskbar_created = w.RegisterWindowMessageW("TaskbarCreated")
        self._wndproc = w.WNDPROC(self._wnd_proc)  # тримаємо посилання від GC
        hinst = w.GetModuleHandleW(None)
        wc = w.WNDCLASSEXW(cbSize=ctypes.sizeof(w.WNDCLASSEXW), lpfnWndProc=self._wndproc,
                           hInstance=hinst, lpszClassName="KeyboardLayoutSwitcherWnd")
        w.RegisterClassExW(ctypes.byref(wc))
        self.hwnd = w.CreateWindowExW(0, wc.lpszClassName, config.APP_NAME, 0, 0, 0, 0, 0,
                                      None, None, hinst, None)
        self.clip = Clipboard(self.hwnd)

        self._update_icon()
        self._tray(w.NIM_ADD)
        if not self._register_hotkey():
            self.notify("Не вдалося зареєструвати гарячу клавішу «%s». Змініть її в налаштуваннях."
                        % self.cfg.hotkey, warning=True)

    # ---------- трей ----------

    def _tooltip(self):
        tip = "Keyboard Layout Switcher — " + self.cfg.hotkey
        if not self.cfg.enabled:
            tip += " (вимкнено)"
        elif not self.hotkey_ok:
            tip += " (клавіша зайнята)"
        return tip[:127]

    def _tray(self, action, info=None, warning=False):
        nid = w.NOTIFYICONDATAW(cbSize=ctypes.sizeof(w.NOTIFYICONDATAW), hWnd=self.hwnd, uID=1)
        if action != w.NIM_DELETE:
            nid.uFlags = w.NIF_MESSAGE | w.NIF_ICON | w.NIF_TIP
            nid.uCallbackMessage = WM_TRAY
            nid.hIcon = self.hicon
            nid.szTip = self._tooltip()
            if info:
                nid.uFlags |= w.NIF_INFO
                nid.szInfo = info[:255]
                nid.szInfoTitle = "Keyboard Layout Switcher"
                nid.dwInfoFlags = w.NIIF_WARNING if warning else w.NIIF_INFO
        w.Shell_NotifyIconW(action, ctypes.byref(nid))

    def _update_icon(self):
        old = self.hicon
        size = w.GetSystemMetrics(w.SM_CXSMICON) or 16
        self.hicon = icon.create_hicon(size, icon.tray_color(self.cfg.enabled))
        if old:
            self._tray(w.NIM_MODIFY)
            w.DestroyIcon(old)

    def refresh_tray(self):
        self._update_icon()
        self._tray(w.NIM_MODIFY)

    def notify(self, text, warning=False):
        self._tray(w.NIM_MODIFY, info=text, warning=warning)

    def show_menu(self):
        m = w.CreatePopupMenu()
        w.AppendMenuW(m, w.MF_STRING | w.MF_GRAYED, 0, "Гаряча клавіша: " + self.cfg.hotkey)
        w.AppendMenuW(m, w.MF_SEPARATOR, 0, None)
        w.AppendMenuW(m, w.MF_STRING | (w.MF_CHECKED if self.cfg.enabled else 0), ID_ENABLED, "Увімкнено")
        w.AppendMenuW(m, w.MF_STRING, ID_SETTINGS, "Налаштування…")
        w.AppendMenuW(m, w.MF_STRING, ID_OPEN_INI, "Відкрити config.ini")
        w.AppendMenuW(m, w.MF_STRING, ID_RELOAD, "Перечитати config.ini")
        w.AppendMenuW(m, w.MF_SEPARATOR, 0, None)
        w.AppendMenuW(m, w.MF_STRING, ID_EXIT, "Вихід")
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
        elif cmd == ID_SETTINGS:
            self.open_settings()
        elif cmd == ID_OPEN_INI:
            os.startfile(config.CONFIG_PATH)
        elif cmd == ID_RELOAD:
            self.reload_config()
        elif cmd == ID_EXIT:
            self.exit()

    # ---------- гаряча клавіша ----------

    def _register_hotkey(self):
        w.UnregisterHotKey(self.hwnd, HOTKEY_ID)
        try:
            mods, vk = hk.parse(self.cfg.hotkey)
            self.hotkey_ok = bool(w.RegisterHotKey(self.hwnd, HOTKEY_ID, mods | hk.MOD_NOREPEAT, vk))
        except ValueError as e:
            log.warning("bad hotkey %r: %s", self.cfg.hotkey, e)
            self.hotkey_ok = False
        self.refresh_tray()
        return self.hotkey_ok

    def reload_config(self):
        self.cfg = config.Config.load()
        if not self._register_hotkey():
            self.notify("Не вдалося зареєструвати гарячу клавішу «%s»." % self.cfg.hotkey, warning=True)
        self.refresh_tray()

    # ---------- налаштування ----------

    def open_settings(self):
        if self.settings_root is not None:
            self.settings_root.deiconify()
            self.settings_root.lift()
            self.settings_root.focus_force()
            return
        import settings_ui
        w.UnregisterHotKey(self.hwnd, HOTKEY_ID)  # щоб комбінацію можна було «зловити» у полі
        try:
            settings_ui.run(self)
        finally:
            self.settings_root = None
            if not self._register_hotkey():
                self.notify("Не вдалося зареєструвати гарячу клавішу «%s»." % self.cfg.hotkey, warning=True)
            if self.exit_pending:
                w.DestroyWindow(self.hwnd)

    def apply_settings(self, values, autostart):
        """Викликається з вікна налаштувань. Повертає текст помилки або None."""
        try:
            mods, vk = hk.parse(values["hotkey"])
        except ValueError as e:
            return "Некоректна гаряча клавіша: %s" % e
        if not w.RegisterHotKey(self.hwnd, HOTKEY_ID, mods | hk.MOD_NOREPEAT, vk):
            return ("Комбінацію «%s» не вдалося зареєструвати — можливо, її вже використовує "
                    "інша програма або система." % values["hotkey"])
        w.UnregisterHotKey(self.hwnd, HOTKEY_ID)  # остаточно зареєструється після закриття вікна
        for key, value in values.items():
            setattr(self.cfg, key, value)
        self.cfg.save()
        try:
            config.set_autostart(autostart)
        except OSError as e:
            return "Не вдалося змінити автозапуск: %s" % e
        self.refresh_tray()
        return None

    def exit(self):
        if self.settings_root is not None:
            self.exit_pending = True
            self.settings_root.after(0, self.settings_root.destroy)
        else:
            w.DestroyWindow(self.hwnd)

    # ---------- конвертація ----------

    def on_hotkey(self):
        if self.busy or not self.cfg.enabled:
            return
        self.busy = True
        try:
            self._convert()
        except Exception:
            log.exception("conversion failed")
        finally:
            self.busy = False

    def _convert(self):
        fg = w.GetForegroundWindow()
        if not fg or fg == self.hwnd:
            return
        kio.neutralize_alt_win()
        if not kio.wait_modifiers_released(3.0):
            return
        hkls = layouts.installed()
        if len(hkls) < 2:
            w.MessageBeep(0)
            return
        current = layouts.current(w.GetWindowThreadProcessId(fg, None))
        timeout = self.cfg.copy_timeout_ms / 1000.0

        snapshot = self.clip.snapshot()
        pasted = False
        try:
            text = self.clip.copy_from(kio.copy, timeout)
            log.debug("hotkey: fg=%#x layout=%#x selection=%r", fg, current, text)
            if text and not _is_line_copy(text):
                dst, pasted = self._convert_selection(text, hkls, current)
            else:
                dst = self._convert_last_word(hkls, current, timeout)
        finally:
            if pasted:
                w.sleep_pumping(_PASTE_SETTLE)
            self.clip.restore(snapshot)
        if dst and self.cfg.switch_layout:
            layouts.switch(fg, dst)

    def _convert_selection(self, text, hkls, current):
        src = layouts.detect_source(text, hkls, current)
        dst = layouts.next_after(src, hkls)
        conv = layouts.convert(text, src, dst)
        pasted = False
        if conv != text:
            if "\n" in conv or len(conv) > _PASTE_THRESHOLD:
                self.clip.set_text(conv)
                kio.paste()
                pasted = True
            else:
                kio.type_text(conv)
            n = kio.caret_len(conv)
            if self.cfg.reselect and n <= _MAX_RESELECT:
                kio.press(kio.VK_LEFT, (kio.VK_SHIFT,), n)
        return dst, pasted

    def _convert_last_word(self, hkls, current, timeout):
        # Розширюємо виділення вліво, доки не впремося в пробіл/початок поля.
        # Ctrl+Shift+Left зупиняється на розділових знаках, а в іншій розкладці
        # це можуть бути літери (б, ю, ж, х, ї, є), тож кроків може бути кілька.
        selected = None
        for _ in range(_MAX_WORD_STEPS):
            t = self.clip.copy_from(kio.select_word_left_and_copy, timeout)
            log.debug("word step: %r", t)
            if not t or t == selected:
                break
            selected = t
            if _WS.search(selected.rstrip()):
                break
        if not selected:
            return None

        core = selected.rstrip()
        suffix = selected[len(core):]
        spaces = list(_WS.finditer(core))
        prefix = core[:spaces[-1].end()] if spaces else ""
        word = core[len(prefix):]
        if not word or "\n" in suffix:
            # Нічого конвертувати — повертаємо курсор на місце, знімаючи виділення.
            kio.press(kio.VK_RIGHT, (kio.VK_SHIFT,), kio.caret_len(selected))
            return None

        src = layouts.detect_source(word, hkls, current)
        dst = layouts.next_after(src, hkls)
        conv = layouts.convert(word, src, dst)
        # Активний кінець виділення зліва: зсуваємо його вправо за префікс,
        # лишаючи виділеними тільки слово + пробіли після нього, і передруковуємо їх.
        kio.press(kio.VK_RIGHT, (kio.VK_SHIFT,), kio.caret_len(prefix))
        if conv != word:
            kio.type_text(conv + suffix)
        else:
            kio.press(kio.VK_RIGHT, (kio.VK_SHIFT,), kio.caret_len(word + suffix))
        return dst

    # ---------- цикл повідомлень ----------

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == w.WM_HOTKEY and wparam == HOTKEY_ID:
                self.on_hotkey()
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
            elif msg == w.WM_DESTROY:
                self._tray(w.NIM_DELETE)
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
        w.MessageBoxW(None, "Keyboard Layout Switcher вже запущено (дивіться трей).",
                      "Keyboard Layout Switcher", 0x40)
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App().run()
    del mutex


if __name__ == "__main__":
    main()
