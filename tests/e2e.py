"""End-to-end acceptance: launch -> open program -> read/write IL -> compile -> save.

Run:  python tools/e2e.py
"""
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

from autoshopkit.app import AutoShop

SRC = _template.require_template("e2e.py")
WORK = r"D:\bililive\autoshopkit\sandbox\e2e"
RESULTS = []


def step(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("[PASS] " if ok else "[FAIL] ") + name + ("  " + str(detail) if detail else ""))


def main():
    app = AutoShop.attach()
    if app:
        app.close()
        time.sleep(2)
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    shutil.copytree(SRC, WORK)
    hcp = [f for f in os.listdir(WORK) if f.lower().endswith(".hcp")][0]
    project = os.path.join(WORK, hcp)

    t0 = time.time()
    app = AutoShop.launch(project, wait=90, timeout_title="e2e")
    step("launch opens the project", "e2e" in app.title, "%.1fs" % (time.time() - t0))

    tree = app.tree_items()
    names = [t for _d, t, _c, _h in tree]
    step("project tree readable", "程序块" in names and "MAIN" in names, "%d entries" % len(tree))
    step("instruction catalog present", "指令集" in names)

    t0 = time.time()
    sym = app.tree_open("符号表")
    step("tree row opens by exact geometry", bool(sym),
         "%.1fs %s" % (time.time() - t0, app.title.split(" - ")[-1]))

    doc = app.activate_document("MAIN") or app.tree_open("MAIN")
    step("MAIN document active", bool(doc) and "[MAIN" in app.title, app.title)

    sci = app.view_il()
    step("instruction-list editor reachable", bool(sci), hex(sci.hwnd) if sci else None)
    before = app.program_il()
    step("instruction list readable", before is not None, repr((before or "")[:40]))

    program = "LD X0\nOUT Y0\n"
    length = app.set_program_il(program)
    after = app.program_il() or ""
    step("instruction list writable", "X0" in after and "Y0" in after, repr(after[:60]) + " len=%s" % length)

    app.view_ladder()
    time.sleep(0.8)
    ok, lines = app.compile()
    errors = [l for l in lines if l.strip().startswith("错误")]
    summary = [l for l in lines if "统计" in l]
    step("compile runs and reports", bool(lines), "%d lines" % len(lines))
    step("program compiles without error", ok and not errors, summary or lines)
    app.snapshot(os.path.join(os.path.dirname(WORK), "e2e_final.png"))

    from autoshopkit.programs import KITCHEN_SINK
    app.view_il()
    app.set_program_il(KITCHEN_SINK)
    app.view_ladder()
    time.sleep(0.6)
    ks_ok, ks_lines = app.compile()
    step("a realistic multi-network program compiles", ks_ok,
         [l for l in ks_lines if "统计 -" in l] or ks_lines[-2:])

    app.wait_idle(60)
    dl_ok, dl_path = app.generate_download_file(os.path.join(os.path.dirname(WORK), "e2e_download.updown"))
    step("offline download file generated", dl_ok and dl_path and os.path.exists(dl_path),
         (dl_path, os.path.getsize(dl_path) if dl_path and os.path.exists(dl_path) else 0))

    app.cmd("save_project")
    time.sleep(1.5)
    step("project saved", os.path.getmtime(os.path.join(WORK, hcp)) > t0, os.path.join(WORK, hcp))

    app.close()
    step("AutoShop closed", app.pid not in __import__("autoshopkit.win32", fromlist=["x"]).find_processes("AutoShop.exe"))

    bad = [r for r in RESULTS if not r[1]]
    print("\n%d/%d passed" % (len(RESULTS) - len(bad), len(RESULTS)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
