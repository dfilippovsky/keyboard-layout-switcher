"""Робота з буфером обміну: збереження/відновлення та копіювання виділеного."""
import ctypes
import time

import winapi as w

CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002
# Формати з GDI-дескрипторами замість HGLOBAL — їх не копіюємо
# (CF_BITMAP система відтворить із CF_DIB, який зберігається).
_SKIP_FORMATS = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E}


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
            return
        p = w.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        w.GlobalUnlock(h)
        if not w.SetClipboardData(fmt, h):
            w.GlobalFree(h)

    def _mark_no_history(self):
        for fmt in self._no_history:
            self._put(fmt, b"\0\0\0\0")

    def snapshot(self):
        """Повертає список (формат, байти) або None, якщо буфер недоступний."""
        if not self._open():
            return None
        items = []
        try:
            fmt = 0
            while True:
                fmt = w.EnumClipboardFormats(fmt)
                if not fmt:
                    break
                if fmt in _SKIP_FORMATS or fmt in self._no_history:
                    continue
                h = w.GetClipboardData(fmt)
                if not h:
                    continue
                size = w.GlobalSize(h)
                p = w.GlobalLock(h) if size else None
                if not p:
                    continue
                try:
                    items.append((fmt, ctypes.string_at(p, size)))
                finally:
                    w.GlobalUnlock(h)
        finally:
            w.CloseClipboard()
        return items

    def restore(self, items):
        if items is None or not self._open():
            return
        try:
            w.EmptyClipboard()
            for fmt, data in items:
                self._put(fmt, data)
            if items:
                self._mark_no_history()
        finally:
            w.CloseClipboard()

    def clear(self):
        if self._open():
            w.EmptyClipboard()
            w.CloseClipboard()

    def set_text(self, text):
        if not self._open():
            return
        try:
            w.EmptyClipboard()
            self._put(CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))
            self._mark_no_history()
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
