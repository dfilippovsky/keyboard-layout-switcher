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

import config
import eyecare
import hotkey as hk
import icon
import keyboard_io as kio
import layouts
import textcase
import translit
import winapi as w
from clipboard import Clipboard

log = logging.getLogger("kls")

# Дії за гарячими клавішами: id -> поле config
HOTKEY_LAYOUT, HOTKEY_CASE, HOTKEY_TRANSLIT = 1, 2, 3
_HOTKEY_FIELDS = dict(zip((HOTKEY_LAYOUT, HOTKEY_CASE, HOTKEY_TRANSLIT), config.HOTKEY_FIELDS))
_HOTKEY_LABELS = {HOTKEY_LAYOUT: "Розкладка", HOTKEY_CASE: "Регістр", HOTKEY_TRANSLIT: "Транслітерація"}
_HOTKEY_ALIAS = 10       # id + 10 — додатковий код тієї ж комбінації (Ctrl+Pause = VK_CANCEL)
_FLASH_COLORS = {HOTKEY_LAYOUT: icon.FLASH_COLOR, HOTKEY_CASE: icon.CASE_FLASH_COLOR,
                 HOTKEY_TRANSLIT: icon.TRANSLIT_FLASH_COLOR}
FLASH_TIMER_ID = 1
EYE_TIMER_ID = 2
EYE_HIDE_TIMER_ID = 3
_SWALLOW_ID = 50       # тимчасові «голі» клавіші під час утримання модифікатора
_HOLD_TIMEOUT = 10.0   # с без натискань — завершити утримання
_FLASH_MS = 350          # скільки іконка в треї світиться кольором дії після обробки гарячої клавіші
WM_TRAY = w.WM_APP + 1
ID_ENABLED, ID_SETTINGS, ID_OPEN_INI, ID_RELOAD, ID_EXIT, ID_EYES = range(100, 106)
_WS = re.compile(r"\s")
_MAX_WORD_STEPS = 8      # скільки разів Ctrl+Shift+Left шукати початок слова
_MAX_RESELECT = 5000     # не виділяти назад надто довгий текст
_PASTE_THRESHOLD = 300   # довший або багаторядковий текст вставляємо через буфер
_PASTE_SETTLE = 0.3      # дати програмі прочитати буфер перед відновленням


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
        self.busy = False
        self.hotkey_ok = False
        self.registered = {}     # дія -> (mods, vk) — лише комбінації, що справді зареєстровані
        self.settings_root = None
        self.exit_pending = False
        self.hicon = None
        self.flash_icons = {}
        self.flashing = None     # id дії, кольором якої зараз світиться іконка
        self.case_cycler = textcase.CaseCycler()
        self.eyes = eyecare.EyeBreaks()
        self.eye_icon = None

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
        self._warn_failed(self._register_hotkeys())
        w.SetTimer(self.hwnd, EYE_TIMER_ID, eyecare.TICK_MS, None)

    # ---------- трей ----------

    def _tooltip(self):
        tip = "Keyboard Layout Switcher — " + self.cfg.hotkey
        if not self.cfg.enabled:
            tip += " (вимкнено)"
        elif not self.hotkey_ok:
            tip += " (клавіша зайнята)"
        return tip[:127]

    def _tray(self, action, info=None, warning=False, title=None, quiet=False, balloon_icon=None):
        nid = w.NOTIFYICONDATAW(cbSize=ctypes.sizeof(w.NOTIFYICONDATAW), hWnd=self.hwnd, uID=1)
        if action != w.NIM_DELETE:
            nid.uFlags = w.NIF_MESSAGE | w.NIF_ICON | w.NIF_TIP
            nid.uCallbackMessage = WM_TRAY
            nid.hIcon = self.flash_icons[self.flashing] if self.flashing else self.hicon
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
        self.flash_icons = {a: icon.create_hicon(size, c) for a, c in _FLASH_COLORS.items()}
        if old[0]:
            self._tray(w.NIM_MODIFY)
            for h in old:
                w.DestroyIcon(h)

    def flash(self, action):
        """Коротко підсвітити іконку в треї кольором дії."""
        self.flashing = action
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
        m = w.CreatePopupMenu()
        for action, field in _HOTKEY_FIELDS.items():
            w.AppendMenuW(m, w.MF_STRING | w.MF_GRAYED, 0, "%s: %s" % (
                _HOTKEY_LABELS[action], getattr(self.cfg, field) or "вимкнено"))
        w.AppendMenuW(m, w.MF_SEPARATOR, 0, None)
        w.AppendMenuW(m, w.MF_STRING | (w.MF_CHECKED if self.cfg.enabled else 0), ID_ENABLED, "Увімкнено")
        w.AppendMenuW(m, w.MF_STRING | (w.MF_CHECKED if self.cfg.eye_breaks else 0), ID_EYES,
                      "Нагадування 20-20-20 для очей")
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
        elif cmd == ID_EYES:
            self.cfg.eye_breaks = not self.cfg.eye_breaks
            self.cfg.save()
            self.eyes.reset()
        elif cmd == ID_SETTINGS:
            self.open_settings()
        elif cmd == ID_OPEN_INI:
            os.startfile(config.CONFIG_PATH)
        elif cmd == ID_RELOAD:
            self.reload_config()
        elif cmd == ID_EXIT:
            self.exit()

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
        for action in _HOTKEY_FIELDS:
            for i in range(2):
                w.UnregisterHotKey(self.hwnd, action + i * _HOTKEY_ALIAS)

    def _register_hotkeys(self):
        """Повертає список комбінацій, які не вдалося зареєструвати."""
        self._unregister_hotkeys()
        failed = []
        self.hotkey_ok = True
        for action, field in _HOTKEY_FIELDS.items():
            text = getattr(self.cfg, field)
            if not text:
                continue
            if self._register(action, text):
                self.registered[action] = hk.parse(text)
            else:
                failed.append(text)
                if action == HOTKEY_LAYOUT:
                    self.hotkey_ok = False
        self.refresh_tray()
        return failed

    def _warn_failed(self, failed):
        if failed:
            self.notify("Не вдалося зареєструвати: %s. Змініть комбінації в налаштуваннях."
                        % ", ".join("«%s»" % t for t in failed), warning=True)

    def reload_config(self):
        self.cfg = config.Config.load()
        self._warn_failed(self._register_hotkeys())

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
                return "Не вдалося змінити автозапуск: %s" % e
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
            return "Не вдалося зберегти %s: %s" % (config.CONFIG_PATH, e)
        self.eyes.reset()
        self.refresh_tray()
        return None

    def _check_hotkeys(self, values):
        """Перевірити комбінації з вікна налаштувань пробною реєстрацією.
        Остаточно вони зареєструються після закриття вікна."""
        seen = set()
        try:
            for action, field in _HOTKEY_FIELDS.items():
                text = values[field]
                if not text:
                    continue
                try:
                    mods, vk = hk.parse(text)
                except ValueError as e:
                    return "Некоректна гаряча клавіша «%s»: %s" % (text, e)
                key = (mods, hk.normalize_vk(vk))
                if key in seen:
                    return "Комбінацію «%s» призначено двом діям." % text
                seen.add(key)
                if not self._register(action, text):
                    return ("Комбінацію «%s» не вдалося зареєструвати — можливо, її вже використовує "
                            "інша програма або система." % text)
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

    def on_hotkey(self, action):
        if self.busy or not self.cfg.enabled:
            return
        fg = w.GetForegroundWindow()
        if not fg or fg == self.hwnd:
            return
        self.busy = True
        try:
            self._run_action(action, fg)
        except Exception:
            log.exception("hotkey action %d failed", action)
        finally:
            self.busy = False
            # Після обробки: потік одразу повертається до циклу повідомлень,
            # тож WM_TIMER прийде вчасно й іконка світиться рівно _FLASH_MS.
            self.flash(action)

    def _run_action(self, action, fg):
        step = {HOTKEY_LAYOUT: self._convert_layout, HOTKEY_CASE: self._toggle_case,
                HOTKEY_TRANSLIT: self._transliterate}[action]
        if action not in self.registered:
            return  # комбінація цієї дії не зареєстрована (невалідна чи зайнята)
        mods, vk = self.registered[action]
        groups = hk.modifier_groups(mods)
        keys = None
        if groups:
            try:
                keys = kio.PhysicalKeys(self.hwnd)
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
        self.flashing = action
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
        dst = None

        def transform(text):
            nonlocal dst
            src = layouts.detect_source(text, hkls, current)
            dst = layouts.next_after(src, hkls)
            return layouts.convert(text, src, dst)

        if self._edit_text(transform) and dst and self.cfg.switch_layout:
            layouts.switch(fg, dst)

    def _toggle_case(self, _fg):
        self._edit_text(self.case_cycler.next)

    def _transliterate(self, _fg):
        self._edit_text(translit.transliterate)

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

    # ---------- нагадування 20-20-20 ----------

    def _eye_tick(self):
        if not self.cfg.eye_breaks:
            self.eyes.reset()
            return
        if self.eyes.tick(self.cfg.eye_break_minutes):
            self.show_eye_break()

    def show_eye_break(self):
        if not self.eye_icon:  # велика іконка сповіщення — малюється при першому показі
            self.eye_icon = icon.create_eye_break_hicon(w.GetSystemMetrics(w.SM_CXICON) or 32)
        self.notify("Подивіться 20 секунд на щось далеко (≈6 м) - очі відпочинуть.",
                    title="Перерва для очей", quiet=True, balloon_icon=self.eye_icon)
        # Тайм-аут у NOTIFYICONDATA Windows ігнорує, тож закриваємо самі
        if self.cfg.eye_break_popup_seconds:
            w.SetTimer(self.hwnd, EYE_HIDE_TIMER_ID, self.cfg.eye_break_popup_seconds * 1000, None)

    def _hide_eye_break(self):
        w.KillTimer(self.hwnd, EYE_HIDE_TIMER_ID)
        self._tray(w.NIM_MODIFY, info="")

    # ---------- цикл повідомлень ----------

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == w.WM_HOTKEY and wparam % _HOTKEY_ALIAS in _HOTKEY_FIELDS:
                self.on_hotkey(wparam % _HOTKEY_ALIAS)
                return 0
            if msg == w.WM_TIMER and wparam == FLASH_TIMER_ID:
                self._end_flash()
                return 0
            if msg == w.WM_TIMER and wparam == EYE_TIMER_ID:
                self._eye_tick()
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
