"""Acceptance for whole-project work: summary, verified save, persistence.

Run:  python tools/e2e_project.py
"""
import ctypes
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

from autoshopkit.app import AutoShop

SRC = _template.require_template("e2e_project.py")
WORK = r"D:\bililive\autoshopkit\sandbox\projwork"
MAIN_SRC = "//main\nLD X0\nOUT Y0\nMOV K1 D10\n"
SBR_SRC = "//sub\nLD Y0\nOUT M5\n"
INT_SRC = "//int\nLD X1\nOUT Y1\n"
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
    app = AutoShop.launch(os.path.join(WORK, hcp), wait=90, timeout_title="projwork")

    summary = app.project_summary()
    step("summary lists the project's programs",
         summary["program_names"][:3] == ["MAIN", "SBR_001", "INT_001"], summary["program_names"])
    step("summary counts the tree", summary["tree_items"] > 600, summary["tree_items"])
    step("file tables start empty", summary["symbols"]["count"] == 0
         and summary["monitor"]["count"] == 0,
         (summary["symbols"]["count"], summary["monitor"]["count"]))

    app.apply_programs({"MAIN": MAIN_SRC, "SBR_001": SBR_SRC, "INT_001": INT_SRC})
    saved = app.save(settle=4.0)
    step("save completes without leaving dialogs", saved["ok"] and not saved["dialogs"],
         (saved["changed"], saved["program_files_changed"]))

    summary = app.project_summary(compile_now=True)
    step("compile of the whole project is clean",
         (summary.get("compile") or {}).get("compiles")
         and (summary["compile"]["summary"] or {}).get("errors") == 0,
         (summary.get("compile") or {}).get("summary"))
    app.close()
    time.sleep(2)

    # phase 2: a fresh session for the grid documents (they are much easier to reach
    # before several program documents are open — see docs/OPEN-QUESTIONS.md)
    app = AutoShop.launch(os.path.join(WORK, hcp), wait=90, timeout_title="projwork")
    app.add_symbol("RUN_LAMP", "Y10", "run lamp", row=0)
    app.add_monitor(["M5", "D10"], start_row=0)
    app.save(settle=4.0)
    summary = app.project_summary()
    step("summary sees the new symbol and monitor rows",
         summary["symbols"]["count"] == 1 and summary["monitor"]["count"] == 2,
         (summary["symbols"]["count"], summary["monitor"]["count"]))
    used = {name for name, _hits in summary["devices"]["most_used"]}
    step("summary reports device usage", {"D10", "Y0"} <= used, sorted(used)[:8])

    app.close()
    time.sleep(2)
    app = AutoShop.launch(os.path.join(WORK, hcp), wait=90, timeout_title="projwork")
    reloaded = app.project_summary()
    step("everything survives save + reload",
         reloaded["symbols"]["count"] == 1 and reloaded["monitor"]["count"] == 2,
         (reloaded["symbols"]["count"], reloaded["monitor"]["count"]))
    programs = app.read_programs()
    normalised = {k: " ".join(v.split()) for k, v in programs.items()}
    step("program text survives save + reload",
         "sub" in normalised.get("SBR_001", "")
         and "MOV K1 D10" in normalised.get("MAIN", ""),
         {k: (v.splitlines()[0] if v else "") for k, v in programs.items()})
    app.close()

    bad = [r for r in RESULTS if not r[1]]
    print("\n%d/%d passed" % (len(RESULTS) - len(bad), len(RESULTS)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
