"""Minimal Win32 layer for driving AutoShop (pure ctypes, no third-party deps)."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

# ---------------------------------------------------------------- constants
WM_COMMAND = 0x0111
WM_CLOSE = 0x0010
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
WM_SETTEXT = 0x000C
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102

TVM_GETNEXTITEM = 0x110A
TVM_GETITEMW = 0x113E
TVM_SELECTITEM = 0x110B
TVM_EXPAND = 0x1102
TVGN_ROOT, TVGN_NEXT, TVGN_PREVIOUS, TVGN_CHILD, TVGN_CARET, TVGN_PARENT = 0, 1, 2, 4, 9, 3
TVIF_TEXT, TVIF_CHILDREN, TVIF_STATE, TVIF_HANDLE, TVIF_PARAM = 1, 2, 4, 0x10, 8
TVE_COLLAPSE, TVE_EXPAND = 1, 2
TVS_EX_DOUBLEBUFFER = 0x0004

LB_GETCOUNT = 0x018B
LB_GETTEXT = 0x0189
LB_GETTEXTLEN = 0x018A
LB_SETCURSEL = 0x0186
LB_GETCURSEL = 0x0188

SB_GETTEXTW = 0x040D
SB_GETTEXTLENGTHW = 0x040C
SB_GETPARTS = 0x0406

TB_BUTTONCOUNT = 0x0418
TB_GETBUTTON = 0x0417
TB_GETITEMRECT = 0x041D
TB_GETBUTTONTEXTW = 0x044B
TB_COMMANDTOINDEX = 0x0419
TB_GETSTATE = 0x0412

BM_CLICK = 0x00F5
CB_GETCOUNT = 0x0146
CB_GETLBTEXT = 0x0148
CB_SETCURSEL = 0x014E
CB_GETCURSEL = 0x0147

PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04

TH32CS_SNAPPROCESS = 0x00000002


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)), ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


class TVITEMW(ctypes.Structure):
    _fields_ = [("mask", ctypes.c_uint), ("hItem", ctypes.c_void_p),
                ("state", ctypes.c_uint), ("stateMask", ctypes.c_uint),
                ("pszText", ctypes.c_void_p), ("cchTextMax", ctypes.c_int),
                ("iImage", ctypes.c_int), ("iSelectedImage", ctypes.c_int),
                ("cChildren", ctypes.c_int), ("lParam", ctypes.c_void_p)]


# ---------------------------------------------------------------- prototypes
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM), wt.LPARAM]
user32.EnumWindows.restype = wt.BOOL
user32.EnumChildWindows.argtypes = [wt.HWND, ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM), wt.LPARAM]
user32.EnumChildWindows.restype = wt.BOOL
user32.GetClassNameW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]
user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsWindowEnabled.argtypes = [wt.HWND]
user32.GetDlgCtrlID.argtypes = [wt.HWND]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetParent.argtypes = [wt.HWND]
user32.GetParent.restype = wt.HWND
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
user32.PostMessageW.restype = wt.BOOL

kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.VirtualAllocEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, wt.DWORD]
kernel32.VirtualAllocEx.restype = ctypes.c_void_p
kernel32.VirtualFreeEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD]
kernel32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                       ctypes.POINTER(ctypes.c_size_t)]
kernel32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                        ctypes.POINTER(ctypes.c_size_t)]
kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
kernel32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]


# ---------------------------------------------------------------- helpers
def window_text(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 2)
    user32.GetWindowTextW(hwnd, buf, n + 2)
    return buf.value


def class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetClassNameW(hwnd, buf, 512)
    return buf.value


def rect(hwnd):
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def enum_windows():
    out = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, l):
        out.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return out


def enum_children(hwnd):
    out = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, l):
        out.append(h)
        return True

    user32.EnumChildWindows(hwnd, cb, 0)
    return out


def find_processes(exe_name: str):
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PROCESSENTRY32W()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    pids = []
    if kernel32.Process32FirstW(snap, ctypes.byref(pe)):
        while True:
            if pe.szExeFile.lower() == exe_name.lower():
                pids.append(pe.th32ProcessID)
            if not kernel32.Process32NextW(snap, ctypes.byref(pe)):
                break
    kernel32.CloseHandle(snap)
    return pids


class Remote:
    """Cross-process buffer helper."""

    def __init__(self, pid: int):
        self.pid = pid
        self.h = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not self.h:
            raise OSError("OpenProcess failed")

    def close(self):
        if self.h:
            kernel32.CloseHandle(self.h)
            self.h = None

    def alloc(self, size):
        p = kernel32.VirtualAllocEx(self.h, None, size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
        if not p:
            raise OSError("VirtualAllocEx failed")
        return p

    def free(self, p):
        kernel32.VirtualFreeEx(self.h, p, 0, MEM_RELEASE)

    def write(self, addr, data: bytes):
        n = ctypes.c_size_t(0)
        buf = ctypes.create_string_buffer(data, len(data))
        if not kernel32.WriteProcessMemory(self.h, addr, buf, len(data), ctypes.byref(n)):
            raise OSError("WriteProcessMemory failed")

    def read(self, addr, size):
        n = ctypes.c_size_t(0)
        buf = ctypes.create_string_buffer(size)
        if not kernel32.ReadProcessMemory(self.h, addr, buf, size, ctypes.byref(n)):
            raise OSError("ReadProcessMemory failed")
        return buf.raw[:n.value]


def send(hwnd, msg, wparam=0, lparam=0):
    return user32.SendMessageW(hwnd, msg, wparam, lparam)


_send_w = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, ctypes.c_wchar_p)(
    ("SendMessageW", user32))


def send_text(hwnd, msg, wparam, text):
    """SendMessage with a string in lParam (same process-independent semantics)."""
    return _send_w(hwnd, msg, wparam, text)


def post(hwnd, msg, wparam=0, lparam=0):
    return user32.PostMessageW(hwnd, msg, wparam, lparam)


def wait_until(predicate, timeout=10.0, interval=0.15):
    end = time.time() + timeout
    while time.time() < end:
        v = predicate()
        if v:
            return v
        time.sleep(interval)
    return predicate()
