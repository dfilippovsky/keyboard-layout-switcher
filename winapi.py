"""Мінімальні ctypes-обгортки над WinAPI, потрібні програмі."""
import ctypes
import time
from ctypes import wintypes as W

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
MSG = W.MSG
POINT = W.POINT

# Повідомлення вікон
WM_NULL = 0x0000
WM_DESTROY = 0x0002
WM_SETTINGCHANGE = 0x001A
WM_INPUTLANGCHANGEREQUEST = 0x0050
WM_SETICON = 0x0080
WM_TIMER = 0x0113
WM_HOTKEY = 0x0312
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_APP = 0x8000

# Трей
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x01, 0x02, 0x04, 0x10
NIIF_INFO, NIIF_WARNING = 0x01, 0x02

# Меню
MF_STRING, MF_GRAYED, MF_CHECKED, MF_SEPARATOR = 0x0000, 0x0001, 0x0008, 0x0800
TPM_RIGHTBUTTON, TPM_NONOTIFY, TPM_RETURNCMD = 0x0002, 0x0080, 0x0100

SM_CXSMICON = 49
ERROR_ALREADY_EXISTS = 183


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", W.UINT), ("style", W.UINT), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", W.HINSTANCE), ("hIcon", W.HICON), ("hCursor", W.HANDLE),
        ("hbrBackground", W.HBRUSH), ("lpszMenuName", W.LPCWSTR),
        ("lpszClassName", W.LPCWSTR), ("hIconSm", W.HICON),
    ]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", W.DWORD), ("Data2", W.WORD), ("Data3", W.WORD), ("Data4", W.BYTE * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", W.DWORD), ("hWnd", W.HWND), ("uID", W.UINT), ("uFlags", W.UINT),
        ("uCallbackMessage", W.UINT), ("hIcon", W.HICON), ("szTip", W.WCHAR * 128),
        ("dwState", W.DWORD), ("dwStateMask", W.DWORD), ("szInfo", W.WCHAR * 256),
        ("uTimeoutOrVersion", W.UINT), ("szInfoTitle", W.WCHAR * 64),
        ("dwInfoFlags", W.DWORD), ("guidItem", GUID), ("hBalloonIcon", W.HICON),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD),
                ("dwFlags", W.DWORD), ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", W.DWORD), ("u", _INPUTUNION)]


def _f(dll, name, restype, *argtypes):
    fn = getattr(dll, name)
    fn.restype = restype
    fn.argtypes = argtypes
    return fn


# user32 — вікна, повідомлення, меню
RegisterClassExW = _f(user32, "RegisterClassExW", W.ATOM, ctypes.POINTER(WNDCLASSEXW))
CreateWindowExW = _f(user32, "CreateWindowExW", W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
                     ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                     W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID)
