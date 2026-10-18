"""Іконки з Lucide (ISC): «languages» (https://lucide.dev/icons/languages) — програма
й трей, «hat-glasses» (https://lucide.dev/icons/hat-glasses) — нагадування для очей,
«weight-tilde» (https://lucide.dev/icons/weight-tilde) — нагадування про перерву.

Растеризуємо самі (з антиаліасингом, круглими кінцями й з'єднаннями) — без Pillow
та файлів ресурсів: шляхи SVG перетворюються на відрізки (дуги й кола — на ламані).
"""
import ctypes
import math
import re
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

# lucide-static 1.59.0, icons/hat-glasses.svg
HAT_GLASSES_PATHS = (
    "M14 18a2 2 0 0 0-4 0",
    "m19 11-2.11-6.657a2 2 0 0 0-2.752-1.148l-1.276.61A2 2 0 0 1 12 4H8.5"
    "a2 2 0 0 0-1.925 1.456L5 11",
    "M2 11h20",
)
HAT_GLASSES_CIRCLES = ((17, 18, 3), (7, 18, 3))

# lucide-static 1.59.0, icons/weight-tilde.svg
WEIGHT_TILDE_PATHS = (
    "M6.5 8a2 2 0 0 0-1.906 1.46L2.1 18.5A2 2 0 0 0 4 21h16a2 2 0 0 0 1.925-2.54L19.4 9.5"
    "A2 2 0 0 0 17.48 8z",
    "M7.999 15a2.5 2.5 0 0 1 4 0 2.5 2.5 0 0 0 4 0",
)
WEIGHT_TILDE_CIRCLES = ((12, 5, 3),)

APP_ICON_COLOR = (0x25, 0x63, 0xEB)
# Коротке підсвічування в треї при спрацюванні гарячої клавіші
FLASH_COLOR = (0x3B, 0x82, 0xF6)           # розкладка — синій
CASE_FLASH_COLOR = (0x22, 0xC5, 0x5E)      # регістр — зелений
TRANSLIT_FLASH_COLOR = (0xA8, 0x55, 0xF7)  # транслітерація — фіолетовий
EYE_BREAK_COLOR = APP_ICON_COLOR           # коло під «hat-glasses» у сповіщенні
WORK_BREAK_COLOR = (0xEA, 0x58, 0x0C)      # коло під «weight-tilde» — помаранчевий

# ---------- SVG -> відрізки ----------

_TOKEN = re.compile(r"[MmLlHhVvAaZz]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "A": 7, "Z": 0}


def _arc_points(x1, y1, rx, ry, phi, large, sweep, x2, y2, steps=12):
    """Точки дуги SVG (параметризація через центр, SVG 1.1 F.6.5), без початкової."""
    if not rx or not ry:
        return [(x2, y2)]
    rx, ry = abs(rx), abs(ry)
    cos, sin = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cos * dx + sin * dy, -sin * dx + cos * dy
    lam = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = (rx * ry) ** 2 - (rx * y1p) ** 2 - (ry * x1p) ** 2
    den = (rx * y1p) ** 2 + (ry * x1p) ** 2
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        co = -co
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx = cos * cxp - sin * cyp + (x1 + x2) / 2
    cy = sin * cxp + cos * cyp + (y1 + y2) / 2
    ux, uy = (x1p - cxp) / rx, (y1p - cyp) / ry
    vx, vy = (-x1p - cxp) / rx, (-y1p - cyp) / ry
    t1 = math.atan2(uy, ux)
    dt = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    pts = []
    for i in range(1, steps + 1):
        t = t1 + dt * i / steps
        ex, ey = rx * math.cos(t), ry * math.sin(t)
        pts.append((cos * ex - sin * ey + cx, sin * ex + cos * ey + cy))
    return pts


def path_segments(d):
    """Відрізки шляху SVG (підтримуються M L H V A Z, абсолютні й відносні)."""
    tokens = _TOKEN.findall(d)
    segs = []
    x = y = sx = sy = 0.0
    i, cmd = 0, None
    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
        elif cmd is None:
            raise ValueError("path must start with a command")
        up, rel = cmd.upper(), cmd.islower()
        if up not in _ARGS:
            raise ValueError("unsupported path command %r" % cmd)
        n = _ARGS[up]
        a = [float(t) for t in tokens[i:i + n]]
        i += n
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if up == "M":
            x, y = sx, sy = a[0] + ox, a[1] + oy
            cmd = "l" if rel else "L"  # наступні пари після M — це лінії
            continue
        if up == "Z":
            pts = [(sx, sy)]
        elif up == "L":
            pts = [(a[0] + ox, a[1] + oy)]
        elif up == "H":
            pts = [(a[0] + ox, y)]
        elif up == "V":
            pts = [(x, a[0] + oy)]
        else:
            pts = _arc_points(x, y, a[0], a[1], a[2], a[3], a[4], a[5] + ox, a[6] + oy)
        for px, py in pts:
            segs.append(((x, y), (px, py)))
            x, y = px, py
    return segs


def circle_segments(cx, cy, r, steps=32):
    pts = [(cx + r * math.cos(2 * math.pi * i / steps), cy + r * math.sin(2 * math.pi * i / steps))
           for i in range(steps + 1)]
    return list(zip(pts, pts[1:]))


# ---------- растеризація ----------

def _dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    l2 = vx * vx + vy * vy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / l2))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def _stroke(size, segments, scale, offset=0.0):
    """Покриття (0..1) обведення відрізків viewBox 24x24, масштабованих на scale і зсунутих."""
    half = max(scale, 0.8)  # половина stroke-width=2, не тонше ~1.6 px
    segs = [(ax * scale + offset, ay * scale + offset, bx * scale + offset, by * scale + offset)
            for (ax, ay), (bx, by) in segments]
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            d = min(_dist(x + 0.5, y + 0.5, *s) for s in segs)
            row.append(max(0.0, min(1.0, half + 0.5 - d)))
        rows.append(row)
    return rows


