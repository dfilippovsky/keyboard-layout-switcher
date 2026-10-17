"""Робота з буфером обміну: збереження/відновлення та копіювання виділеного."""
import ctypes
import logging
import time

import winapi as w

log = logging.getLogger(__name__)

CF_UNICODETEXT = 13
CF_ENHMETAFILE = 14
_GMEM_MOVEABLE = 0x0002
# Формати з GDI-дескрипторами замість HGLOBAL: зберегти байтами їх не можна, але система
# синтезує їх із формату, який ми зберігаємо (CF_BITMAP/CF_PALETTE — з CF_DIB/CF_DIBV5,
# CF_METAFILEPICT — з CF_ENHMETAFILE). Формат вважається збереженим, якщо є його джерело.
_SYNTHESIZED_FROM = {2: (8, 17), 9: (8, 17), 3: (CF_ENHMETAFILE,)}
# CF_OWNERDISPLAY та DSP-формати відтворити неможливо зовсім.
_UNSAVABLE = {0x80, 0x82, 0x83, 0x8E}


class Clipboard:
    def __init__(self, hwnd):
        self.hwnd = hwnd
        # Позначки, щоб наш тимчасовий/відновлений вміст не засмічував журнал Win+V
        self._no_history = [w.RegisterClipboardFormatW(name) for name in
                            ("CanIncludeInClipboardHistory", "CanUploadToCloudClipboard")]

    def _open(self, timeout=0.5):
        end = time.monotonic() + timeout
        while not w.OpenClipboard(self.hwnd):
            if time.monotonic() > end:
                return False
            w.sleep_pumping(0.01)
        return True

    def _put(self, fmt, data):
        h = w.GlobalAlloc(_GMEM_MOVEABLE, max(len(data), 1))
        if not h:
            return False
        p = w.GlobalLock(h)
        if not p:
            w.GlobalFree(h)
            return False
        ctypes.memmove(p, data, len(data))
        w.GlobalUnlock(h)
        if not w.SetClipboardData(fmt, h):
            w.GlobalFree(h)
            return False
        return True

    def _mark_no_history(self):
        for fmt in self._no_history:
            self._put(fmt, b"\0\0\0\0")

    def _read(self, fmt):
        """Байти формату або None, якщо їх не вдалося прочитати."""
        h = w.GetClipboardData(fmt)
        if not h:
            return None
        if fmt == CF_ENHMETAFILE:
            size = w.GetEnhMetaFileBits(h, 0, None)
            if not size:
                return None
            buf = ctypes.create_string_buffer(size)
            return buf.raw if w.GetEnhMetaFileBits(h, size, buf) == size else None
        size = w.GlobalSize(h)
        if not size:
            return None
        p = w.GlobalLock(h)
        if not p:
            return None
        try:
            return ctypes.string_at(p, size)
        finally:
            w.GlobalUnlock(h)

    def snapshot(self):
        """Повний знімок буфера: список (формат, байти).

        Повертає None, якщо буфер недоступний або якийсь формат не вдається
        зберегти чи відтворити — тоді чіпати буфер не можна.
        """
        if not self._open():
            return None
        items, unsaved = [], []
        try:
            fmt = 0
            while True:
                fmt = w.EnumClipboardFormats(fmt)
                if not fmt:
                    break
                if fmt in self._no_history:
                    continue
                data = None if fmt in _UNSAVABLE or fmt in _SYNTHESIZED_FROM else self._read(fmt)
                if data is None:
                    unsaved.append(fmt)
                else:
                    items.append((fmt, data))
        finally:
            w.CloseClipboard()
        saved = {fmt for fmt, _ in items}
        lost = [f for f in unsaved if not saved.intersection(_SYNTHESIZED_FROM.get(f, ()))]
        if lost:
            log.warning("clipboard formats cannot be preserved: %s", lost)
            return None
        return items

    def restore(self, items):
        """Повернути збережений вміст. Повертає False, якщо щось не вдалося записати."""
        if items is None or not self._open(1.0):
            return False
        try:
            w.EmptyClipboard()
            ok = all([self._put_any(fmt, data) for fmt, data in items])
            if items:
                self._mark_no_history()
            return ok
        finally:
            w.CloseClipboard()

    def _put_any(self, fmt, data):
        if fmt != CF_ENHMETAFILE:
            return self._put(fmt, data)
        h = w.SetEnhMetaFileBits(len(data), data)
        if not h:
            return False
        if not w.SetClipboardData(fmt, h):
            w.DeleteEnhMetaFile(h)
            return False
        return True

    def clear(self):
        if self._open():
            w.EmptyClipboard()
            w.CloseClipboard()

    def set_text(self, text):
        """Записати текст у буфер. Повертає True лише якщо запис вдався."""
        if not self._open():
            return False
        try:
            if not w.EmptyClipboard():
                return False
            ok = self._put(CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))
            self._mark_no_history()
            return ok
        finally:
            w.CloseClipboard()

    def get_text(self):
        if not self._open(0.1):
            return None
        try:
            h = w.GetClipboardData(CF_UNICODETEXT)
            p = w.GlobalLock(h) if h else None
            if not p:
                return None
            try:
                return ctypes.wstring_at(p)
            finally:
                w.GlobalUnlock(h)
        finally:
            w.CloseClipboard()

    def copy_from(self, send_copy, timeout):
        """Очистити буфер, викликати send_copy() і дочекатися тексту від програми."""
        self.clear()
        seq = w.GetClipboardSequenceNumber()
        send_copy()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            w.sleep_pumping(0.01)
            if w.GetClipboardSequenceNumber() != seq and w.IsClipboardFormatAvailable(CF_UNICODETEXT):
                text = self.get_text()
                if text is not None:
                    return text
        return None
