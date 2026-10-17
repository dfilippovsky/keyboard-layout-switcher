"""Розкладки клавіатури: таблиці символів і конвертація тексту між розкладками.

Таблиці будуються через ToUnicodeEx для кожної встановленої розкладки,
тож підтримується будь-яка комбінація (EN/UK/RU/DE/...), а не лише зашита.
"""
import ctypes
from ctypes import wintypes as W

import winapi as w

# Клавіші, що друкують символи: цифри, літери, OEM-клавіші (;=,-./`[\]' та <> на ISO)
_TYPING_VKS = (list(range(0x30, 0x3A)) + list(range(0x41, 0x5B)) +
               list(range(0xBA, 0xC1)) + list(range(0xDB, 0xE0)) + [0xE2])
# Стани модифікаторів: (Shift, AltGr). Порядок = пріоритет при неоднозначності.
_STATES = ((False, False), (True, False), (False, True), (True, True))
_TOUNICODE_NO_STATE_CHANGE = 0x4

_cache = {}


class KeyMap:
    def __init__(self, hkl):
        self.hkl = hkl
        self.key_to_char = {}
        self.char_to_key = {}
        state = (ctypes.c_ubyte * 256)()
        buf = ctypes.create_unicode_buffer(8)
        for si, (shift, altgr) in enumerate(_STATES):
            ctypes.memset(state, 0, 256)
            if shift:
                state[0x10] = state[0xA0] = 0x80
            if altgr:
                state[0x11] = state[0xA2] = state[0x12] = state[0xA5] = 0x80
            for vk in _TYPING_VKS:
                scan = w.MapVirtualKeyExW(vk, 0, hkl)
                rc = w.ToUnicodeEx(vk, scan, state, buf, 8, _TOUNICODE_NO_STATE_CHANGE, hkl)
                if rc < 0:
                    _flush_dead_key(hkl, buf)
                    continue
                if rc != 1 or buf[0] < " ":
                    continue
                key = (vk, si)
                self.key_to_char[key] = buf[0]
                self.char_to_key.setdefault(buf[0], key)


def _flush_dead_key(hkl, buf):
    empty = (ctypes.c_ubyte * 256)()
    scan = w.MapVirtualKeyExW(0x20, 0, hkl)
    for _ in range(4):
        if w.ToUnicodeEx(0x20, scan, empty, buf, 8, _TOUNICODE_NO_STATE_CHANGE, hkl) >= 0:
            break


def keymap(hkl):
    km = _cache.get(hkl)
    if km is None:
        km = _cache[hkl] = KeyMap(hkl)
    return km


def installed():
    n = w.GetKeyboardLayoutList(0, None)
    arr = (W.HKL * n)()
    n = w.GetKeyboardLayoutList(n, arr)
    return [arr[i] or 0 for i in range(n)]


def current(thread_id):
    return w.GetKeyboardLayout(thread_id) or 0


def name(hkl):
    buf = ctypes.create_unicode_buffer(85)
    if w.LCIDToLocaleName(hkl & 0xFFFF, buf, 85, 0):
        return buf.value.split("-")[0].upper()
    return "%08X" % (hkl & 0xFFFFFFFF)


def detect_source(text, hkls, cur):
    """Розкладка, в якій найімовірніше набрано текст (за кількістю «своїх» символів)."""
    order = [cur] + [h for h in hkls if h != cur] if cur in hkls else list(hkls)
    best, best_score = order[0], -1
    for hkl in order:
        chars = keymap(hkl).char_to_key
        score = sum(1 for ch in text if not ch.isspace() and ch in chars)
        if score > best_score:
            best, best_score = hkl, score
    return best


def next_after(hkl, hkls):
    i = hkls.index(hkl) if hkl in hkls else -1
    return hkls[(i + 1) % len(hkls)]


def convert(text, src, dst):
    s, d = keymap(src), keymap(dst)
    out = []
    for ch in text:
        key = s.char_to_key.get(ch)
        out.append(d.key_to_char.get(key, ch) if key else ch)
    return "".join(out)


def switch(hwnd, hkl):
    """Попросити вікно перейти на розкладку hkl."""
    if hkl >= 1 << 63:  # LPARAM знаковий
        hkl -= 1 << 64
    w.PostMessageW(hwnd, w.WM_INPUTLANGCHANGEREQUEST, 0, hkl)
