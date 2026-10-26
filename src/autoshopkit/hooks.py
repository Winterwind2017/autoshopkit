"""In-process text tap (Frida) used to read what AutoShop paints.

Why this exists: the 信息输出窗口 (compile / convert / find output) is an
owner-drawn list box whose items carry no retrievable string -- ``LB_GETTEXT``
returns four NUL characters for every row -- and the ladder canvas is drawn
pixel by pixel.  The GDI text calls do receive the real strings, so a short
Frida hook captures exactly what the app displays for a chosen window.

Verified observations (2026-10-26, AutoShop V4.11.0.5):
  * ``DrawTextW``/``DrawTextExW`` carry the full line for the output pane.
  * The output list box only repaints when new messages arrive, so
    :meth:`TextTap.repaint` invalidates it to read the *current* content.
  * Frida 17 removed ``Module.getExportByName(module, name)``; use
    ``Module.getGlobalExportByName``.
"""
from __future__ import annotations

import time

import frida

_HOOK_JS = r"""
function resolve(name) {
  try { return Module.getGlobalExportByName(name); } catch (e) {}
  try { return Module.getExportByName(null, name); } catch (e) {}
  return null;
}

function hook(name, iHwnd, iText) {
  const addr = resolve(name);
  if (addr === null) { send({ api: 'resolve-failed', hwnd: '0', text: name }); return; }
  try {
    Interceptor.attach(addr, {
      onEnter(args) {
        try {
          const hwnd = args[iHwnd].toInt32();
          const p = args[iText];
          if (p.isNull()) return;
          const text = p.readUtf16String();
          if (text) send({ api: name, hwnd: String(hwnd), text: text });
        } catch (e) {}
      }
    });
  } catch (e) { send({ api: 'hook-failed', hwnd: '0', text: name + ': ' + String(e) }); }
}

hook('DrawTextW', 0, 1);
hook('DrawTextExW', 0, 1);
send({ api: 'armed', hwnd: '0', text: 'text hook installed' });
"""

WANTED = {"DrawTextW", "DrawTextExW"}


def _u32(value: int) -> int:
    return value & 0xFFFFFFFF


class TextTap:
    """Collect the strings AutoShop paints, optionally for one window only."""

    def __init__(self, pid: int, hwnds=None):
        self.pid = pid
        self.hwnds = {_u32(h) for h in hwnds} if hwnds else None
        self.messages = []
        self._session = None
        self._script = None

    def start(self):
        self._session = frida.attach(self.pid)
        self._script = self._session.create_script(_HOOK_JS)
        self._script.on("message", self._on_message)
        self._script.load()
        return self

    def _on_message(self, message, data):
        if message.get("type") != "send":
            return
        payload = message["payload"]
        if payload.get("api") not in WANTED and payload.get("api") != "armed":
            return
        try:
            hwnd = int(payload.get("hwnd", "0")) & 0xFFFFFFFF
        except ValueError:
            hwnd = 0
        if self.hwnds is not None and hwnd not in self.hwnds and payload.get("api") != "armed":
            return
        text = payload.get("text", "")
        if text and text != "text hook installed":
            self.messages.append(text)

    def repaint(self, hwnd, wait=0.6):
        """Force ``hwnd`` to redraw so its current text is captured."""
        from . import win32 as w
        user32 = w.user32
        user32.InvalidateRect(hwnd, None, True)
        time.sleep(wait)

    def lines(self, dedupe=True):
        out = []
        prev = None
        for t in self.messages:
            if dedupe and t == prev:
                continue
            out.append(t)
            prev = t
        return out

    def wait_for(self, predicate, timeout=60.0, poll=0.2):
        end = time.time() + timeout
        while time.time() < end:
            if predicate(self.lines()):
                return True
            time.sleep(poll)
        return False

    def stop(self):
        try:
            if self._script:
                self._script.unload()
        except Exception:
            pass
        try:
            if self._session:
                self._session.detach()
        except Exception:
            pass
        self._script = None
        self._session = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False
