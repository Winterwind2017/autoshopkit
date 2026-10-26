"""AutoShop (Inovance PLC IDE) driver.

Everything here was verified against AutoShop V4.11.0.5 (see docs/RECON.md):

* AutoShop is an MFC MDI application.  Its menu bar and toolbars come from the
  MFC Feature Pack, so ``GetMenu`` returns nothing and there are no menu
  handles to walk; commands are dispatched with ``WM_COMMAND`` carrying the
  resource command id (the ids are recovered in docs/COMMANDS.md).
* ``AutoShop.exe <project.hcp>`` opens that project directly - the fastest way
  to reach a deterministic state.
* The project tree is a ``SysTreeView32`` (control id 1) that only reacts to
  genuine input: ``TVM_*`` reads work, but opening an entry needs a real double
  click.  ``tree_open`` therefore drives the keyboard plus one synthetic click.
* The information/output pane is an owner-drawn ``ListBox`` whose rows hold no
  text (``LB_GETTEXT`` returns four NULs); see :mod:`autoshopkit.hooks`.
* The instruction-list ("指令列表") editor is a real ``Scintilla`` control, so
  program source can be read and written with ``SCI_*`` messages.
* Documents live in an MDI client; ``WM_MDIACTIVATE`` switches the active one.
"""
from __future__ import annotations

import ctypes
import os
import struct
import subprocess
import time

from . import win32 as w

EXE = r"D:\Inovance Control\AutoShop\AutoShop.exe"
PROC = "AutoShop.exe"

# Command ids recovered from the MENU / TOOLBAR / ACCELERATOR resources of
# AutoShop.exe (see docs/COMMANDS.md for the extraction method).
CMD = {
    # project
    "new_project": 32858,
    "open_project": 32859,
    "save_project": 32861,
    "save_project_as": 32862,
    "close_project": 32860,
    "project_props": 33181,
    "pack_project": 33838,
    "unpack_project": 33839,
    # documents
    "save_file": 57603,
    "close_file": 57602,
    "import": 33031,
    "export": 33032,
    "make_download_file": 33186,
    "compare_local": 33507,
    "compare_plc": 33594,
    # editing
    "undo": 57643,
    "redo": 57644,
    "cut": 57635,
    "copy": 57634,
    "paste": 57637,
    "delete": 57632,
    "find": 57641,
    "replace": 57641,
    # views
    # 查看 -> 切换编辑器（实测 ID；32867/32868/32869 是 SFC 的并行分支/汇合/梯形图块，不是视图）
    "view_il": 32883,        # 切换为指令列表编辑器（仅 H3U 这类以 .IL 存程序的机型有效）
    "view_ladder": 32884,    # 切换为梯形图编辑器
    "view_sfc": 32885,       # 切换为步进状态图编辑器
    "view_symbols": 33367,   # 查看 -> 符号编址
    # plc / compile
    "compile": 32992,        # PLC -> 编译        (Ctrl+Alt+F7)
    "compile_all": 32993,    # PLC -> 全部编译    (Ctrl+F7)
    "clean_compile": 33008,  # PLC -> 清理编译信息
    "upload": 33009,         # PLC -> 上载
    "download": 32882,       # PLC -> 下载        (Ctrl+F8)
    "program_check": 33006,  # PLC -> 程序校验
    "run": 33009,
    "stop": 33010,
    # debug
    "monitor": 32893,        # 调试 -> 监控        (Ctrl+F3)
    "monitor_pause": 32910,
    "online_edit": 32908,
    "write": 32895,          # 调试 -> 写入        (Ctrl+F4)
    "monitor_table_add": 33030,
    # ladder elements
    "no_contact": 32931,
    "nc_contact": 32932,
    "application_ins": 32841,
    "vertical_line": 32935,
    "delete_vertical": 32930,
    # misc
    "exit": 57665,
}


class Control:
    def __init__(self, hwnd, app):
        self.hwnd = hwnd
        self.app = app

    @property
    def cls(self):
        return w.class_name(self.hwnd)

    @property
    def text(self):
        return w.window_text(self.hwnd)

    @property
    def cid(self):
        return w.user32.GetDlgCtrlID(self.hwnd)

    @property
    def visible(self):
        return bool(w.user32.IsWindowVisible(self.hwnd))

    @property
    def enabled(self):
        return bool(w.user32.IsWindowEnabled(self.hwnd))

    @property
    def rect(self):
        return w.rect(self.hwnd)

    def __repr__(self):
        return "<%s id=%s '%s'>" % (self.cls, self.cid, self.text)


