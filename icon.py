"""Іконка «languages» з Lucide (https://lucide.dev/icons/languages, ISC).

SVG складається лише з відрізків, тож растеризуємо їх самі (з антиаліасингом,
круглими кінцями й з'єднаннями) — без Pillow та файлів ресурсів.
"""
import ctypes
import math
import struct
import winreg
import zlib

import winapi as w

# Відрізки шляхів у viewBox 0..24 (stroke-width 2, round caps/joins)
SEGMENTS = (
    ((5, 8), (11, 14)),                      # m5 8 6 6
    ((4, 14), (10, 8)), ((10, 8), (12, 5)),  # m4 14 6-6 2-3
    ((2, 5), (14, 5)),                       # M2 5h12
    ((7, 2), (8, 2)),                        # M7 2h1
    ((22, 22), (17, 12)), ((17, 12), (12, 22)),  # m22 22-5-10-5 10
    ((14, 18), (20, 18)),                    # M14 18h6
)

APP_ICON_COLOR = (0x25, 0x63, 0xEB)


def _dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    l2 = vx * vx + vy * vy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / l2))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def _alpha(size):
    scale = size / 24.0
    half = max(scale, 0.8)  # половина stroke-width=2, не тонше ~1.6 px
    segs = [(ax * scale, ay * scale, bx * scale, by * scale) for (ax, ay), (bx, by) in SEGMENTS]
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            d = min(_dist(x + 0.5, y + 0.5, *s) for s in segs)
            row.append(int(round(max(0.0, min(1.0, half + 0.5 - d)) * 255)))
        rows.append(row)
    return rows


def dib(size, rgb):
    """Зображення іконки у форматі ресурсу: BITMAPINFOHEADER + BGRA + AND-маска."""
    r, g, b = rgb
    mask = bytes(((size + 31) // 32) * 4 * size)
    pixels = bytearray()
    for row in reversed(_alpha(size)):  # DIB зберігається знизу вгору
        for a in row:
            pixels += bytes((b, g, r, a))
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(pixels) + len(mask), 0, 0, 0, 0)
    return header + bytes(pixels) + mask


def png_bytes(size, rgb):
    """PNG (RGBA) — для іконки вікна Tk."""
    r, g, b = rgb
    raw = b"".join(b"\0" + b"".join(bytes((r, g, b, a)) for a in row) for row in _alpha(size))
    chunk = lambda tag, data: (struct.pack(">I", len(data)) + tag + data +
                               struct.pack(">I", zlib.crc32(tag + data)))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def ico_bytes(sizes=(16, 20, 24, 32, 40, 48, 64, 128, 256), rgb=APP_ICON_COLOR):
    images = [dib(s, rgb) for s in sizes]
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for s, img in zip(sizes, images):
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(img), offset)
        offset += len(img)
    return out + b"".join(images)


def write_ico(path):
    with open(path, "wb") as f:
        f.write(ico_bytes())


def create_hicon(size, rgb):
    data = dib(size, rgb)
    buf = ctypes.create_string_buffer(data, len(data))
    return w.CreateIconFromResourceEx(buf, len(data), True, 0x00030000, size, size, 0)


def taskbar_is_light():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return bool(winreg.QueryValueEx(k, "SystemUsesLightTheme")[0])
    except OSError:
        return False


def tray_color(enabled):
    if not enabled:
        return (0x80, 0x80, 0x80)
    return (0x1F, 0x1F, 0x1F) if taskbar_is_light() else (0xFF, 0xFF, 0xFF)
