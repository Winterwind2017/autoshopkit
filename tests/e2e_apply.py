"""Acceptance for the high-level authoring loop and the environment self-check.

Run:  python tools/e2e_apply.py
"""
import ctypes
import glob
import json
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
from autoshopkit.programs import KITCHEN_SINK

SRC = _template.require_template("e2e_apply.py")
WORK = r"D:\bililive\autoshopkit\sandbox\applytest"
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
    app = AutoShop.launch(os.path.join(WORK, hcp), wait=90, timeout_title="applytest")

    report = app.doctor()
    step("doctor reports a usable environment",
         report["project_open"] and report["has_tree"] and report["output_pane"]
         and report["comtypes"] != "missing",
         {k: report[k] for k in ("project_open", "has_tree", "uia", "comtypes", "frida")})

    result = app.apply_program(KITCHEN_SINK, document="MAIN", save=True)
    step("apply_program writes, converts and compiles",
         result["written"] and result["compiles"],
         (result["written"], (result["summary"] or {}).get("line")))
    step("readback confirms the program text", result["readback_ok"],
         (result.get("readback_ok"),))
    step("diagnostics are structured",
         isinstance(result["summary"], dict) and result["summary"].get("errors") == 0,
         result["summary"])

    bad = app.apply_program("LD X0\nNOP K1 K2\nOUT Y0\n")
    step("a broken program reports a located error",
         (not bad["compiles"]) and bad["errors"] and bad["errors"][0].get("line") is not None,
         bad["errors"][:1])

    good = app.apply_program("LD X0\nOUT Y0\n", save=True)
    step("recovery after a bad program", good["compiles"], (good["summary"] or {}).get("line"))

    app.close()
    hcp_path = os.path.join(WORK, hcp)
    step("saved project touched on disk", os.path.getsize(hcp_path) > 0, os.path.getsize(hcp_path))

    bad_rows = [r for r in RESULTS if not r[1]]
    print("\n%d/%d passed" % (len(RESULTS) - len(bad_rows), len(RESULTS)))
    print(json.dumps({"doctor": report}, ensure_ascii=False, default=str)[:400])
    return 0 if not bad_rows else 1


if __name__ == "__main__":
    sys.exit(main())