class AutoShop:
    def __init__(self, pid: int):
        self.pid = pid
        self.remote = w.Remote(pid)
        self.frame = self._find_frame()
        if not self.frame:
            raise RuntimeError("AutoShop frame window not found")

    # -------------------------------------------------------------- lifecycle
    @classmethod
    def attach(cls) -> "AutoShop | None":
        pids = w.find_processes(PROC)
        return cls(pids[0]) if pids else None

    @classmethod
    def launch(cls, project: str | None = None, exe: str = EXE,
               wait: float = 60.0, timeout_title: str | None = None) -> "AutoShop":
        # a stale instance would be attached instead of the new project
        running = cls.attach()
        if running:
            running.close(timeout=12, force=True)
            time.sleep(1.0)
        args = [exe] + ([project] if project else [])
        subprocess.Popen(args, cwd=os.path.dirname(exe))
        end = time.time() + wait
        app = None
        while time.time() < end:
            try:
                app = cls.attach()
            except Exception:
                app = None
            if app:
                titled = timeout_title in app.title if timeout_title else True
                if project and os.path.isdir(project):
                    wanted = os.path.basename(project.rstrip("\\"))
                    titled = titled and wanted and wanted.split(".")[0] in app.title
                if titled:
                    # the title appears before the project tree is populated; grid and
                    # tree clicks need the tree ready, so wait for it here
                    tree = app.tree()
                    for _ in range(40):
                        try:
                            if tree and len(app.tree_items(tree)) >= 5:
                                return app
                        except Exception:  # noqa: BLE001 - keep polling
                            pass
                        time.sleep(0.5)
                    return app
            time.sleep(0.5)
        raise TimeoutError("AutoShop main frame did not appear in %.0fs" % wait)

    def close(self, timeout=20.0, save=False, force=True):
        """Close AutoShop, answering "save changes?" prompts with yes/no.

        ``save=False`` answers 否 (discard), which is what a scratch/CI run
        wants; pass ``save=True`` to answer 是.
        """
        keep = "是(&Y)" if save else "否(&N)"
        w.post(self.frame, w.WM_CLOSE)
        end = time.time() + timeout
        while time.time() < end:
            if self.pid not in w.find_processes(PROC):
                return True
            for h in self.dialogs():
                clicked = False
                for c in self.dialog_controls(h):
                    if c.cls == "Button" and c.text == keep:
                        w.post(c.hwnd, w.BM_CLICK)
                        clicked = True
                        break
                if not clicked:
                    for c in self.dialog_controls(h):
                        if c.cls == "Button" and c.text in ("确定", "否(&N)"):
                            w.post(c.hwnd, w.BM_CLICK)
                            break
            time.sleep(0.3)
        if force:
            import ctypes as _c
            h = w.kernel32.OpenProcess(0x0001, False, self.pid)  # PROCESS_TERMINATE
            if h:
                w.kernel32.TerminateProcess(h, 1)
                w.kernel32.CloseHandle(h)
                time.sleep(1.0)
                return self.pid not in w.find_processes(PROC)
        return False

    def _find_frame(self):
        for hwnd in w.enum_windows():
            pid = ctypes.c_ulong(0)
            w.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != self.pid:
                continue
            cls = w.class_name(hwnd)
            title = w.window_text(hwnd)
            if cls.startswith("Afx:") and title.startswith("AutoShop"):
                return hwnd
        return None

    @classmethod
    def create_project(cls, name, dest_dir=None, **dialog_args):
        """Create a project and leave it open, returning ``(app, project_dir)``.

        Creates through the 新建工程 dialog (which always writes to Documents),
        closes AutoShop so the folder can be moved to ``dest_dir``, then starts a
        fresh instance on the moved project - the deterministic way to end up with
        an open, usable project at a chosen location.
        """
        import os
        import shutil

        app = cls.attach() or cls.launch(None)
        project = app.new_project(name, dest_dir=None, **dialog_args)
        if not project:
            raise RuntimeError("project creation failed")
        app.close()
        if dest_dir:
            dest_dir = os.path.abspath(dest_dir)
            os.makedirs(dest_dir, exist_ok=True)
            target = os.path.join(dest_dir, os.path.basename(project.rstrip("\\")))
            if os.path.normcase(os.path.normpath(target)) != os.path.normcase(os.path.normpath(project)):
                if os.path.isdir(target):
                    shutil.rmtree(target)
                shutil.move(project.rstrip("\\"), target)
                project = target
        hcp = [f for f in os.listdir(project) if f.lower().endswith(".hcp")]
        path = os.path.join(project, hcp[0]) if hcp else project
        new_app = cls.launch(path, wait=90, timeout_title=os.path.basename(project))
        return new_app, project

    @property
    def title(self):
        return w.window_text(self.frame)

    @property
    def project_path(self):
        """Directory of the open project, parsed from the frame title."""
        t = self.title
        marker = "  "
        if marker in t:
            rest = t.split(marker, 1)[1]
            if " - [" in rest:
                return rest.split(" - [")[0].strip()
            return rest.strip()
        return ""

    @property
    def project_name(self):
        return os.path.basename(self.project_path)

    # --------------------------------------------------------------- commands
    def command(self, cmd_id: int, verify=None, timeout=3.0):
        w.post(self.frame, w.WM_COMMAND, cmd_id)
        if verify:
            return w.wait_until(verify, timeout)
        time.sleep(0.2)
        return None

    def cmd(self, name: str, **kw):
        if name not in CMD:
            raise KeyError("unknown command alias %r (see CMD)" % name)
        return self.command(CMD[name], **kw)

    # --------------------------------------------------------------- controls
    def children(self, root=None):
        root = self.frame if root is None else root
        return [Control(h, self) for h in w.enum_children(root)]

    def find(self, cls=None, cid=None, text=None, visible=None, root=None):
        res = []
        for c in self.children(root):
            if cls and not c.cls.startswith(cls):
                continue
            if cid is not None and c.cid != cid:
                continue
            if text and text not in c.text:
                continue
            if visible is not None and c.visible != visible:
                continue
            res.append(c)
        return res

    def one(self, cls=None, cid=None, text=None, visible=None):
        r = self.find(cls, cid, text, visible)
        if not r:
            raise LookupError("control not found cls=%r cid=%r text=%r" % (cls, cid, text))
        return r[0]

    def toolbars(self):
        return [c for c in self.children() if c.cls.startswith("Afx:ToolBar")]

    def toolbar(self, name):
        for c in self.toolbars():
            if c.text == name:
                return c
        return None

    def toolbar_buttons(self, tb):
        """[(index, command_id, state)] from TB_GETBUTTON (needs a remote buffer)."""
        n = w.send(tb.hwnd, w.TB_BUTTONCOUNT)
        size = 40  # sizeof(TBBUTTON) on win32
        buf = self.remote.alloc(size)
        out = []
        try:
            for i in range(n):
                if not w.send(tb.hwnd, w.TB_GETBUTTON, i, buf):
                    continue
                raw = self.remote.read(buf, size)
                _bitmap, cmd_id, state, style = struct.unpack_from("<iiBB", raw, 0)
                out.append((i, cmd_id, state))
        finally:
            self.remote.free(buf)
        return out

    # --------------------------------------------------------------- treeview
    def tree(self):
        """The **project** tree.

        H3U projects expose it as control id 1, but an H5U project puts the *device catalog*
        in id 1 and the project in **id 2** (877 catalog rows vs 100 project rows on the real
        machine project).  Pick by root text instead: the project tree's root names the
        project (`<name> [H5U]`), while the catalog's root is ``EtherCAT Devices``.
        """
        candidates = self.find("SysTreeView32")
        if not candidates:
            return None
        project_name = self.project_name or ""
        best, best_score = None, -1
        for candidate in candidates:
            score = 0
            try:
                root = w.send(candidate.hwnd, w.TVM_GETNEXTITEM, w.TVGN_ROOT, 0)
                text, _kids, _expanded = self._tree_item_info(root, candidate)
            except Exception:  # noqa: BLE001 - a tree we cannot read scores zero
                text = ""
            if text and "EtherCAT" not in text:
                score += 3
            if project_name and text and project_name in text:
                score += 4
            if candidate.cid == 1:
                score += 1
            if score > best_score:
                best, best_score = candidate, score
        return best

    def tree_expand_all(self, tree=None, max_items=4000):
        """Expand every node through ``TVM_EXPAND`` (no keyboard needed).

        A collapsed node has no meaningful ``TVM_GETITEMRECT`` result, so rows must
        be revealed before they can be clicked (a freshly copied project opens
        collapsed).  TVM_EXPAND works cross-process, unlike the arrow keys.
        """
        tree = tree or self.tree()
        if not tree:
            return 0
        expanded = 0
        stack = []
        root = w.send(tree.hwnd, w.TVM_GETNEXTITEM, w.TVGN_ROOT, 0)
        while root:
            stack.append(root)
            root = w.send(tree.hwnd, w.TVM_GETNEXTITEM, w.TVGN_NEXT, root)
        seen = 0
        while stack and seen < max_items:
            hitem = stack.pop()
            seen += 1
            child = w.send(tree.hwnd, w.TVM_GETNEXTITEM, w.TVGN_CHILD, hitem)
            if not child:
                continue
            w.send(tree.hwnd, 0x1102, 2, hitem)       # TVM_EXPAND / TVE_EXPAND
            expanded += 1
            while child:
                stack.append(child)
                child = w.send(tree.hwnd, w.TVM_GETNEXTITEM, w.TVGN_NEXT, child)
        time.sleep(0.4)
        return expanded

    def tree_items(self, tree=None):
        """Depth-first ``[(depth, text, n_children, hitem)]`` of the project tree.

        ``TVITEMW`` is marshalled by hand in the *target* (win32) layout: a
        64-bit ctypes structure would have the wrong size and be rejected.
        """
        return [(d, t, c, h) for d, t, c, h, _e in self._tree_walk(tree)]

    def _tree_walk(self, tree=None):
        """``[(depth, text, children, hitem, expanded)]`` in display order."""
        tree = tree or self.tree()
        if not tree:
            return []
        item_size = 40
        buf = self.remote.alloc(item_size + 2048)
        text_ptr = buf + item_size
        out = []
        mask = w.TVIF_TEXT | w.TVIF_CHILDREN | w.TVIF_HANDLE | w.TVIF_STATE

        def read(hitem, depth):
            packed = struct.pack("<IIIIIIiiii", mask, hitem, 0, 0x0020, text_ptr, 1024, 0, 0, 0, 0)
            self.remote.write(buf, packed)
            text = ""
            children = -1
            expanded = False
            if w.send(tree.hwnd, w.TVM_GETITEMW, 0, buf):
                raw = self.remote.read(buf, item_size)
                (_mask, _h, state, _sm, _pt, _cch, _img, _sel,
                 children, _lp) = struct.unpack("<IIIIIIiiii", raw)
                expanded = bool(state & 0x0020)   # TVIS_EXPANDED
                text = self.remote.read(text_ptr, 2048).decode("utf-16-le", "replace").split("\x00")[0]
            out.append((depth, text, children, hitem, expanded))
            child = w.send(tree.hwnd, w.TVM_GETNEXTITEM, w.TVGN_CHILD, hitem)
            while child:
                read(child, depth + 1)
                child = w.send(tree.hwnd, w.TVM_GETNEXTITEM, w.TVGN_NEXT, child)

        root = w.send(tree.hwnd, w.TVM_GETNEXTITEM, w.TVGN_ROOT, 0)
        while root:
            read(root, 0)
            root = w.send(tree.hwnd, w.TVM_GETNEXTITEM, w.TVGN_NEXT, root)
        self.remote.free(buf)
        return out

    def _tree_item_info(self, hitem, tree=None):
        """(text, has_children, expanded) for one hitem."""
        tree = tree or self.tree()
        buf = self.remote.alloc(60 + 1024)
        text_ptr = buf + 60
        try:
            mask = w.TVIF_TEXT | w.TVIF_HANDLE | w.TVIF_STATE
            packed = struct.pack("<IIIIIIiiii", mask, hitem, 0, 0x0020, text_ptr, 512, 0, 0, 0, 0)
            self.remote.write(buf, packed)
            if not w.send(tree.hwnd, w.TVM_GETITEMW, 0, buf):
                return "", False, False
            raw = self.remote.read(buf, 40)
            _mask, _h, state = struct.unpack_from("<III", raw, 0)
            text = self.remote.read(text_ptr, 1024).decode("utf-16-le", "replace").split("\x00")[0]
            has_kids = bool(w.send(tree.hwnd, w.TVM_GETNEXTITEM, w.TVGN_CHILD, hitem))
            return text, has_kids, bool(state & 0x0020)
        finally:
            self.remote.free(buf)

    def tree_visible(self, tree=None):
        """``[(row, depth, text, hitem)]`` for the rows a user can see right now."""
        tree = tree or self.tree()
        if not tree:
            return []
        rows = []

        def visit(hitem, depth):
            while hitem:
                text, kids, expanded = self._tree_item_info(hitem, tree)
                rows.append((len(rows), depth, text, hitem))
                if kids and expanded:
                    visit(w.send(tree.hwnd, w.TVM_GETNEXTITEM, w.TVGN_CHILD, hitem), depth + 1)
                hitem = w.send(tree.hwnd, w.TVM_GETNEXTITEM, w.TVGN_NEXT, hitem)

        visit(w.send(tree.hwnd, w.TVM_GETNEXTITEM, w.TVGN_ROOT, 0), 0)
        return rows

    def tree_hit_test(self, x, y, tree=None):
        """``TVM_HITTEST``: which hitem sits at client ``(x, y)`` (0 if none)."""
        tree = tree or self.tree()
        buf = self.remote.alloc(24)
        try:
            self.remote.write(buf, struct.pack("<iiII", x, y, 0, 0))
            w.send(tree.hwnd, 0x1112, 0, buf)          # TVM_HITTEST
            _pt_x, _pt_y, _flags, hitem = struct.unpack("<iiII", self.remote.read(buf, 16))
            return hitem
        finally:
            self.remote.free(buf)

    def tree_item_rect(self, hitem, tree=None, code=0):
        """Client rect of a tree row via ``TVM_GETITEMRECT``.

        The message needs a *remote* RECT whose ``left`` field carries the hitem;
        with a local pointer it returns 0 (which is why row geometry looked
        unavailable).  ``code`` 0 = whole row, 1 = label only.
        """
        tree = tree or self.tree()
        buf = self.remote.alloc(16)
        try:
            self.remote.write(buf, struct.pack("<IIII", hitem, 0, 0, 0))
            if not w.send(tree.hwnd, 0x1104, code, buf):
                return None
            return struct.unpack("<iiii", self.remote.read(buf, 16))
        finally:
            self.remote.free(buf)

    def tree_caret(self, tree=None):
        """Text of the tree's caret item (needs no geometry)."""
        tree = tree or self.tree()
        if not tree:
            return None
        hitem = w.send(tree.hwnd, w.TVM_GETNEXTITEM, w.TVGN_CARET, 0)
        if not hitem:
            return None
        buf = self.remote.alloc(60 + 1024)
        text_ptr = buf + 60
        try:
            packed = struct.pack("<IIIIIIiiii", w.TVIF_TEXT | w.TVIF_HANDLE, hitem, 0, 0,
                                 text_ptr, 512, 0, 0, 0, 0)
            self.remote.write(buf, packed)
            if not w.send(tree.hwnd, w.TVM_GETITEMW, 0, buf):
                return None
            return self.remote.read(text_ptr, 1024).decode("utf-16-le", "replace").split("\x00")[0]
        finally:
            self.remote.free(buf)

    def tree_flat(self):
        """Project-only view of the tree (drops the 指令集 instruction catalog)."""
        return [(d, t) for d, t, _c, _h in self.tree_items() if not self._in_instruction_set(t)]

    def _in_instruction_set(self, _text):
        return False

    def tree_select(self, text, tree=None):
        tree = tree or self.tree()
        for _d, t, _c, hitem in self.tree_items(tree):
            if t == text or (t and text in t):
                w.send(tree.hwnd, w.TVM_SELECTITEM, w.TVGN_CARET, hitem)
                return hitem
        return None

    def tree_open(self, text, tree=None, timeout=12.0):
        """Open a tree entry with a real double click at its exact row.

        Keyboard navigation is *not* reliable here: the app never moves the
        ``TVGN_CARET`` item when arrow keys are sent (verified: posts and real
        keystrokes both leave the caret on the root), while a click does move it.
        The row geometry comes from ``TVM_GETITEMRECT`` after ``TVM_ENSUREVISIBLE``,
        so no font-size or scrolling assumptions are needed.
        """
        from . import input as inp
        tree = tree or self.tree()
        if not tree:
            raise LookupError("project tree not found")
        items = self.tree_items(tree)
        exact = [h for _d, t, _c, h in items if t == text]
        loose = [h for _d, t, _c, h in items if t and text in t]
        hits = exact or loose
        if not hits:
            raise LookupError("tree entry %r not found" % text)

        before = {h for h, _t in self.documents()}
        time.sleep(0.3)                      # let a freshly opened tree settle
        self.tree_expand_all(tree)           # rows must exist before they can be clicked
        hitem = hits[0]
        w.send(tree.hwnd, 0x1114, 0, hitem)              # TVM_ENSUREVISIBLE
        time.sleep(0.3)
        self.activate()
        time.sleep(0.2)

        for attempt in range(4):
            rect = self.tree_item_rect(hitem, tree)
            if not rect:
                break
            left, top, right, bottom = rect
            cx = (left + right) // 2
            cy = (top + bottom) // 2
            inp.click_client(tree.hwnd, cx, cy, count=2)
            time.sleep(1.0)
            new = [h for h, _t in self.documents() if h not in before]
            caret = self.tree_caret(tree)
            if caret == text or (caret and text in caret):
                if new:
                    return new[-1]
                if ("[" + text) in self.title:
                    return self.active_doc_hwnd()
                return None
            # the row landed elsewhere: use the caret's own rect to learn the offset
            caret_item = w.send(tree.hwnd, w.TVM_GETNEXTITEM, w.TVGN_CARET, 0)
            caret_rect = self.tree_item_rect(caret_item, tree) if caret_item else None
            if not caret_rect:
                break
            delta = top - caret_rect[1]
            if delta == 0:
                break
            print("tree_open: row off by %d px (caret=%r), retrying" % (delta, caret))
        return None

        # already open somewhere: activate it
        for h, t in self.documents():
            if t == text or t.startswith(text):
                self.activate_document(t)
                return h
        return None

    # --------------------------------------------------------------- output
    def output_tabs(self):
        return self.find("ListBox")

    def output_box(self):
        boxes = [b for b in self.output_tabs() if b.visible]
        return boxes[0] if boxes else (self.output_tabs() or [None])[0]

    @staticmethod
    def _last_paint_group(lines):
        """Collapse the paint stream into one ordered line list.

        The pane both appends incrementally and occasionally repaints every row,
        so lines can repeat; keeping the first occurrence preserves the real
        message order (verified against the 编译 / 转换 panes).
        """
        seen = set()
        out = []
        for line in lines:
            if line in seen:
                continue
            seen.add(line)
            out.append(line)
        return out

    @staticmethod
    def _pane_block(lines):
        """Keep the last message block of the output pane (header .. summary).

        The pane is painted through a helper window whose handle we cannot
        predict, so messages are selected by their content: a block starts at
        the ``---- AutoShop : ... 消息 ----`` header and runs to the next header.
        """
        blocks = []
        current = None
        for line in lines:
            if line.startswith("----") and "AutoShop" in line:
                if current:
                    blocks.append(current)
                current = [line]
            elif current is not None:
                if current[-1] != line:
                    current.append(line)
        if current:
            blocks.append(current)
        if blocks:
            block = blocks[-1]
            for i, line in enumerate(block):
                if "统计 -" in line:
                    block = block[: i + 1]
                    break
            return block
        # no header yet: fall back to lines that look like diagnostics
        keep = ("错误", "警告", "统计", "开始", "完成", "转换", "编译", "生成", ".LD", ".IL")
        return [l for l in lines if any(k in l for k in keep)]

    def output_lines(self, wait=0.9):
        """Read the information/output pane by capturing what it paints."""
        box = self.output_box()
        if not box:
            return []
        from .hooks import TextTap
        with TextTap(self.pid) as tap:
            tap.repaint(box.hwnd, wait)
            self.force_repaint(box.hwnd)
            time.sleep(wait)
            raw = tap.lines()
        if not raw:
            return []
        return self._pane_block(self._last_paint_group(raw))

    def compile(self, all_programs=True, timeout=90.0):
        """Run 编译 / 全部编译 and return the messages it produced.

        Returns ``(ok, lines)`` where ``ok`` means a 统计 (summary) line was seen
        without a 错误 (error) line.
        """
        from .hooks import TextTap
        box = self.output_box()
        hwnds = [box.hwnd] if box else None
        cmd_id = CMD["compile_all" if all_programs else "compile"]
        with TextTap(self.pid) as tap:
            time.sleep(0.3)
            w.post(self.frame, w.WM_COMMAND, cmd_id)
            tap.wait_for(lambda ls: any("统计" in l for l in ls), timeout=timeout)
            time.sleep(0.5)
            lines = self._pane_block(self._last_paint_group(tap.lines()))
        ok = any("统计" in l for l in lines) and not any(l.strip().startswith("错误") for l in lines)
        return ok, lines

    def statusbar(self):
        for c in self.children():
            if c.cls.startswith("Afx:StatusBar"):
                buf = self.remote.alloc(2048)
                try:
                    texts = []
                    for i in range(6):
                        w.send(c.hwnd, w.SB_GETTEXTW, i, buf)
                        data = self.remote.read(buf, 2048).decode("utf-16-le", "replace")
                        t = data.split("\x00")[0]
                        if t:
                            texts.append(t)
                    return texts
                finally:
                    self.remote.free(buf)
        return []

    # ------------------------------------------------------------- documents
    def mdi_client(self):
        r = self.find("MDIClient")
        return r[0] if r else None

    def documents(self):
        mc = self.mdi_client()
        if not mc:
            return []
        out = []
        for h in w.enum_children(mc.hwnd):
            t = w.window_text(h)
            if t and w.class_name(h).startswith("Afx:"):
                out.append((h, t))
        return out

    def activate_document(self, title, tries=None):
        """Activate a document by cycling the MDI tab bar with Ctrl+Tab.

        ``WM_MDIACTIVATE`` is accepted by the MDI client but does not change the
        visible document in this app (it uses a tabbed MDI), so we cycle tabs
        with genuine keystrokes until the frame title matches.
        """
        from . import input as inp
        name = title.strip().rstrip("*").strip()
        for h, t in self.documents():
            if t.strip().rstrip("*").strip() == name and ("[" + name + "]") in self.title:
                return h
        self.activate()
        time.sleep(0.2)
        n = tries if tries is not None else max(4, len(self.documents()) + 2)
        for _ in range(n):
            inp.chord(["ctrl"], "tab")
            time.sleep(0.45)
            for h, t in self.documents():
                if t.strip().rstrip("*").strip() == name and ("[" + name) in self.title:
                    return h
        return None

    def active_document(self):
        for h, t in self.documents():
            if self.title.rstrip().endswith("[" + t + "]") or ("[" + t + "]") in self.title:
                return h, t
        return (self.documents() or [(None, None)])[0]

    def active_doc_hwnd(self):
        """MDI child window whose title is the one in brackets in the frame title."""
        import re
        m = re.search(r"\[([^\]]+)\]", self.title)
        if m:
            name = m.group(1).strip().rstrip("*").strip()
            for h, t in self.documents():
                if t.strip().rstrip("*").strip() == name:
                    return h
        return None

    def scintilla(self, doc=None, allow_fallback=True):
        """Instruction-list editor of a document (default: the active one).

        ``allow_fallback=False`` refuses to return an editor that belongs to another
        document.  That matters for correctness: with several programs open, a
        process-wide search returns whichever Scintilla is first, so a read that looked
        successful could hand back *another program's* text (this happened with the
        monitor document active — see ``docs/RECON.md`` §4).
        """
        doc = doc or self.active_doc_hwnd()
        if doc:
            for c in self.children(doc):
                if c.cls == "Scintilla":
                    return c
        if not allow_fallback:
            return None
        cands = self.find("Scintilla")
        vis = [c for c in cands if c.visible]
        return (vis or cands or [None])[0]

    def program_il(self, strict=False):
        """Full instruction-list text of the active document (None if absent).

        ``strict=True`` only accepts an editor that belongs to the active document.
        """
        sci = self.scintilla(allow_fallback=not strict)
        if not sci:
            return None
        w.send(sci.hwnd, 2006)  # SCI_GETLENGTH
        length = w.send(sci.hwnd, 2182)  # SCI_GETTEXTLENGTH
        w.send(sci.hwnd, 2013, 0, 0)     # SCI_SELECTALL
        buf = self.remote.alloc(max(length, 1) + 16)
        try:
            n = w.send(sci.hwnd, 2161, 0, buf)  # SCI_GETSELTEXT
            if n <= 0:
                return ""
            return self.remote.read(buf, n).decode("utf-8", "replace")
        finally:
            self.remote.free(buf)

    def set_program_il(self, text, timeout=6.0, retries=3):
        """Replace the instruction list through a real select-all + paste.

        ``SCI_SETTEXT`` changes the buffer but the document model never learns
        about it, so AutoShop keeps the old program and never converts (verified:
        the text appears on screen, the compiler still uses the old code).
        Pasting genuine input makes the app reformat the text and convert it.

        The paste is verified by reading the buffer back, because focus can be
        stolen (for example when another window activates) and the keystrokes
        would then land nowhere.
        """
        from . import input as inp

        # never paste into another document's editor: the search must stay scoped
        if not self.scintilla(allow_fallback=False):
            self.view_il()          # the IL editor only exists in that view
        if not self.scintilla(allow_fallback=False):
            raise LookupError("no instruction-list editor in the active document")

        def normalized(value):
            return " ".join((value or "").replace("\t", " ").split())

        want = normalized(text)
        last = ""
        for attempt in range(retries):
            sci = self.scintilla()
            if not sci:
                raise LookupError("no instruction-list editor in the active document")
            self.activate()
            time.sleep(0.25)
            inp.set_clipboard(text)
            inp.click_client(sci.hwnd, 40, 20 + attempt)
            time.sleep(0.3)
            inp.chord(["ctrl"], "a")
            time.sleep(0.2)
            inp.chord(["ctrl"], "v")
            end = time.time() + timeout
            while time.time() < end:
                time.sleep(0.2)
                last = self.program_il() or ""
                if normalized(last).startswith(want[:40]) or want[:40] in normalized(last):
                    return w.send(sci.hwnd, 2182)
            time.sleep(0.3)
        return w.send(self.scintilla().hwnd, 2182)

    def view_il(self):
        """Switch the active document to the instruction-list editor.

        Measured on V4.11.0.5: an **H3U** program document already owns a ``Scintilla``, and
        this command is the 梯形图⇄指令表 switch.  An **H5U** program is stored as ``.LD``
        (a graph) and offers only 梯形图(LD) / 结构化文本(LiteST); issuing this command there
        creates no editor and no document — the IL only exists as a compile product
        (``il_log.log`` / ``Compile/*.compile``), so read it with :mod:`autoshopkit.projectfile`.
        """
        w.post(self.frame, w.WM_COMMAND, CMD["view_il"])
        time.sleep(1.2)
        return self.scintilla()

    def view_ladder(self):
        w.post(self.frame, self.WM_COMMAND if hasattr(self, "WM_COMMAND") else w.WM_COMMAND,
               CMD["view_ladder"])
        time.sleep(1.5)


    # ------------------------------------------------------------- symbols
    # Fallbacks measured with UIA on a 96-dpi-equivalent layout; the real values
    # are derived from the grid's header cells at runtime (symbol_columns).
    SYMBOL_TAB = (60, 28)            # 自定义元件 sheet tab (grid client coords)
    SYMBOL_COL_X = (107, 200, 643)   # 符号 / 地址 / 注释 centres
    SYMBOL_ROW0_Y = 26               # first data row centre
    SYMBOL_ROW_PITCH = 17

    def symbol_grid(self):
        """The grid of the 符号表 document, identified by its header cells.

        Checked by headers (``符号``) so it can never return the monitor grid, which is
        hosted in the same kind of ``#32770`` window.
        """
        def lookup(doc):
            if not doc:
                return None
            for control in self.children(doc):
                if control.cls != "VSFlexGrid8N":
                    continue
                if self.grid_layout(control, ("符号", "地址")):
                    return control
            return None

        grid = lookup(self.active_doc_hwnd())
        if grid is None:
            self.tree_open("符号表")
            time.sleep(1.0)
            grid = lookup(self.active_doc_hwnd())
        return grid

    def grid_layout(self, grid, headers):
        """Measure a ``VSFlexGrid8N``: header x positions and the first row / pitch.

        UI Automation exposes the grid's header cells and its ``Row N`` items with real
        bounding rectangles, so column centres and row pitch are measured instead of
        guessed.  Returns ``(col_x, row0, pitch)`` in the grid's client coordinates, or
        ``None`` when UIA cannot see the grid.
        """
        if not grid:
            return None
        try:
            from . import uia
            element = uia.from_handle(grid.hwnd)
            if element is None:
                return None
            gl, gt, _gr, _gb = grid.rect
            columns, rows = {}, []
            for child in uia.children(element):
                try:
                    name = (child.CurrentName or "").strip()
                    rect = child.CurrentBoundingRectangle
                except Exception:
                    continue
                if not name:
                    continue
                cx = (rect.left + rect.right) // 2 - gl
                cy = (rect.top + rect.bottom) // 2 - gt
                for header in headers:
                    if name == header:
                        columns[header] = cx
                if name.startswith("Row ") and name != "Row 0":
                    rows.append(cy)
        except Exception:
            return None
        if not columns or not rows:
            return None
        ordered = [columns[h] for h in headers if h in columns]
        rows.sort()
        pitch = rows[1] - rows[0] if len(rows) > 1 else self.SYMBOL_ROW_PITCH
        return tuple(ordered), rows[0], pitch

    def symbol_columns(self):
        """``(col_x, row0_y, row_pitch)`` derived from UIA header rectangles.

        The grid exposes its header cells and ``Row N`` items through UI Automation
        (each with a real bounding rectangle), which turns the earlier pixel
        guessing into measurement.  Falls back to the class defaults when UIA is
        unavailable.
        """
        try:
            from . import uia
        except Exception:
            return self.SYMBOL_COL_X, self.SYMBOL_ROW0_Y, self.SYMBOL_ROW_PITCH
        grid = self.symbol_grid()
        if not grid:
            return self.SYMBOL_COL_X, self.SYMBOL_ROW0_Y, self.SYMBOL_ROW_PITCH
        try:
            root = uia.from_handle(self.frame)
            element = uia.find_first(root, class_name="VSFlexGrid8N")
            if element is None:
                return self.SYMBOL_COL_X, self.SYMBOL_ROW0_Y, self.SYMBOL_ROW_PITCH
            gl, gt, _gr, _gb = grid.rect
            columns, rows = {}, []
            for child in uia.children(element):
                try:
                    name = (child.CurrentName or "").strip()
                    rect = child.CurrentBoundingRectangle
                except Exception:
                    continue
                if not name:
                    continue
                cx = (rect.left + rect.right) // 2 - gl
                cy = (rect.top + rect.bottom) // 2 - gt
                if name in ("符号", "地址", "注释"):
                    columns[name] = cx
                elif name.startswith("Row ") and name != "Row 0":
                    rows.append(cy)
        except Exception:
            return self.SYMBOL_COL_X, self.SYMBOL_ROW0_Y, self.SYMBOL_ROW_PITCH
        col_x = (columns.get("符号", self.SYMBOL_COL_X[0]),
                 columns.get("地址", self.SYMBOL_COL_X[1]),
                 columns.get("注释", self.SYMBOL_COL_X[2]))
        row0 = min(rows) if rows else self.SYMBOL_ROW0_Y
        pitch = (sorted(rows)[1] - sorted(rows)[0]) if len(rows) > 1 else self.SYMBOL_ROW_PITCH
        return col_x, row0, pitch

    def cell_value(self, grid, x, y, timeout=1.5):
        """Read one grid cell: click it, press F2 (edit without changing), read UIA.

        Clicking alone does not open the in-cell editor (only a keystroke does), and
        ``F2`` enters edit mode *without* touching the content, so the editor's
        ``ValuePattern`` then reports the committed value.
        """
        from . import input as inp
        try:
            from . import uia
        except Exception:
            return None
        self.activate()
        time.sleep(0.15)
        inp.click_client(grid.hwnd, x, y)
        time.sleep(0.3)
        w.post(grid.hwnd, 0x0100, 0x71, 0)      # WM_KEYDOWN VK_F2
        w.post(grid.hwnd, 0x0101, 0x71, 0)
        time.sleep(0.35)
        element = uia.editor_element_in(grid.hwnd, timeout=timeout)
        value = uia.value_of(element) if element else None
        inp.key("escape")
        time.sleep(0.2)
        return value

    def read_symbol(self, row=0):
        """Read back one 符号表 row as ``{"symbol", "address", "note"}``."""
        grid = self.symbol_grid()
        if not grid:
            raise LookupError("符号表 grid not found")
        col_x, row0, pitch = self.symbol_columns()
        y = row0 + row * pitch
        keys = ("symbol", "address", "note")
        return {key: self.cell_value(grid, x, y) for key, x in zip(keys, col_x)}

    def symbols(self, source="auto"):
        """The project's global symbol table.

        ``source="file"`` reads the saved ``VarList.gdt`` (instant, exact framing —
        see :mod:`autoshopkit.projectfile`), ``"ui"`` walks the grid cell by cell
        (≈6 s/row), and ``"auto"`` prefers the file and falls back to the grid when
        the file has no symbols (for example before the first save).
        """
        from . import projectfile
        if source in ("auto", "file"):
            rows = projectfile.read_symbols(self.project_path) if self.project_path else []
            if rows or source == "file":
                return rows
        return self.read_symbols()

    def read_symbols(self, max_rows=40):
        """Enumerate the 自定义元件 sheet until a row has no 符号.

        Each row costs three cell reads (click + F2 + UIA), so this is exact but not
        instant; ``max_rows`` bounds the walk.  Rows whose 符号 cell is empty end the
        scan (the sheet is contiguous in practice).
        """
        out = []
        for row in range(max_rows):
            values = self.read_symbol(row=row)
            if not (values.get("symbol") or "").strip():
                break
            out.append(values)
        return out

    def add_symbol(self, name, address, note="", row=0):
        """Add one user symbol on the 自定义元件 sheet of 符号表.

        The grid is a Visual Studio FlexGrid ActiveX: cells hold no window text and
        the app rejects ``WM_SETTEXT`` on the in-cell editor.  What works (verified):

        * click the sheet tab (client ``(60, 28)``) to select 自定义元件;
        * click the cell, post ``WM_CHAR`` to the grid so the in-cell editor opens;
        * write the text through **UIA ``ValuePattern``** on the editor element
          (class ``ATL:697A8F20``) and commit by clicking the next cell.

        Returns True when all three cells accepted the value.
        """
        self._dismiss_all()
        self.wait_idle(30)
        grid = self.symbol_grid()
        if not grid:
            raise LookupError("符号表 grid not found")
        grid_rect = self.grid_rect(grid) if hasattr(self, "grid_rect") else None
        from . import input as inp
        try:
            from . import uia
        except Exception:
            uia = None
        if uia is None:
            raise RuntimeError("UI Automation (comtypes) is required for symbol writes")
        col_x, row0, pitch = self.symbol_columns()
        self.activate()
        self.focus_window(grid.hwnd)
        time.sleep(0.2)
        inp.click_client(grid.hwnd, self.SYMBOL_TAB[0], self.SYMBOL_TAB[1])
        time.sleep(0.5)
        y = row0 + row * pitch
        ok_all = True
        for x, text in zip(col_x, (name, address, note)):
            if not text:
                continue
            inp.click_client(grid.hwnd, x, y)
            time.sleep(0.3)
            w.post(grid.hwnd, 0x0102, ord(" "), 1)
            time.sleep(0.3)
            element = uia.editor_element_in(grid.hwnd)
            ok = bool(element and uia.set_value(element, text))
            ok_all = ok_all and ok
            time.sleep(0.2)
        # commit the last cell and the row, then leave no editor open
        inp.click_client(grid.hwnd, col_x[0], y + pitch * 2)
        time.sleep(0.3)
        inp.key("enter")
        time.sleep(0.3)
        inp.key("escape")          # a lingering in-cell editor eats the next click
        time.sleep(0.3)
        return ok_all

    # ------------------------------------------------------------ download
    def wait_idle(self, timeout=45.0):
        """Wait until no dialog is open and the frame is enabled.

        A modal AutoShop dialog (including the progress windows it shows during
        compile) disables its owner, so ``IsWindowEnabled(frame)`` is a reliable
        "busy" flag - posting a command while busy silently does nothing.
        """
        end = time.time() + timeout
        while time.time() < end:
            if not self.dialogs() and w.user32.IsWindowEnabled(self.frame):
                return True
            time.sleep(0.4)
        return not self.dialogs() and bool(w.user32.IsWindowEnabled(self.frame))

    def _dismiss_all(self, tries=6):
        """Close every dialog of this process, falling back to Escape."""
        from . import input as inp
        for _ in range(tries):
            ds = self.dialogs()
            if not ds:
                return True
            h = ds[0]
            done = False
            for c in self.dialog_controls(h):
                if c.cls == "Button" and c.text in ("关闭", "取消", "否(&N)"):
                    w.post(c.hwnd, w.BM_CLICK, 0, 0)
                    done = True
                    break
            if not done:
                w.user32.BringWindowToTop(h)
                w.user32.SetForegroundWindow(h)
                time.sleep(0.3)
                inp.key("esc")
            time.sleep(0.8)
        return not self.dialogs()

    def generate_download_file(self, target_path=None, timeout=90.0):
        """PLC → 生成下载文件: write the offline ``*.updown`` artefact.

        Verified flow (no PLC needed):

        1. ``生成下载文件`` (33186) opens the 下载选项 dialog;
        2. 生成文件 (id 1436) opens the Windows *shell* 另存为 dialog;
        3. the shell dialog only reacts to genuine typing **in its filename
           field** (which has focus when it opens): ``WM_SETTEXT`` on the edit,
           ``BM_CLICK`` on 保存, ``WM_COMMAND(IDOK)``, Enter and Alt+S are all
           ignored -- Ctrl+A + paste + Enter works;
        4. AutoShop reports ``生成文件成功！`` and writes
           ``<project>\\<name>.updown.down``.

        ``target_path`` moves the produced file afterwards.  Returns
        ``(ok, path)``.
        """
        import glob
        import os
        import shutil

        from . import input as inp

        self._dismiss_all()
        self.wait_idle(45)
        time.sleep(0.4)
        start_time = time.time()
        project = self.project_path
        before = set(glob.glob(os.path.join(project, "**", "*"), recursive=True))
        hdlg = None
        for _attempt in range(4):
            self.wait_idle(20)
            w.post(self.frame, w.WM_COMMAND, CMD["make_download_file"])
            hdlg = self.dialog("下载选项", timeout=12)
            if hdlg:
                break
            self._dismiss_all()
            time.sleep(1.5)
        if not hdlg:
            raise LookupError("下载选项 dialog did not appear")
        ctrls = {c.cid: c for c in self.dialog_controls(hdlg) if c.cid}
        if 1436 not in ctrls:
            self.close_dialogs()
            raise LookupError("下载选项 dialog has no 生成文件 button")
        time.sleep(0.4)
        w.post(ctrls[1436].hwnd, w.BM_CLICK, 0, 0)

        savedlg = None
        for _ in range(30):
            time.sleep(0.5)
            for h in self.dialogs():
                if w.window_text(h) != "另存为":
                    continue
                if any(c.cls == "Edit" for c in self.dialog_controls(h)):
                    savedlg = h
                    break
            if savedlg:
                break
        if not savedlg:
            self.close_dialogs()
            return False, None

        # Only genuine keystrokes in the filename field are honoured: WM_SETTEXT
        # on the edit, BM_CLICK on 保存, WM_COMMAND(IDOK), Enter and Alt+S are all
        # ignored by this shell dialog.  Click the bottom-most Edit (the filename
        # box), then Ctrl+A + paste + Enter, retrying while the dialog stays open.
        # typing the FULL path makes the shell dialog save exactly there; a plain
        # name would land in whatever folder the dialog used last time
        if target_path:
            desired = os.path.abspath(target_path)
        else:
            desired = os.path.join(project, os.path.basename(project.rstrip("\\")) + ".updown")
        name = desired
        for attempt in range(5):
            if not w.user32.IsWindow(savedlg):
                break
            w.user32.BringWindowToTop(savedlg)
            w.user32.SetForegroundWindow(savedlg)
            time.sleep(1.0)
            edits = [c for c in self.dialog_controls(savedlg) if c.cls == "Edit" and c.visible]
            if not edits:
                time.sleep(0.8)
                continue
            # the filename box is the lowest edit of the dialog
            target = max(edits, key=lambda c: c.rect[1])
            l, t, r, b = target.rect
            inp.click(x=(l + r) // 2, y=(t + b) // 2)
            time.sleep(0.35)
            # prove the field really has focus before pasting
            before_len = w.send(target.hwnd, 0x000E)
            inp._type_unicode("q")
            time.sleep(0.25)
            focused = w.send(target.hwnd, 0x000E) != before_len
            if focused:
                w.post(target.hwnd, 0x0102, 8, 1)   # undo the probe character
                time.sleep(0.2)
            inp.set_clipboard(name)
            time.sleep(0.2)
            inp.chord(["ctrl"], "a")
            time.sleep(0.2)
            inp.chord(["ctrl"], "v")
            time.sleep(0.6)
            inp.key("enter")
            time.sleep(1.5)
            if not w.user32.IsWindow(savedlg):
                break

        ok = False
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.6)
            for h in self.dialogs():
                if w.window_text(h) != "AutoShop":
                    continue
                texts = [c.text for c in self.dialog_controls(h) if c.text]
                if any("生成文件成功" in t for t in texts):
                    ok = True
                for c in self.dialog_controls(h):
                    if c.cls == "Button" and c.text == "确定":
                        w.post(c.hwnd, w.BM_CLICK, 0, 0)
                if ok:
                    break
            if ok:
                break
        self._dismiss_all()
        time.sleep(0.6)

        produced = None
        cands = []
        for candidate in (desired, desired + ".down"):
            if os.path.exists(candidate) and os.path.getmtime(candidate) >= start_time - 2:
                cands.append(candidate)
        if not cands:
            after = set(glob.glob(os.path.join(project, "**", "*"), recursive=True))
            cands = [p for p in after if os.path.isfile(p)
                     and p.lower().endswith((".down", ".updown"))
                     and os.path.getmtime(p) >= start_time - 2]
        if cands:
            produced = max(cands, key=os.path.getmtime)
        if produced and os.path.abspath(produced) != os.path.abspath(desired):
            folder = os.path.dirname(desired)
            if folder:
                os.makedirs(folder, exist_ok=True)
            if os.path.exists(desired):
                os.remove(desired)
            shutil.move(produced, desired)
            produced = desired
        ok = bool(ok or (produced and os.path.exists(produced)))
        return ok, produced

    # ------------------------------------------------------------- text entry
    def type_chars(self, ctl, text, per_char=0.012):
        """Type into a control with WM_CHAR, which needs no focus.

        Several AutoShop dialog edits ignore ``WM_SETTEXT`` *and* real clicks
        (verified on the 新建工程 dialog: ``WM_SETTEXT`` returns 0 and even a
        focused synthetic click does not move the caret), yet they do process
        ``WM_CHAR`` -- the text length grows and the field renders the characters.
        """
        for ch in text:
            w.post(ctl.hwnd, 0x0102, ord(ch), 1)
            time.sleep(per_char)

    def clear_chars(self, ctl, count=120, per_char=0.006):
        for _ in range(count):
            w.post(ctl.hwnd, 0x0102, 8, 1)   # WM_CHAR backspace
            time.sleep(per_char)

    def set_combo_index(self, hdlg, ctl, index, notify=0x0001):
        """Select a combo item and tell the dialog about it.

        ``CB_SETCURSEL`` changes the selection but sends **no** ``CBN_SELCHANGE``,
        so an MFC handler never runs (verified: every series index still produced
        an H3U project).  Posting ``WM_COMMAND(CBN_SELCHANGE)`` to the dialog makes
        the app act on the new selection.
        """
        w.send(ctl.hwnd, 0x014E, index, 0)                       # CB_SETCURSEL
        time.sleep(0.1)
        w.post(hdlg, w.WM_COMMAND, (notify << 16) | (ctl.cid & 0xFFFF), ctl.hwnd)
        time.sleep(0.25)

    def new_project(self, name, dest_dir=None, editor_index=None, series_index=None,
                    model_index=None, timeout=40.0):
        """Create a project through 文件 → 新建工程 and return its folder.

        Verified behaviour of this dialog (V4.11.0.5):

        * the 工程名 / 保存路径 edits reject ``WM_SETTEXT`` and even real clicks,
          but they do process ``WM_CHAR``;
        * the app owns 保存路径: it recomputes ``<%USERPROFILE%>\\Documents\\<name>\\``
          whenever the name changes, and a typed path is discarded on 确定, so the
          project always lands in Documents;
        * 确定 asks ``文件夹已存在，是否覆盖原文件夹？`` when that folder exists.

        Because the destination is not honour-able through this dialog, the
        project is created in Documents and then *moved* to ``dest_dir`` (the
        project is closed first, so nothing holds the files).
        """
        import os
        import shutil

        self.close_dialogs()
        w.post(self.frame, w.WM_COMMAND, CMD["new_project"])
        end_t = time.time() + 10
        hdlg = None
        while time.time() < end_t and not hdlg:
            for h in self.dialogs():
                if w.window_text(h) == "新建工程":
                    hdlg = h
            time.sleep(0.25)
        if not hdlg:
            raise LookupError("新建工程 dialog did not appear")

        ctrls = {c.cid: c for c in self.dialog_controls(hdlg) if c.cid and c.cid > 0}
        if 1052 not in ctrls or 1 not in ctrls:
            raise LookupError("unexpected 新建工程 layout: %r" % sorted(ctrls))
        self.clear_chars(ctrls[1052], 60)
        self.type_chars(ctrls[1052], name)
        for cid, index in ((1046, editor_index), (2969, series_index), (1045, model_index)):
            if index is not None and cid in ctrls:
                self.set_combo_index(hdlg, ctrls[cid], index)
        time.sleep(0.6)
        w.post(ctrls[1].hwnd, w.BM_CLICK, 0, 0)

        deadline = time.time() + timeout
        project = None
        while time.time() < deadline:
            time.sleep(0.6)
            for h in self.dialogs():
                if w.window_text(h) == "AutoShop":
                    for c in self.dialog_controls(h):
                        if c.cls == "Button" and c.text == "是(&Y)":
                            w.post(c.hwnd, w.BM_CLICK, 0, 0)
                            time.sleep(0.6)
                            break
            if "[" in self.title and name in self.title:
                project = self.project_path
                break
        if not project:
            self.close_dialogs()
            return None

        if dest_dir:
            dest_dir = os.path.abspath(dest_dir)
            parent = os.path.dirname(project.rstrip("\\"))
            if os.path.normcase(parent) != os.path.normcase(os.path.normpath(dest_dir)):
                w.post(self.frame, w.WM_COMMAND, CMD["close_project"])
                for _ in range(40):
                    if "[" not in self.title:
                        break
                    for h in self.dialogs():
                        for c in self.dialog_controls(h):
                            if c.cls == "Button" and c.text == "否(&N)":
                                w.post(c.hwnd, w.BM_CLICK, 0, 0)
                    time.sleep(0.3)
                target = os.path.join(dest_dir, os.path.basename(project.rstrip("\\")))
                if os.path.isdir(target):
                    shutil.rmtree(target)
                os.makedirs(dest_dir, exist_ok=True)
                shutil.move(project.rstrip("\\"), target)
                project = target
        return project

    # ------------------------------------------------------------ monitor
    MONITOR_COLS = (107, 210, 310, 703)   # 元件名称 / 数据类型 / 显示格式 / 注释
    MONITOR_ROW0 = 26
    MONITOR_PITCH = 17

    def open_tree_child(self, parent_text, child_text=None, timeout=12.0):
        """Open (or activate) a child row of a tree folder, verified by its editor.

        ``元件监控表`` is a folder whose document is its ``MAIN`` child, and ``程序块`` is
        the folder that holds ``MAIN`` / ``SBR_001`` / ``INT_001``.  Two facts make this
        fiddly and are handled here:

        * a collapsed child row has no usable rect (``TVM_GETITEMRECT`` answers with the
          neighbour's rect), so the parent is expanded explicitly first;
        * a double click on a *folder* row toggles it instead of opening the child, so the
          row is selected and verified through the caret before the double click.

        With ``child_text`` the result is verified by the frame title **and** by the
        document owning an instruction-list editor (titles repeat: the 元件监控表 document
        is also called ``MAIN``).  Without it the first child is opened and success is
        judged by a new document handle.
        """
        from . import input as inp
        tree = self.tree()
        if not tree:
            return None
        inp.key("escape")
        time.sleep(0.2)
        self.tree_expand_all(tree)
        items = self.tree_items(tree)
        parent = target = None
        for index, (depth, text, _children, hitem) in enumerate(items):
            if text != parent_text:
                continue
            parent = hitem
            for child in items[index + 1:index + 6]:
                if child[0] <= depth:
                    break
                if child_text is None or child[1] == child_text:
                    target = child
                    break
            break
        if target is None:
            return None
        if parent:
            w.send(tree.hwnd, 0x1102, 2, parent)          # TVM_EXPAND / TVE_EXPAND
        w.send(tree.hwnd, 0x1114, 0, target[3])           # TVM_ENSUREVISIBLE
        time.sleep(0.6)
        before = {h for h, _t in self.documents()}
        self.activate()
        time.sleep(0.2)
        inp.click_client(tree.hwnd, 60, 10)               # first click focuses the pane
        time.sleep(0.35)

        def rect_of(hitem):
            return self.tree_item_rect(hitem, tree)

        def opened():
            """Success: the child's document is in front and has its own editor."""
            if child_text is None:
                new = [h for h, _t in self.documents() if h not in before]
                return new[-1] if new else None
            if "[" + child_text in self.title:
                self.view_il()
                if self.scintilla(allow_fallback=False):
                    return self.active_doc_hwnd()
            return None

        rect = rect_of(target[3])
        for _attempt in range(4):
            if not rect:
                break
            cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
            inp.click_client(tree.hwnd, cx, cy)          # select the row
            time.sleep(0.3)
            if self.tree_caret(tree) != target[1]:
                # the rect was stale: use the caret's own rect to learn the offset
                caret_hitem = w.send(tree.hwnd, w.TVM_GETNEXTITEM, w.TVGN_CARET, 0)
                caret_rect = rect_of(caret_hitem) if caret_hitem else None
                if caret_rect and caret_rect[1] != rect[1]:
                    cy += rect[1] - caret_rect[1]
                    inp.click_client(tree.hwnd, cx, cy)
                    time.sleep(0.3)
            if self.tree_caret(tree) != target[1]:
                rect = rect_of(target[3])
                continue
            inp.click_client(tree.hwnd, cx, cy, count=2)  # now open it
            end_at = time.time() + min(timeout, 4.0)
            while time.time() < end_at:
                found = opened()
                if found:
                    return found
                time.sleep(0.2)
            time.sleep(0.3)
            rect = rect_of(target[3])
        return None

    def open_program(self, name, timeout=12.0):
        """Open one program document from the 程序块 folder (unambiguous by name)."""
        return self.open_tree_child("程序块", name, timeout=timeout)

    def monitor_grid(self):
        """The grid of the 元件监控表 document, identified by its header cells.

        Both grid documents are hosted in a ``#32770`` (verified: 符号表's children are
        ``Afx:ToolBar…, Afx:DockPane…, #32770, VSFlexGrid8N, ATL:697A8F20``), so the
        *headers* are the only reliable discriminator: the monitor grid has
        ``元件名称 / 数据类型 / 显示格式 / 注释``, the symbol grid has ``符号 / 地址 / 注释``.
        """
        def lookup(doc):
            if not doc:
                return None
            for control in self.children(doc):
                if control.cls != "VSFlexGrid8N":
                    continue
                if self.grid_layout(control, ("元件名称", "数据类型")):
                    return control
            return None

        from . import input as inp

        grid = lookup(self.active_doc_hwnd())
        if grid:
            return grid
        self.open_tree_child("元件监控表")             # not open yet: open it from the tree
        time.sleep(0.8)
        self.wait_idle(20)
        grid = lookup(self.active_doc_hwnd())
        if grid:
            return grid

        def cycle():
            """Ctrl+Tab through the open documents looking for the monitor grid."""
            for _ in range(len(self.documents())):
                self.activate()
                inp.chord(["ctrl"], "tab")
                time.sleep(0.5)
                found = lookup(self.active_doc_hwnd())
                if found:
                    return found
            return None

        return cycle()                      # already open but behind another document

    def crossref(self):
        """Device cross-reference from the saved project (``CrossTable.crs``).

        Each row is ``{"device", "program", "instruction", "flag", "tail"}`` — the file
        AutoShop rewrites on save, so this is an offline "where is this device used"
        view (see :func:`autoshopkit.projectfile.read_crossref`).
        """
        from . import projectfile
        return projectfile.read_crossref(self.project_path) if self.project_path else []

    def device_usage(self):
        """Aggregate :meth:`crossref` into ``{device: [{"program", "instruction"}]}``."""
        usage = {}
        for row in self.crossref():
            program = os.path.basename(row.get("program") or "")
            usage.setdefault(row["device"], []).append(
                {"program": program, "instruction": row.get("instruction", "")})
        return usage

    def monitor_table(self):
        """The saved 元件监控表 rows (``VarList``-style offline read)."""
        from . import projectfile
        return projectfile.read_monitor(self.project_path) if self.project_path else []

    def add_monitor(self, devices, start_row=0):
        """Append device names to 元件监控表 (the grid takes text only via UIA).

        Same recipe as ``add_symbol``: click the cell, post ``WM_CHAR`` so the
        in-cell editor opens, write through ``ValuePattern``, then commit by clicking
        away.  ``元件名称`` accepts a plain device such as ``M100`` or ``D10``.
        """
        from . import input as inp
        try:
            from . import uia
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("UI Automation is required: %s" % exc)
        self._dismiss_all()          # a leftover dialog or a busy frame eats the click
        self.wait_idle(30)
        grid = None
        for _attempt in range(3):    # a long session can leave the tree scrolled
            grid = self.monitor_grid()
            if grid:
                break
            self._dismiss_all()
            self.wait_idle(20)
            time.sleep(0.5)
        if not grid:
            raise LookupError("元件监控表 grid not found (is the document open?)")
        layout = self.grid_layout(grid, ("元件名称", "数据类型", "显示格式", "注释"))
        if layout:
            col_x, row0, pitch = layout
        else:
            col_x, row0, pitch = self.MONITOR_COLS, self.MONITOR_ROW0, self.MONITOR_PITCH
        self.focus_window(grid.hwnd)     # cell clicks need the grid focused, not the frame
        time.sleep(0.2)
        written = []
        first_y = row0 + start_row * pitch
        for index, device in enumerate(devices):
            y = row0 + (start_row + index) * pitch
            self.activate()
            time.sleep(0.15)
            element = None
            for _try in range(3):
                inp.click_client(grid.hwnd, col_x[0], y)
                time.sleep(0.35)
                w.post(grid.hwnd, 0x0102, ord(" "), 1)
                time.sleep(0.4)
                element = uia.editor_element_in(grid.hwnd, timeout=1.5)
                if element is not None:
                    break
                self.focus_window(grid.hwnd)
                time.sleep(0.4)
            if element is not None and uia.set_value(element, device):
                written.append(device)
            time.sleep(0.25)
            inp.key("enter")            # commit this row before touching the next one
            time.sleep(0.45)
        inp.click_client(grid.hwnd, col_x[0], row0 + pitch * (start_row + len(devices) + 3))
        time.sleep(0.3)
        inp.key("enter")
        time.sleep(0.4)
        if not written:
            raise LookupError(
                "元件监控表 accepted no device (is its document frontmost? open it with "
                "open_tree_child('元件监控表') first)")
        return written

    # ------------------------------------------------------- high-level work
    def diagnostics(self, lines=None):
        """Structured view of the compile/conversion pane (see diagnostics.py)."""
        from . import diagnostics as diag
        return diag.parse(self.output_lines() if lines is None else lines)

    def apply_program(self, text, document="MAIN", save=False, all_programs=True):
        """Write a program, convert it, compile it and report what happened.

        One call for the whole authoring loop, which is what an agent actually
        needs: ``{"document", "written", "readback_ok", "compiles", "errors",
        "warnings", "summary", "converted"}``.  ``converted`` is the conversion
        diagnosis taken from the 转换 pane right after the paste.
        """
        from . import diagnostics as diag

        if document and not self.activate_document(document):
            self.tree_open(document)
        sci = self.scintilla() or self.view_il()
        if not sci:
            raise LookupError("no instruction-list editor for %r" % document)
        length = self.set_program_il(text)
        time.sleep(0.6)
        converted = diag.parse(self.output_lines())
        readback = (self.program_il() or "").replace("\t", " ")
        wanted = " ".join(text.replace("\t", " ").split())[:40]
        readback_ok = wanted.split(" ")[0] in readback if wanted else bool(readback)
        self.view_ladder()
        time.sleep(0.5)
        ok, lines = self.compile(all_programs=all_programs)
        result = diag.parse(lines)
        result.update({"document": document, "written": length,
                       "readback_ok": readback_ok, "compiles": bool(ok),
                       "converted": converted})
        if save:
            self.cmd("save_project")
            time.sleep(1.2)
        return result

    def document_names(self):
        """Program documents of the project tree (``MAIN``, ``SBR_001``, ``INT_001``…)."""
        tree = self.tree()
        if not tree:
            return []
        items = self.tree_items(tree)
        names = []
        inside = False
        for depth, text, _children, _hitem in items:
            if depth == 1:
                inside = text == "程序块"
                continue
            if inside and depth == 2 and text and text not in names:
                names.append(text)
        return names

    def activate_program(self, name, tries=None):
        """Bring a *program* document to the front **and make its IL editor exist**.

        Two traps are handled here:

        * ``[MAIN]`` is ambiguous — the 元件监控表 document is also called ``MAIN``, so the
          frame title alone is not proof;
        * a document opened in the ladder view has no instruction-list editor until
          ``view_il`` is issued, and only editors that belong to the active document are
          acceptable (a process-wide search returns another program's buffer and silently
          hands back the wrong text).
        """
        from . import input as inp

        def ready():
            if "[" + name not in self.title:
                return False
            self.view_il()
            return bool(self.scintilla(allow_fallback=False))

        if ready():
            return True
        if self.activate_document(name) and ready():
            return True
        self.activate()
        time.sleep(0.2)
        for _ in range(tries if tries is not None else max(6, len(self.documents()) + 3)):
            inp.chord(["ctrl"], "tab")
            time.sleep(0.45)
            if ready():
                return True
        return False

    def programs_from_il_log(self, project_dir=None):
        """Program texts from ``il_log.log`` — the only IL source for H5U ladder projects.

        H5U documents have no instruction-list editor, so the Scintilla channel comes back
        empty even though the project compiles.  转换/编译 rewrites ``il_log.log`` with the
        whole project as numbered IL; ``projectfile.split_il_programs`` turns it into one list
        of instructions per program (``MAIN``, ``SBR_*``, ``FB:*``).
        """
        from . import projectfile

        project_dir = project_dir or self.project_path
        if not project_dir:
            return {}
        split = projectfile.split_il_programs(project_dir)
        return {name: "\n".join(lines) for name, lines in split.items()}

    def read_programs(self, names=None, il_log_fallback=True):
        """Read every program document through the instruction-list channel.

        Returns ``{name: text}``.  Each program is opened from the tree (≈3 s the first
        time) and read with the Scintilla selection API, so the text is exactly what the
        editor holds, not what the ladder happens to draw.
        """
        out = {}
        for name in (names or self.document_names()):
            if not self.activate_program(name):
                if not self.tree_open(name) or not self.activate_program(name):
                    continue
            self.view_il()
            time.sleep(0.4)
            # strict read: a process-wide search would hand back another program
            text = self.program_il(strict=True)
            if text is None:
                continue
            out[name] = text.rstrip("\x00")
        if not out and il_log_fallback and not names:
            return self.programs_from_il_log()
        return out

    def apply_programs(self, programs, save=False, all_programs=True):
        """Write several programs and compile once.

        ``programs`` maps a document name to IL text (``{"MAIN": "...", "SBR_001":
        "..."}``).  Each write reports its own conversion result; the final compile is
        shared, so project-level diagnostics (double coils across programs, missing
        interrupt numbers) appear once, attributed by ``source``.
        """
        from . import diagnostics as diag

        written = {}
        for name, text in programs.items():
            if not self.activate_document(name):
                self.tree_open(name)
            self.view_il()
            time.sleep(0.3)
            length = self.set_program_il(text)
            time.sleep(0.6)
            converted = diag.parse(self.output_lines())
            readback = (self.program_il() or "").replace("\t", " ")
            first = " ".join((text or "").split())[:24]
            written[name] = {"written": length, "converted": converted,
                             "readback_ok": bool(first) and first.split(" ")[0] in readback}
        self.view_ladder()
        time.sleep(0.5)
        ok, lines = self.compile(all_programs=all_programs)
        result = diag.parse(lines)
        result.update({"compiles": bool(ok), "programs": written})
        if save:
            self.cmd("save_project")
            time.sleep(1.5)
        return result

    def _project_mtimes(self):
        import os
        root = self.project_path or ""
        out = {}
        if not root or not os.path.isdir(root):
            return out
        for folder, _dirs, files in os.walk(root):
            if os.path.basename(folder).lower() == "backup":
                continue
            for name in files:
                path = os.path.join(folder, name)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                out[os.path.relpath(path, root)] = (stat.st_mtime_ns, stat.st_size)
        return out

    def save(self, timeout=45, settle=4.0):
        """保存工程 with verification of *which* files were written.

        AutoShop rewrites only the components it considers dirty, so the ``.hcp`` mtime
        is not a reliable signal (verified: a program edit rewrote ``MAIN.IL`` while the
        ``.hcp`` stayed untouched).  This snapshots every project file, saves, then polls
        until something changes or ``settle`` seconds pass.

        Returns ``{"ok", "path", "changed_files", "changed", "dialogs", "waited"}``.
        ``changed=False`` is legitimate when there was nothing to save.
        """
        before = self._project_mtimes()
        self._dismiss_all()
        self.wait_idle(timeout)
        self.cmd("save_project")
        self.wait_idle(timeout)
        left = [w.window_text(h) for h in self.dialogs()]
        deadline = time.time() + max(0.0, settle)
        changed = {}
        waited = 0.0
        after = before
        # accumulate over the whole window: AutoShop flushes several files in sequence
        while True:
            after = self._project_mtimes()
            for name, stamp in after.items():
                if before.get(name) != stamp:
                    changed[name] = stamp
            if time.time() >= deadline:
                break
            time.sleep(0.25)
            waited += 0.25
        hcp = next((os.path.join(self.project_path or "", n) for n in (before or {})
                    if n.lower().endswith(".hcp")), None)
        program_files = [n for n in changed
                         if n.lower().endswith((".ld", ".il", ".st", ".ldx", ".prg"))]
        return {"ok": not left, "path": hcp, "changed_files": sorted(changed),
                "program_files_changed": sorted(program_files),
                "changed": bool(changed), "dialogs": left, "waited": round(waited, 2)}

    def project_summary(self, compile_now=False):
        """One call that describes the whole project, for an agent to plan against.

        Reads the programs through the editors, the symbol and monitor tables and the
        cross-reference through the saved files, and (optionally) compiles.  ``stale``
        is set when a file-backed table may predate unsaved edits, so a caller knows to
        ``save()`` first.
        """
        summary = {"project": self.project_path, "title": self.title,
                   "documents": [t for _h, t in self.documents()],
                   "program_names": self.document_names()}
        tree = self.tree()
        summary["tree_items"] = len(self.tree_items(tree)) if tree else 0
        programs = self.read_programs()
        summary["programs"] = {name: {"lines": len(text.splitlines()),
                                      "chars": len(text),
                                      "networks": text.count("//")}
                               for name, text in programs.items()}
        symbols = self.symbols()
        summary["symbols"] = {"count": len(symbols), "rows": symbols[:20]}
        monitor = self.monitor_table()
        summary["monitor"] = {"count": len(monitor), "rows": monitor}
        usage = self.device_usage()
        summary["devices"] = {"count": len(usage),
                              "most_used": sorted(usage.items(),
                                                  key=lambda kv: -len(kv[1]))[:8]}
        # the file-backed tables reflect the last save, not unsaved editor state
        summary["file_tables_from_last_save"] = True
        if compile_now:
            ok, lines = self.compile()
            from . import diagnostics as diag
            result = diag.parse(lines)
            result["compiles"] = bool(ok)
            summary["compile"] = result
        return summary

    def project_check(self, compile_now=True):
        """Audit the project and return ``{"findings", "counts", ...}``.

        Combines the verified sources (compile diagnostics, ``CrossTable.crs``,
        ``VarList.gdt``, ``MAIN.mon``) into findings with stable codes — see
        :mod:`autoshopkit.check`.  Nothing is inferred beyond what those sources say.
        """
        from . import check as project_check

        programs = self.read_programs()
        crossref = self.crossref()
        symbols = self.symbols()
        monitor = self.monitor_table()
        diagnostics = None
        if compile_now:
            ok, lines = self.compile()
            from . import diagnostics as diag
            diagnostics = diag.parse(lines)
            diagnostics["compiles"] = bool(ok)
        items = project_check.findings(programs, crossref, symbols, monitor, diagnostics)
        return {"findings": items, "counts": project_check.summarize(items),
                "compiles": (diagnostics or {}).get("compiles"),
                "summary": (diagnostics or {}).get("summary"),
                "programs": list(programs), "devices": len(crossref),
                "symbols": len(symbols), "monitor": len(monitor)}

    def doctor(self):
        """Environment self-check an agent can run before doing real work."""
        import importlib
        report = {"frame": hex(self.frame), "title": self.title,
                  "project": self.project_path,
                  "project_open": bool(self.project_path),
                  "has_tree": bool(self.tree_items()),
                  "has_document": bool(self.documents()),
                  "statusbar": self.statusbar_text()}
        for module in ("frida", "comtypes"):
            try:
                mod = importlib.import_module(module)
                report[module] = getattr(mod, "__version__", "installed")
            except Exception as exc:  # noqa: BLE001 - report, do not raise
                report[module] = "missing: %s" % exc
        try:
            from . import uia
            report["uia"] = bool(uia.from_handle(self.frame))
        except Exception as exc:  # noqa: BLE001
            report["uia"] = "unavailable: %s" % exc
        report["il_editor"] = bool(self.scintilla())
        report["output_pane"] = bool(self.output_box())
        report["dialogs_open"] = [w.window_text(h) for h in self.dialogs()]
        return report

    # --------------------------------------------------------------- dialogs
    def dialogs(self):
        out = []
        for hwnd in w.enum_windows():
            pid = ctypes.c_ulong(0)
            w.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != self.pid or hwnd == self.frame:
                continue
            cls = w.class_name(hwnd)
            if cls != "#32770":
                continue
            if not w.window_text(hwnd):
                continue
            out.append(hwnd)
        return out

    def dialog(self, title=None, timeout=10.0):
        def find():
            for h in self.dialogs():
                if title is None or title in w.window_text(h):
                    return h
            return None
        return w.wait_until(find, timeout)

    def dialog_controls(self, hdlg):
        return [Control(h, self) for h in w.enum_children(hdlg)]

    def dialog_summary(self, hdlg=None):
        hdlg = hdlg or (self.dialogs() or [None])[0]
        if not hdlg:
            return []
        return [(c.cls, c.cid, c.text, c.rect) for c in self.dialog_controls(hdlg)]

    def click(self, ctl):
        w.post(ctl.hwnd, w.BM_CLICK, 0, 0)
        time.sleep(0.3)

    def close_dialogs(self):
        closed = []
        for h in self.dialogs():
            ctrls = self.dialog_controls(h)
            cancel = [c for c in ctrls if c.cls == "Button" and c.text in ("取消", "关闭", "Cancel")]
            if cancel:
                w.post(cancel[0].hwnd, w.BM_CLICK, 0, 0)
            else:
                w.post(h, w.WM_CLOSE, 0, 0)
            closed.append(w.window_text(h))
            time.sleep(0.3)
        return closed

    # -------------------------------------------------------------- text i/o
    def set_control_text(self, ctl, text):
        data = text.encode("utf-16-le") + b"\x00\x00"
        buf = self.remote.alloc(len(data))
        try:
            self.remote.write(buf, data)
            w.send(ctl.hwnd, w.WM_SETTEXT, 0, buf)
        finally:
            self.remote.free(buf)

    def get_control_text(self, ctl, size=1024):
        buf = self.remote.alloc(size * 2)
        try:
            w.send(ctl.hwnd, w.WM_GETTEXT, size, buf)
            return self.remote.read(buf, size * 2).decode("utf-16-le", "replace").split("\x00")[0]
        finally:
            self.remote.free(buf)

    def combo_items(self, ctl):
        n = w.send(ctl.hwnd, w.CB_GETCOUNT)
        out = []
        buf = self.remote.alloc(1024)
        try:
            for i in range(n):
                w.send(ctl.hwnd, w.CB_GETLBTEXT, i, buf)
                out.append(self.remote.read(buf, 1024).decode("utf-16-le", "replace").split("\x00")[0])
        finally:
            self.remote.free(buf)
        return out

    # ------------------------------------------------------------------ misc
    def statusbar_text(self):
        """Status-bar message through UI Automation.

        ``SB_GETTEXTW``/``SB_GETPARTS`` return 0 for this status bar (an MFC
        ``CMFCStatusBar``), but the bar is exposed to UIA as an element whose name
        is the current message (e.g. ``就绪``, ``切换为指令列表编辑器``).
        """
        try:
            from . import uia
        except Exception:
            return ""
        try:
            return uia.status_bar_text(self.frame)
        except Exception:
            return ""

    def force_repaint(self, hwnd):
        """Nudge a window's size by one pixel so the app repaints it itself."""
        l, t, r, b = w.rect(hwnd)
        SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0002, 0x0004, 0x0010
        w.user32.SetWindowPos.restype = w.wt.BOOL
        w.user32.SetWindowPos(hwnd, None, 0, 0, r - l + 1, b - t, SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE)
        time.sleep(0.15)
        w.user32.SetWindowPos(hwnd, None, 0, 0, r - l, b - t, SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE)
        time.sleep(0.15)

    def focus_window(self, hwnd):
        """Give ``hwnd`` keyboard focus across processes (AttachThreadInput trick).

        ``SetFocus`` only works inside the owning thread, and a synthetic click
        does not always move focus in this app (verified: Down keys then never
        moved the tree caret).  Attaching our input queue to the target thread
        makes both ``SetForegroundWindow`` and ``SetFocus`` succeed.
        """
        target_thread = w.user32.GetWindowThreadProcessId(hwnd, None)
        current = w.kernel32.GetCurrentThreadId()
        attached = False
        try:
            if target_thread and target_thread != current:
                attached = bool(w.user32.AttachThreadInput(current, target_thread, True))
            w.user32.BringWindowToTop(hwnd)
            w.user32.SetForegroundWindow(hwnd)
            w.user32.SetFocus(hwnd)
            time.sleep(0.15)
        finally:
            if attached:
                w.user32.AttachThreadInput(current, target_thread, False)
        return True

    def activate(self):
        w.user32.ShowWindow(self.frame, 9)   # SW_RESTORE
        w.user32.SetForegroundWindow(self.frame)
        time.sleep(0.15)

    def snapshot(self, path):
        from .capture import capture_window
        return capture_window(self.frame, path)

    def summary(self):
        items = self.tree_items()
        project = [(d, t) for d, t, _c, _h in items]
        return {
            "pid": self.pid,
            "frame": hex(self.frame),
            "title": self.title,
            "project": self.project_path,
            "documents": [t for _h, t in self.documents()],
            "tree_count": len(project),
            "tree": project,
            "toolbars": [(c.text, c.cid) for c in self.toolbars()],
            "dialogs": [w.window_text(h) for h in self.dialogs()],
        }
