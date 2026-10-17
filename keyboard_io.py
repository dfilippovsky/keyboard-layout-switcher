"""Емуляція натискань клавіш через SendInput."""
import ctypes
import struct
import time

import winapi as w

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

# Клавіші, які треба надсилати з прапорцем «extended» (стрілки, Home/End тощо)
_EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5C, 0x5D, 0x6F, 0x90}

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