DefWindowProcW = _f(user32, "DefWindowProcW", LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
DestroyWindow = _f(user32, "DestroyWindow", W.BOOL, W.HWND)
PostQuitMessage = _f(user32, "PostQuitMessage", None, ctypes.c_int)
GetMessageW = _f(user32, "GetMessageW", W.BOOL, ctypes.POINTER(W.MSG), W.HWND, W.UINT, W.UINT)
TranslateMessage = _f(user32, "TranslateMessage", W.BOOL, ctypes.POINTER(W.MSG))
DispatchMessageW = _f(user32, "DispatchMessageW", LRESULT, ctypes.POINTER(W.MSG))
PeekMessageW = _f(user32, "PeekMessageW", W.BOOL, ctypes.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT)
PostMessageW = _f(user32, "PostMessageW", W.BOOL, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
SendMessageW = _f(user32, "SendMessageW", LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
RegisterWindowMessageW = _f(user32, "RegisterWindowMessageW", W.UINT, W.LPCWSTR)
SetTimer = _f(user32, "SetTimer", ULONG_PTR, W.HWND, ULONG_PTR, W.UINT, W.LPVOID)
KillTimer = _f(user32, "KillTimer", W.BOOL, W.HWND, ULONG_PTR)
RegisterHotKey = _f(user32, "RegisterHotKey", W.BOOL, W.HWND, ctypes.c_int, W.UINT, W.UINT)
UnregisterHotKey = _f(user32, "UnregisterHotKey", W.BOOL, W.HWND, ctypes.c_int)
CreatePopupMenu = _f(user32, "CreatePopupMenu", W.HMENU)
AppendMenuW = _f(user32, "AppendMenuW", W.BOOL, W.HMENU, W.UINT, ULONG_PTR, W.LPCWSTR)
SetMenuDefaultItem = _f(user32, "SetMenuDefaultItem", W.BOOL, W.HMENU, W.UINT, W.UINT)
TrackPopupMenu = _f(user32, "TrackPopupMenu", W.BOOL, W.HMENU, W.UINT, ctypes.c_int, ctypes.c_int,
                    ctypes.c_int, W.HWND, W.LPVOID)
DestroyMenu = _f(user32, "DestroyMenu", W.BOOL, W.HMENU)
GetCursorPos = _f(user32, "GetCursorPos", W.BOOL, ctypes.POINTER(W.POINT))
SetForegroundWindow = _f(user32, "SetForegroundWindow", W.BOOL, W.HWND)
GetForegroundWindow = _f(user32, "GetForegroundWindow", W.HWND)
GetWindowThreadProcessId = _f(user32, "GetWindowThreadProcessId", W.DWORD, W.HWND, ctypes.POINTER(W.DWORD))
GetSystemMetrics = _f(user32, "GetSystemMetrics", ctypes.c_int, ctypes.c_int)
MessageBoxW = _f(user32, "MessageBoxW", ctypes.c_int, W.HWND, W.LPCWSTR, W.LPCWSTR, W.UINT)
MessageBeep = _f(user32, "MessageBeep", W.BOOL, W.UINT)
CreateIconFromResourceEx = _f(user32, "CreateIconFromResourceEx", W.HICON, W.LPVOID, W.DWORD, W.BOOL,
                              W.DWORD, ctypes.c_int, ctypes.c_int, W.UINT)
DestroyIcon = _f(user32, "DestroyIcon", W.BOOL, W.HICON)

# user32 — клавіатура
GetKeyboardLayout = _f(user32, "GetKeyboardLayout", W.HKL, W.DWORD)
GetKeyboardLayoutList = _f(user32, "GetKeyboardLayoutList", ctypes.c_int, ctypes.c_int, ctypes.POINTER(W.HKL))
ToUnicodeEx = _f(user32, "ToUnicodeEx", ctypes.c_int, W.UINT, W.UINT, ctypes.POINTER(ctypes.c_ubyte),
                 W.LPWSTR, ctypes.c_int, W.UINT, W.HKL)
MapVirtualKeyExW = _f(user32, "MapVirtualKeyExW", W.UINT, W.UINT, W.UINT, W.HKL)
SendInput = _f(user32, "SendInput", W.UINT, W.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
GetAsyncKeyState = _f(user32, "GetAsyncKeyState", W.SHORT, ctypes.c_int)

# user32 — буфер обміну
OpenClipboard = _f(user32, "OpenClipboard", W.BOOL, W.HWND)
CloseClipboard = _f(user32, "CloseClipboard", W.BOOL)
EmptyClipboard = _f(user32, "EmptyClipboard", W.BOOL)
GetClipboardData = _f(user32, "GetClipboardData", W.HANDLE, W.UINT)
SetClipboardData = _f(user32, "SetClipboardData", W.HANDLE, W.UINT, W.HANDLE)
EnumClipboardFormats = _f(user32, "EnumClipboardFormats", W.UINT, W.UINT)
IsClipboardFormatAvailable = _f(user32, "IsClipboardFormatAvailable", W.BOOL, W.UINT)
GetClipboardSequenceNumber = _f(user32, "GetClipboardSequenceNumber", W.DWORD)
RegisterClipboardFormatW = _f(user32, "RegisterClipboardFormatW", W.UINT, W.LPCWSTR)

# gdi32 — розширені метафайли в буфері обміну
GetEnhMetaFileBits = _f(gdi32, "GetEnhMetaFileBits", W.UINT, W.HANDLE, W.UINT, W.LPVOID)
SetEnhMetaFileBits = _f(gdi32, "SetEnhMetaFileBits", W.HANDLE, W.UINT, ctypes.c_char_p)
DeleteEnhMetaFile = _f(gdi32, "DeleteEnhMetaFile", W.BOOL, W.HANDLE)

# kernel32
GlobalAlloc = _f(kernel32, "GlobalAlloc", W.HGLOBAL, W.UINT, ctypes.c_size_t)
GlobalLock = _f(kernel32, "GlobalLock", W.LPVOID, W.HGLOBAL)
GlobalUnlock = _f(kernel32, "GlobalUnlock", W.BOOL, W.HGLOBAL)
GlobalSize = _f(kernel32, "GlobalSize", ctypes.c_size_t, W.HGLOBAL)
GlobalFree = _f(kernel32, "GlobalFree", W.HGLOBAL, W.HGLOBAL)
GetModuleHandleW = _f(kernel32, "GetModuleHandleW", W.HMODULE, W.LPCWSTR)
CreateMutexW = _f(kernel32, "CreateMutexW", W.HANDLE, W.LPVOID, W.BOOL, W.LPCWSTR)
LCIDToLocaleName = _f(kernel32, "LCIDToLocaleName", ctypes.c_int, W.DWORD, W.LPWSTR, ctypes.c_int, W.DWORD)

# shell32
Shell_NotifyIconW = _f(shell32, "Shell_NotifyIconW", W.BOOL, W.DWORD, ctypes.POINTER(NOTIFYICONDATAW))


def sleep_pumping(seconds):
    """Пауза, під час якої обробляються надіслані (SendMessage) повідомлення.

    Інакше програма, що копіює в буфер, зависає на EmptyClipboard, чекаючи
    відповіді на WM_DESTROYCLIPBOARD від нашого вікна (попереднього власника).
    Posted-повідомлення (WM_HOTKEY тощо) лишаються в черзі — без реентерабельності.
    """
    msg = W.MSG()
    end = time.monotonic() + seconds
    while True:
        PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # PM_NOREMOVE
        left = end - time.monotonic()
        if left <= 0:
            return
        time.sleep(min(0.01, left))