def _glyph(size, rgb):
    """«languages» одним кольором: рядки пікселів (r, g, b, a) зверху вниз."""
    r, g, b = rgb
    return [[(r, g, b, int(round(c * 255))) for c in row] for row in _stroke(size, SEGMENTS, size / 24.0)]


def _badge(size, paths, circles, rgb):
    """Білий гліф Lucide у колі кольору rgb."""
    inner = size * 0.6  # гліф займає 60% діаметра кола
    segments = [s for p in paths for s in path_segments(p)]
    segments += [s for c in circles for s in circle_segments(*c)]
    glyph = _stroke(size, segments, inner / 24.0, (size - inner) / 2)
    br, bg, bb = rgb
    c = size / 2.0
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            disk = max(0.0, min(1.0, c + 0.5 - math.hypot(x + 0.5 - c, y + 0.5 - c) - 0.5))
            k = glyph[y][x]
            row.append((int(round(br + (255 - br) * k)), int(round(bg + (255 - bg) * k)),
                        int(round(bb + (255 - bb) * k)), int(round(disk * 255))))
        rows.append(row)
    return rows


def _eye_break(size):
    return _badge(size, HAT_GLASSES_PATHS, HAT_GLASSES_CIRCLES, EYE_BREAK_COLOR)


def _work_break(size):
    return _badge(size, WEIGHT_TILDE_PATHS, WEIGHT_TILDE_CIRCLES, WORK_BREAK_COLOR)


def _dib(rows):
    """Зображення іконки у форматі ресурсу: BITMAPINFOHEADER + BGRA + AND-маска."""
    size = len(rows)
    mask = bytes(((size + 31) // 32) * 4 * size)
    pixels = bytearray()
    for row in reversed(rows):  # DIB зберігається знизу вгору
        for r, g, b, a in row:
            pixels += bytes((b, g, r, a))
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(pixels) + len(mask), 0, 0, 0, 0)
    return header + bytes(pixels) + mask


def dib(size, rgb):
    return _dib(_glyph(size, rgb))


def _png(rows):
    size = len(rows)
    raw = b"".join(b"\0" + b"".join(bytes(px) for px in row) for row in rows)
    chunk = lambda tag, data: (struct.pack(">I", len(data)) + tag + data +
                               struct.pack(">I", zlib.crc32(tag + data)))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def png_bytes(size, rgb):
    """PNG (RGBA) — для іконки вікна Tk."""
    return _png(_glyph(size, rgb))


def eye_break_png(size):
    return _png(_eye_break(size))


def work_break_png(size):
    return _png(_work_break(size))


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


def _hicon(data, size):
    buf = ctypes.create_string_buffer(data, len(data))
    return w.CreateIconFromResourceEx(buf, len(data), True, 0x00030000, size, size, 0)


def create_hicon(size, rgb):
    return _hicon(dib(size, rgb), size)


def create_eye_break_hicon(size):
    return _hicon(_dib(_eye_break(size)), size)


def create_work_break_hicon(size):
    return _hicon(_dib(_work_break(size)), size)


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
