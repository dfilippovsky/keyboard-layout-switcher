"""Емуляція натискань клавіш через SendInput."""
import ctypes
import logging
import struct
import time
from ctypes import wintypes as W

import winapi as w

log = logging.getLogger("kls")

VK_BACK = 0x08
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_C = 0x43
VK_V = 0x56
VK_UNASSIGNED = 0xE8  # «порожня» клавіша, щоб Alt/Win не активували меню

MODIFIER_VKS = (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN)
# Ліві/праві модифікатори окремо: LShift, RShift, LCtrl, RCtrl, LAlt, RAlt, LWin, RWin
SIDED_MODIFIER_VKS = (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, VK_LWIN, VK_RWIN)
_MENU_KEYS = {0xA4, 0xA5, VK_LWIN, VK_RWIN}  # відпускання «самотніх» Alt/Win відкриває меню/Пуск

# Клавіші, які треба надсилати з прапорцем «extended» (стрілки, Home/End, правий Ctrl/Alt тощо)
_EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5C, 0x5D, 0x6F, 0x90,
             0xA3, 0xA5}

_INPUT_KEYBOARD = 1
_KEYEVENTF_EXTENDEDKEY = 0x0001
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004
_CHUNK = 200


def _input(vk=0, scan=0, flags=0):
    inp = w.INPUT(type=_INPUT_KEYBOARD)
    inp.u.ki = w.KEYBDINPUT(vk, scan, flags, 0, 0)
    return inp


def _key(vk, up=False):
    flags = _KEYEVENTF_KEYUP if up else 0
    if vk in _EXTENDED:
        flags |= _KEYEVENTF_EXTENDEDKEY
    return _input(vk, w.MapVirtualKeyExW(vk, 0, None) & 0xFF, flags)


def _send(inputs):
    for i in range(0, len(inputs), _CHUNK):
        part = inputs[i:i + _CHUNK]
        arr = (w.INPUT * len(part))(*part)
        w.SendInput(len(part), arr, ctypes.sizeof(w.INPUT))


def press(vk, mods=(), times=1):
    """Натиснути клавішу `times` разів, утримуючи модифікатори `mods`."""
    if times <= 0:
        return
    seq = [_key(m) for m in mods]
    for _ in range(times):
        seq += [_key(vk), _key(vk, True)]
    seq += [_key(m, True) for m in reversed(mods)]
    _send(seq)


def copy():
    press(VK_C, (VK_CONTROL,))


def paste():
    press(VK_V, (VK_CONTROL,))


def extend_left_and_copy():
    press(VK_LEFT, (VK_SHIFT,))
    copy()


def extend_right_and_copy():
    press(VK_RIGHT, (VK_SHIFT,))
    copy()


def select_word_left_and_copy():
    press(VK_LEFT, (VK_CONTROL, VK_SHIFT))
    copy()


