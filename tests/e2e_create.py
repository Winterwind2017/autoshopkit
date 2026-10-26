"""Acceptance for project creation: 新建工程 → move → reopen → program → compile.

Run:  python tools/e2e_create.py
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

DEST = r"D:\bililive\autoshopkit\sandbox\created"
RESULTS = []


def step(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("[PASS] " if ok else "[FAIL] ") + name + ("  " + str(detail) if detail else ""))


def main():
    name = "e2e_created"
    target = os.path.join(DEST, name)
    if os.path.isdir(target):
        shutil.rmtree(target)
    app = AutoShop.attach()
    if app:
        app.close()
        time.sleep(2)

    t0 = time.time()
    app, project = AutoShop.create_project(name, DEST)
    step("project created and reopened", os.path.isdir(project) and name in app.title,
         "%.0fs %s" % (time.time() - t0, project))

    files = sorted(os.listdir(project))
    step("project folder has the component files",
         any(f.lower().endswith(".hcp") for f in files) and "MAIN.LD" in files,
         files[:6])

    tree = [t for _d, t, _c, _h in app.tree_items()]
    step("tree of the new project", tree and tree[0].startswith(name), tree[:3])

    app.activate_document("MAIN")
    sci = app.view_il()
    step("instruction-list editor present", bool(sci), hex(sci.hwnd) if sci else None)

    app.set_program_il("LD X0\nOUT Y0\n")
    app.view_ladder()
    time.sleep(0.6)
    ok, lines = app.compile()
    step("written program compiles", ok, [l for l in lines if "统计" in l] or lines[-2:])

    app.cmd("save_project")
    time.sleep(1.5)
    step("project saved", os.path.getmtime(os.path.join(project, [f for f in os.listdir(project)
                                                               if f.lower().endswith(".hcp")][0])) > t0)

    app.close()
    bad = [r for r in RESULTS if not r[1]]
    print("\n%d/%d passed" % (len(RESULTS) - len(bad), len(RESULTS)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
