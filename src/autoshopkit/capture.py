"""Window capture helpers (PrintWindow -> PNG) without third-party libraries."""
from __future__ import annotations

import ctypes
import struct
import zlib

from . import win32 as w

SRCCOPY = 0x00CC0020
PW_RENDERFULLCONTENT = 0x00000002
DIB_RGB_COLORS = 0
BI_RGB = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16),
                ("biCompression", ctypes.c_uint32), ("biSizeImage", ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_int32), ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]


gdi32 = w.gdi32
gdi32.CreateCompatibleDC.argtypes = [w.wt.HDC]
gdi32.CreateCompatibleDC.restype = w.wt.HDC
gdi32.CreateCompatibleBitmap.argtypes = [w.wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = w.wt.HBITMAP
gdi32.SelectObject.argtypes = [w.wt.HDC, w.wt.HGDIOBJ]
gdi32.SelectObject.restype = w.wt.HGDIOBJ
gdi32.GetDIBits.argtypes = [w.wt.HDC, w.wt.HBITMAP, ctypes.c_uint, ctypes.c_uint,
                            ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), ctypes.c_uint]
gdi32.DeleteObject.argtypes = [w.wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [w.wt.HDC]
user32 = w.user32
user32.PrintWindow.argtypes = [w.wt.HWND, w.wt.HDC, ctypes.c_uint]


def _png(width, height, rgb_rows):
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + row for row in rgb_rows)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def capture_window(hwnd, path):
    """Grab one window into a PNG file. Returns (width, height)."""
    left, top, right, bottom = w.rect(hwnd)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        raise ValueError("window has no area")
    hdc_win = w.user32.GetDC(hwnd)
    hdc_mem = w.gdi32.CreateCompatibleDC(hdc_win)
    hbmp = w.gdi32.CreateCompatibleBitmap(hdc_win, width, height)
    w.gdi32.SelectObject(hdc_mem, hbmp)
    ok = w.user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height  # top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB
    buf = ctypes.create_string_buffer(width * height * 4)
    w.gdi32.GetDIBits(hdc_mem, hbmp, 0, height, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
    rows = []
    data = buf.raw
    for y in range(height):
        off = y * width * 4
        line = data[off:off + width * 4]
        # BGRA -> RGB
        rgb = bytearray(width * 3)
        rgb[0::3] = line[2::4]
        rgb[1::3] = line[1::4]
        rgb[2::3] = line[0::4]
        rows.append(bytes(rgb))
    png = _png(width, height, rows)
    with open(path, "wb") as fh:
        fh.write(png)
    w.gdi32.DeleteObject(hbmp)
    w.gdi32.DeleteDC(hdc_mem)
    w.user32.ReleaseDC(hwnd, hdc_win)
    return width, height, ok