def type_text(text):
    """Надрукувати текст юнікод-подіями (не залежить від поточної розкладки)."""
    seq = []
    for ch in text.replace("\r\n", "\n"):
        if ch == "\n":
            seq += [_key(VK_RETURN), _key(VK_RETURN, True)]
            continue
        data = ch.encode("utf-16-le")
        for unit in struct.unpack("<%dH" % (len(data) // 2), data):
            seq.append(_input(0, unit, _KEYEVENTF_UNICODE))
            seq.append(_input(0, unit, _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP))
    _send(seq)


def caret_len(text):
    """Скільки позицій курсора займає текст (CRLF — одна позиція)."""
    return len(text.replace("\r\n", "\n"))


def is_down(vk):
    return bool(w.GetAsyncKeyState(vk) & 0x8000)


def neutralize_alt_win():
    """Якщо утримуються Alt/Win — «використати» їх, щоб відпускання не відкрило меню/Пуск."""
    if is_down(VK_MENU) or is_down(VK_LWIN) or is_down(VK_RWIN):
        _send([_key(VK_UNASSIGNED), _key(VK_UNASSIGNED, True)])


def wait_modifiers_released(timeout):
    end = time.monotonic() + timeout
    while any(is_down(vk) for vk in MODIFIER_VKS):
        if time.monotonic() > end:
            return False
        w.sleep_pumping(0.01)
    return True


def release_modifiers():
    """Логічно відпустити утримувані модифікатори (фізично їх можуть і далі тримати),
    щоб наші Ctrl+C і друк не змішалися з ними. Повертає відпущені клавіші."""
    held = [vk for vk in SIDED_MODIFIER_VKS if is_down(vk)]
    neutralize_alt_win()
    _send([_key(vk, True) for vk in held])
    return held


def press_modifiers(vks):
    """Повернути логічний стан модифікаторів, які фізично досі утримуються."""
    if not vks:
        return
    seq = [_key(vk) for vk in vks]
    if _MENU_KEYS.intersection(vks):  # щоб їх відпускання потім не відкрило меню/Пуск
        seq += [_key(VK_UNASSIGNED), _key(VK_UNASSIGNED, True)]
    _send(seq)


def _sided(vk, make_code, flags):
    """Raw Input дає загальні VK_SHIFT/CONTROL/MENU — уточнюємо лівий/правий."""
    if vk == VK_SHIFT:
        return 0xA1 if make_code == 0x36 else 0xA0
    if vk == VK_CONTROL:
        return 0xA3 if flags & w.RI_KEY_E0 else 0xA2
    if vk == VK_MENU:
        return 0xA5 if flags & w.RI_KEY_E0 else 0xA4
    return vk


class PhysicalKeys:
    """Фізичний стан модифікаторів через Raw Input (без хуків): події, надіслані через
    SendInput (hDevice = 0), ігноруються, тож видно, що користувач реально тримає,
    навіть коли ми логічно відпустили модифікатори."""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self._register(w.RIDEV_INPUTSINK, hwnd)
        # Знімок після реєстрації: усе, що зміниться далі, прийде подіями
        self.down = {vk for vk in SIDED_MODIFIER_VKS if is_down(vk)}
        self._events = []  # (MSG.time, vk, натиснуто) — прочитані, але ще не застосовані
        log.debug("raw input on, modifiers down: %s", sorted(self.down))

    @staticmethod
    def _register(flags, hwnd):
        dev = w.RAWINPUTDEVICE(0x01, 0x06, flags, hwnd)  # Generic Desktop / Keyboard
        if not w.RegisterRawInputDevices(ctypes.byref(dev), 1, ctypes.sizeof(dev)):
            raise OSError(ctypes.get_last_error(), "RegisterRawInputDevices failed")

    def close(self):
        self._register(w.RIDEV_REMOVE, None)

    def held(self, groups):
        """groups: [(лівий, правий), ...] — чи утримується зараз хоча б одна клавіша з кожної групи."""
        down = self.at(None)
        return all(down.intersection(g) for g in groups)

    def at(self, t):
        """Модифікатори, фізично утримувані на момент t (MSG.time, мс; None — зараз).
        Застосовує прочитані події не пізніші за t, тож викликати з неспадним t."""
        while self._events and (t is None or (t - self._events[0][0]) & 0xFFFFFFFF < 0x80000000):
            _, vk, pressed = self._events.pop(0)
            if pressed:
                self.down.add(vk)
            else:
                self.down.discard(vk)
        return self.down

    def poll(self):
        """Прочитати накопичені події Raw Input (застосовуються в at())."""
        msg = w.MSG()
        buf = (ctypes.c_byte * 64)()  # з запасом: RAWINPUT більший за заголовок + RAWKEYBOARD
        rec = w.RAWINPUT_KEYBOARD.from_buffer(buf)
        size = W.UINT()
        while w.PeekMessageW(ctypes.byref(msg), self.hwnd, w.WM_INPUT, w.WM_INPUT, w.PM_REMOVE):
            size.value = ctypes.sizeof(buf)
            got = w.GetRawInputData(msg.lParam, w.RID_INPUT, buf, ctypes.byref(size),
                                    ctypes.sizeof(w.RAWINPUTHEADER))
            w.DefWindowProcW(self.hwnd, w.WM_INPUT, msg.wParam, msg.lParam)
            if got in (0, 0xFFFFFFFF) or rec.header.dwType != w.RIM_TYPEKEYBOARD:
                log.debug("raw input: unreadable event (%d)", got)
                continue
            kb = rec.keyboard
            vk = _sided(kb.VKey, kb.MakeCode, kb.Flags)
            log.debug("raw input: vk=%#x make=%#x flags=%#x device=%s", kb.VKey, kb.MakeCode, kb.Flags,
                      rec.header.hDevice)
            if not rec.header.hDevice or vk not in SIDED_MODIFIER_VKS:
                continue  # наші SendInput або не модифікатор
            self._events.append((msg.time, vk, not kb.Flags & w.RI_KEY_BREAK))
