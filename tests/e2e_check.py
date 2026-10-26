"""Acceptance for the project health check: plant defects, expect the right findings.

Run:  python tools/e2e_check.py
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

SRC = _template.require_template("e2e_check.py")
WORK = r"D:\bililive\autoshopkit\sandbox\checktest"

# MAIN drives Y0 twice (double coil) and leaves M9 written but never read;
# SBR_001 is empty; the symbol and the monitor row are never used.
DEFECTIVE = {
    "MAIN": "//net1\nLD X0\nOUT Y0\n//net2\nLD X1\nOUT Y0\nOUT M9\n",
    "SBR_001": "//nothing here\n",
    "INT_001": "//int\nLD M7\nOUT Y1\n",     # M7 is read but never written
}
CLEAN = {
    "MAIN": "//net1\nLD X0\nOUT Y0\n//net2\nLD X1\nAND Y0\nOUT Y1\n",
    "SBR_001": "//sub\nLD X3\nOUT Y2\n",
    "INT_001": "//int\nLD X4\nOUT Y3\n",
}
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
    app = AutoShop.launch(os.path.join(WORK, hcp), wait=90, timeout_title="checktest")

    # --- clean project: no warnings planted, so none of the warning codes may fire
    app.apply_programs(CLEAN)
    app.save(settle=4.0)
    baseline = app.project_check()
    codes = set(baseline["counts"]["codes"])
    step("clean project produces no planted warning",
         not (codes & {"W101-double-coil", "W110-empty-program", "W130-unused-symbol",
                       "W140-monitor-not-in-program", "W150-dead-write"}),
         sorted(codes))
    step("clean project compiles inside the check", baseline["compiles"] is True,
         baseline["summary"])
    step("capacity is reported", "I100-capacity" in codes, baseline["summary"])

    # --- plant defects
    app.apply_programs(DEFECTIVE)
    app.add_symbol("SPARE1", "M50", "never used", row=0)
    app.add_monitor(["M60"], start_row=0)          # M60 appears in no program
    app.save(settle=4.0)

    report = app.project_check()
    codes = set(report["counts"]["codes"])
    step("double coil is reported", "W101-double-coil" in codes,
         sorted(c for c in codes if c.startswith("W1")))
    step("empty program is reported", "W110-empty-program" in codes,
         [f["message"] for f in report["findings"] if f["code"] == "W110-empty-program"])
    step("unused symbol is reported", "W130-unused-symbol" in codes,
         [f["detail"] for f in report["findings"] if f["code"] == "W130-unused-symbol"])
    step("monitor row outside the programs is reported",
         "W140-monitor-not-in-program" in codes,
         [f["detail"] for f in report["findings"] if f["code"] == "W140-monitor-not-in-program"])
    step("write-only device is reported as info", "I110-write-only-device" in codes,
         [f["detail"] for f in report["findings"] if f["code"] == "I110-write-only-device"])

    dead = [f for f in report["findings"] if f["code"] == "W150-dead-write"]
    step("dead write is located by program and line",
         bool(dead) and any("M9" in f["message"] for f in dead),
         [f["message"] for f in dead])
    readonly = [f for f in report["findings"] if f["code"] == "I120-read-only-device"]
    step("read-only internal device is reported as info",
         bool(readonly) and any("M7" in f["message"] for f in readonly),
         [f["message"] for f in readonly])
    step("counts are summarised",
         report["counts"]["warnings"] >= 4 and report["counts"]["infos"] >= 2,
         report["counts"])

    app.close()
    bad = [r for r in RESULTS if not r[1]]
    print("\n%d/%d passed" % (len(RESULTS) - len(bad), len(RESULTS)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
