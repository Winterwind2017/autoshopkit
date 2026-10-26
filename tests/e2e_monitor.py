"""Acceptance for the monitor table: write devices, save, read them back offline.

Run:  python tools/e2e_monitor.py
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

SRC = _template.require_template("e2e_monitor.py")
WORK = r"D:\bililive\autoshopkit\sandbox\montest"
DEVICES = ["M100", "D10", "X0"]
EXPECTED_TYPES = {"M100": 1, "D10": 2, "X0": 1}
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
    app = AutoShop.launch(os.path.join(WORK, hcp), wait=90, timeout_title="montest")

    step("monitor table starts empty", app.monitor_table() == [], app.monitor_table())

    grid = app.monitor_grid()
    step("元件监控表 document opens with a grid", bool(grid),
         (app.title.split(" - ")[-1], grid.cls if grid else None))

    written = app.add_monitor(DEVICES, start_row=0)
    step("devices written through UIA", written == DEVICES, written)

    app.cmd("save_project")
    time.sleep(2.0)
    rows = app.monitor_table()
    step("saved MAIN.mon lists the same devices",
         [r["device"] for r in rows] == DEVICES, rows)
    step("device data types match (1=bit, 2=word)",
         all(EXPECTED_TYPES[r["device"]] == r["data_type"] for r in rows
             if r["device"] in EXPECTED_TYPES),
         {r["device"]: r["data_type"] for r in rows})

    app.close()
    time.sleep(2.0)

    # persistence: the table survives a reload, read straight from the project
    app = AutoShop.launch(os.path.join(WORK, hcp), wait=90, timeout_title="montest")
    reloaded = app.monitor_table()
    step("monitor table persists across a reload",
         [r["device"] for r in reloaded] == DEVICES, reloaded)
    app.close()
    bad = [r for r in RESULTS if not r[1]]
    print("\n%d/%d passed" % (len(RESULTS) - len(bad), len(RESULTS)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
