"""Acceptance for multi-program projects: read all programs, write several, compile once.

Run:  python tools/e2e_programs.py
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

SRC = _template.require_template("e2e_programs.py")
WORK = r"D:\bililive\autoshopkit\sandbox\progtest"
MAIN_SRC = "//main body\nLD X0\nOUT Y0\nLD X1\nOUT M0\n"
SBR_SRC = "//sub body\nLD M0\nOUT Y1\n"
INT_SRC = "//interrupt body\nLD X2\nOUT Y2\n"
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
    app = AutoShop.launch(os.path.join(WORK, hcp), wait=90, timeout_title="progtest")

    names = app.document_names()
    step("program documents listed from the tree", names[:3] == ["MAIN", "SBR_001", "INT_001"], names)

    before = app.read_programs()
    step("all programs readable", set(before) == {"MAIN", "SBR_001", "INT_001"}
         and all("网络注释" in text for text in before.values()),
         {k: len(v) for k, v in before.items()})

    result = app.apply_programs({"MAIN": MAIN_SRC, "SBR_001": SBR_SRC, "INT_001": INT_SRC})
    step("three programs written in one call", result["compiles"], sorted(result["programs"]))
    step("every write read back", all(v["readback_ok"] for v in result["programs"].values()),
         {k: v["readback_ok"] for k, v in result["programs"].items()})
    step("compile is clean", (result["summary"] or {}).get("errors") == 0,
         result["summary"])

    after = app.read_programs()
    step("program text persists in the editor",
         "main body" in after.get("MAIN", "") and "sub body" in after.get("SBR_001", ""),
         {k: v.splitlines()[0] if v else "" for k, v in after.items()})

    broken = app.apply_programs({"SBR_001": "LD X0\nNOTANOP K1\nOUT Y0\n"})
    sources = {e.get("source") for e in broken["errors"]}
    step("a broken subprogram is attributed to its own file",
         (not broken["compiles"]) and any("SBR_001" in (s or "") for s in sources),
         broken["errors"][:1])

    app.apply_programs({"MAIN": MAIN_SRC, "SBR_001": SBR_SRC, "INT_001": INT_SRC}, save=True)
    time.sleep(1.0)
    usage = app.device_usage()
    step("cross-reference lists each device with its program",
         "MAIN.IL" in {u["program"] for u in usage.get("M0", [])}
         and "SBR_001.IL" in {u["program"] for u in usage.get("M0", [])}
         and "INT_001.LD" in {u["program"] for u in usage.get("X2", [])},
         {k: sorted({u["program"] for u in v}) for k, v in list(usage.items())[:4]})
    app.close()
    time.sleep(2)

    app = AutoShop.launch(os.path.join(WORK, hcp), wait=90, timeout_title="progtest")
    reloaded = app.read_programs()
    step("programs survive save + reload",
         "sub body" in reloaded.get("SBR_001", "") and "interrupt body" in reloaded.get("INT_001", ""),
         {k: (v.splitlines()[0] if v else "") for k, v in reloaded.items()})
    app.close()

    bad = [r for r in RESULTS if not r[1]]
    print("\n%d/%d passed" % (len(RESULTS) - len(bad), len(RESULTS)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
