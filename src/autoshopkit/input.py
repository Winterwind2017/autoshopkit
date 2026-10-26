"""Real (synthetic) mouse and keyboard input.

Some AutoShop surfaces only react to genuine input: the project tree opens a
document on a real double click, MFC Feature Pack menus and the custom ladder
canvas need real keystrokes/clicks because ``PostMessage`` does not update the
keyboard state that ``TranslateAccelerator``/tracking code consults.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time

from . import win32 as w

user32 = w.user32

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
user32.ScreenToClient.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
user32.mouse_event.argtypes = [wt.DWORD, ctypes.c_long, ctypes.c_long, wt.DWORD, ctypes.c_void_p]
user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, wt.DWORD, ctypes.c_void_p]
user32.GetForegroundWindow.restype = wt.HWND
user32.SetFocus.argtypes = [wt.HWND]
user32.GetFocus.restype = wt.HWND
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.MapWindowPoints.argtypes = [wt.HWND, wt.HWND, ctypes.POINTER(wt.POINT), ctypes.c_uint]

VK = {
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12,
    "enter": 0x0D, "esc": 0x1B, "tab": 0x09, "space": 0x20,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "multiply": 0x6A, "add": 0x6B, "subtract": 0x6D, "decimal": 0x6E,
    "prior": 0x21, "next": 0x22, "pgup": 0x21, "pgdn": 0x22,
    "insert": 0x2D, "delete": 0x2E, "escape": 0x1B, "enter": 0x0D, "tab": 0x09,
    "delete": 0x2E, "insert": 0x2D, "back": 0x08,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}


def client_to_screen(hwnd, x, y):
    pt = wt.POINT(x, y)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y


def screen_to_client(hwnd, x, y):
    pt = wt.POINT(x, y)
    user32.ScreenToClient(hwnd, ctypes.byref(pt))
    return pt.x, pt.y


def move(x, y):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.02)


def click(x, y, button="left", count=1, delay=0.05):
    down = MOUSEEVENTF_LEFTDOWN if button == "left" else MOUSEEVENTF_RIGHTDOWN
    up = MOUSEEVENTF_LEFTUP if button == "left" else MOUSEEVENTF_RIGHTUP
    move(x, y)
    for _ in range(count):
        user32.mouse_event(down, 0, 0, 0, None)
        time.sleep(0.02)
        user32.mouse_event(up, 0, 0, 0, None)
        time.sleep(delay)


def click_client(hwnd, x, y, button="left", count=1):
    sx, sy = client_to_screen(hwnd, int(x), int(y))
    click(sx, sy, button, count)


def wheel(x, y, delta=-120):
    move(x, y)
    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, None)
    time.sleep(0.1)


def key(name, hold=0.03):
    vk = VK.get(name.lower()) if isinstance(name, str) and len(name) > 1 else None
    if vk is None:
        vk = ord(name.upper()) if isinstance(name, str) else int(name)
    user32.keybd_event(vk, 0, 0, None)
    time.sleep(hold)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, None)
    time.sleep(hold)


def chord(mods, name):
    mod_vks = [VK[m.lower()] for m in mods]
    for vk in mod_vks:
        user32.keybd_event(vk, 0, 0, None)
        time.sleep(0.01)
    key(name)
    for vk in reversed(mod_vks):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, None)
        time.sleep(0.01)


def type_text(text, per_char=0.01):
    for ch in text:
        vk = 0
        if ch.isascii() and ch.isprintable():
            # simple ASCII through VkKeyScan equivalent: use keybd_event with the char code
            user32.keybd_event(0, 0, 0, None)
        # fall back to unicode injection
        _type_unicode(ch)
        time.sleep(per_char)


def _type_unicode(ch):
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                    ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        _anonymous_ = ("u",)
        _fields_ = [("type", wt.DWORD), ("u", _U)]

    for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.ki = KEYBDINPUT(0, ord(ch), flags, 0, None)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


w.kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
w.kernel32.GlobalAlloc.restype = ctypes.c_void_p
w.kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
w.kernel32.GlobalLock.restype = ctypes.c_void_p
w.kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
w.kernel32.GlobalUnlock.restype = wt.BOOL
w.kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
w.kernel32.GlobalSize.restype = ctypes.c_size_t


def set_clipboard(text):
    """Put text on the clipboard (CF_UNICODETEXT)."""
    user32.OpenClipboard.argtypes = [wt.HWND]
    user32.EmptyClipboard.restype = wt.BOOL
    user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
    user32.SetClipboardData.restype = wt.HANDLE
    user32.CloseClipboard.restype = wt.BOOL
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    data = text.encode("utf-16-le") + b"\x00\x00"
    h = w.kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    p = w.kernel32.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    w.kernel32.GlobalUnlock(h)
    user32.OpenClipboard(None)
    user32.EmptyClipboard()
    user32.SetClipboardData(CF_UNICODETEXT, h)
    user32.CloseClipboard()


def get_clipboard():
    user32.GetClipboardData.argtypes = [wt.UINT]
    user32.GetClipboardData.restype = ctypes.c_void_p
    CF_UNICODETEXT = 13
    user32.OpenClipboard(None)
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        w.kernel32.GlobalLock.restype = ctypes.c_void_p
        p = w.kernel32.GlobalLock(h)
        if not p:
            return ""
        size = w.kernel32.GlobalSize(ctypes.c_void_p(h))
        raw = ctypes.string_at(p, size)
        w.kernel32.GlobalUnlock(h)
        return raw.decode("utf-16-le", "replace").split("\x00")[0]
    finally:
        user32.CloseClipboard()
