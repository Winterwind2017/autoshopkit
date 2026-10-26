"""UI Automation helpers (comtypes) — the read path for owner-drawn surfaces.

Why this exists: several AutoShop surfaces keep their text out of reach of window
messages (the status bar ignores ``SB_GETTEXTW``, the ladder canvas paints its own
labels, the symbol grid's cells are ActiveX internals).  UI Automation sees them
because it runs out-of-process in ``UIAutomationCore`` and therefore crosses the
32/64-bit boundary, which plain window messages cannot.

Verified observations (AutoShop V4.11.0.5):

* the frame exposes the dock panes, the project tree (nodes carry ``Value``), the
  MDI tabs, the toolbars and the **status bar text** (``Afx:StatusBar`` element
  name, e.g. ``就绪``);
* the symbol grid ``VSFlexGrid8N`` exposes only its header cells and
  ``Row 0..N`` items — **not** individual cells;
* while a cell is being edited, the in-cell editor appears as an element whose
  class is ``ATL:697A8F20`` and it **does** support ``ValuePattern`` (read and
  ``SetValue``) — this is the missing write path for the symbol table.
"""
from __future__ import annotations

import time

import comtypes
import comtypes.client
from comtypes.client import GetModule

GetModule("UIAutomationCore.dll")
from comtypes.gen import UIAutomationClient as U  # noqa: E402

TreeScope_Children = 2
TreeScope_Descendants = 4

_automation = None


def automation():
    global _automation
    if _automation is None:
        _automation = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)
    return _automation


def from_handle(hwnd):
    return automation().ElementFromHandle(hwnd)


def find_first(root, class_name=None, name=None, control_type=None, timeout=0.0):
    """First descendant matching the given (single) property condition."""
    a = automation()
    cond = None
    if class_name is not None:
        cond = a.CreatePropertyCondition(U.UIA_ClassNamePropertyId, class_name)
    elif name is not None:
        cond = a.CreatePropertyCondition(U.UIA_NamePropertyId, name)
    elif control_type is not None:
        cond = a.CreatePropertyCondition(U.UIA_ControlTypePropertyId, control_type)
    if cond is None:
        return None
    end = time.time() + timeout

    def valid(value):
        # comtypes hands back a POINTER(IUnknown) whose ``value`` is 0 when nothing was
        # found; such a pointer is *truthy*, so a plain ``if element`` check mistakes it
        # for a hit (this made every "no editor" case look like a successful one).
        if value is None:
            return None
        try:
            return value if value.value else None
        except Exception:
            return value

    while True:
        try:
            element = valid(root.FindFirst(TreeScope_Descendants, cond))
        except Exception:
            element = None
        if element is not None or time.time() >= end:
            return element
        time.sleep(0.2)


def value_pattern(element):
    """``IUIAutomationValuePattern`` for an element (None when unsupported).

    ``GetCurrentPattern`` hands back a bare ``IUnknown``; comtypes only exposes the
    typed members after an explicit ``QueryInterface``.
    """
    try:
        raw = element.GetCurrentPattern(U.UIA_ValuePatternId)
    except Exception:
        return None
    try:
        return raw.QueryInterface(U.IUIAutomationValuePattern)
    except Exception:
        return None


def value_of(element):
    pattern = value_pattern(element)
    if pattern is None:
        return None
    try:
        return pattern.CurrentValue
    except Exception:
        return None


def set_value(element, text):
    """Write through ``ValuePattern``; returns True when the app accepted it."""
    pattern = value_pattern(element)
    if pattern is None:
        return False
    try:
        if pattern.CurrentIsReadOnly:
            return False
        pattern.SetValue(text)
        return True
    except Exception:
        return False


def children(element):
    a = automation()
    walker = a.RawViewWalker
    out = []
    try:
        child = walker.GetFirstChildElement(element)
    except Exception:
        return out
    while child is not None:
        out.append(child)
        try:
            child = walker.GetNextSiblingElement(child)
        except Exception:
            break
    return out


def status_bar_text(frame_hwnd):
    """The status bar's current message (``SB_GETTEXTW`` cannot read it)."""
    root = from_handle(frame_hwnd)
    element = find_first(root, class_name="Afx:StatusBar:400000:8:10003:10")
    if element is None:
        element = find_first(root, control_type=U.UIA_StatusBarControlTypeId)
    if element is None:
        return ""
    name = ""
    try:
        name = element.CurrentName or ""
    except Exception:
        name = ""
    return name


EDITOR_PREFIX = "ATL:"


def _editor_in(element, depth=3):
    """First ``ATL:*`` descendant (the grids' in-cell editor), breadth-first."""
    if element is None:
        return None
    frontier = [element]
    for _ in range(max(1, depth)):
        next_frontier = []
        for node in frontier:
            try:
                kids = children(node)
            except Exception:
                kids = []
            for child in kids:
                try:
                    class_name = child.CurrentClassName or ""
                except Exception:
                    continue
                if class_name.startswith(EDITOR_PREFIX):
                    return child
                next_frontier.append(child)
        frontier = next_frontier
        if not frontier:
            break
    return None


def _wait_editor(parent_hwnd, timeout):
    end = time.time() + max(0.0, timeout)
    while True:
        found = _editor_in(from_handle(parent_hwnd))
        if found is not None or time.time() >= end:
            return found
        time.sleep(0.15)


def editor_element(frame_hwnd, class_name="ATL:", timeout=3.0):
    """The in-cell editor of any ActiveX grid inside ``frame_hwnd``.

    The class name is ``ATL:<hash>`` and **the hash differs between controls** (the symbol
    grid's editor was ``ATL:697A8F20``, the monitor grid's ``ATL:503B8F20``), so the search
    matches on the ``ATL:`` prefix instead of an exact name — an exact match silently
    missed the monitor grid altogether.
    """
    return _wait_editor(frame_hwnd, timeout)


def editor_element_in(parent_hwnd, class_name="ATL:", timeout=2.0):
    """Like :func:`editor_element`, but scoped to one grid window.

    Scoping matters as soon as two ActiveX grids are open (符号表 and 元件监控表): a
    frame-wide search can return the editor that belongs to the *other* document.
    """
    return _wait_editor(parent_hwnd, timeout)
