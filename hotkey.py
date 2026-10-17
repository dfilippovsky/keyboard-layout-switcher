"""Розбір і форматування рядків гарячих клавіш на кшталт "Ctrl+Shift+Pause"."""
import re

import winapi as w

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000

_MOD_ORDER = ((MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_SHIFT, "Shift"), (MOD_WIN, "Win"))
_MOD_ALIASES = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT,
                "shift": MOD_SHIFT, "win": MOD_WIN, "windows": MOD_WIN}

KEY_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x13: "Pause", 0x14: "CapsLock",
    0x1B: "Esc", 0x20: "Space", 0x21: "PageUp", 0x22: "PageDown", 0x23: "End",
    0x24: "Home", 0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0x2C: "PrintScreen", 0x2D: "Insert", 0x2E: "Delete", 0x5D: "Apps", 0x91: "ScrollLock",
    0x6A: "NumMul", 0x6B: "NumPlus", 0x6D: "NumMinus", 0x6E: "NumDecimal", 0x6F: "NumDiv",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`",
    0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'", 0xE2: "OEM102",
}
KEY_NAMES.update({ord(c): c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"})
KEY_NAMES.update({0x60 + i: "Num%d" % i for i in range(10)})
KEY_NAMES.update({0x70 + i: "F%d" % (i + 1) for i in range(24)})

_BY_NAME = {v.lower(): k for k, v in KEY_NAMES.items()}
_BY_NAME.update({"break": 0x13, "escape": 0x1B, "return": 0x0D, "del": 0x2E, "ins": 0x2D,
                 "pgup": 0x21, "pgdn": 0x22, "menu": 0x5D})


def parse(text):
    """'Ctrl+Shift+F12' -> (mods, vk). Кидає ValueError для некоректного рядка."""
    parts = [p.strip() for p in text.split("+")]
    if not parts or any(not p for p in parts):
        raise ValueError("порожня частина в «%s»" % text)
    *mod_parts, key = parts
    mods = 0
    for p in mod_parts:
        if p.lower() not in _MOD_ALIASES:
            raise ValueError("невідомий модифікатор «%s»" % p)
        mods |= _MOD_ALIASES[p.lower()]
    k = key.lower()
    if k in _BY_NAME:
        return mods, _BY_NAME[k]
    m = re.fullmatch(r"vk([0-9a-f]{2})", k)
    if m:
        return mods, int(m.group(1), 16)
    raise ValueError("невідома клавіша «%s»" % key)


def format(mods, vk):
    parts = [n for m, n in _MOD_ORDER if mods & m]
    parts.append(KEY_NAMES.get(vk, "VK%02X" % vk) if vk else "")
    return "+".join(parts)


def current_mods():
    down = lambda *vks: any(w.GetAsyncKeyState(v) & 0x8000 for v in vks)
    mods = 0
    if down(0x11):
        mods |= MOD_CONTROL
    if down(0x12):
        mods |= MOD_ALT
    if down(0x10):
        mods |= MOD_SHIFT
    if down(0x5B, 0x5C):
        mods |= MOD_WIN
    return mods
