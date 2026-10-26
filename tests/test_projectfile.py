"""Pure-logic tests for the project-file readers (.LD text, .hcpp backup, tables).

Needs the ladder captures produced by ``tools/probes/ld_experiment.py`` and the machine
project from ``tools/probes/machine_apply.py``; those steps are skipped when absent, so the
test still runs on a clean checkout.

Run:  python tools/test_projectfile.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from autoshopkit import check, ilparse, projectfile
from autoshopkit.programs import MACHINE_PROGRAM

CAPTURES = r"D:\bililive\autoshopkit\recon\ldcaps"
MACHINE = r"D:\bililive\autoshopkit\sandbox\machine"
RESULTS = []


def step(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("[PASS] " if ok else "[FAIL] ") + name + ("  " + str(detail)[:220] if detail else ""))


def skip(name, why):
    RESULTS.append((name, True, why))
    print("[SKIP] " + name + "  " + why)


def main():
    # 1. ladder files carry their element text as <len><ascii>
    expected = {
        "p1_ld_out": ["n1", "X0", "Y0"],
        "p5_timer": ["n1", "X0", "T0 K10"],
        "p6_compare": ["n1", "LD> D0 K5", "Y0"],
        "p7_mov": ["n1", "X0", "MOV K7 D20"],
        "p8_not": ["n1", "X0", "Y0"],
    }
    for name, want in expected.items():
        path = os.path.join(CAPTURES, name + ".LD")
        if not os.path.exists(path):
            skip("LD tokens %s" % name, "capture missing")
            continue
        got = projectfile.read_ld_text(path)
        step("LD tokens %s" % name, got == want, got)

    path = os.path.join(CAPTURES, "p3_series.LD")
    if os.path.exists(path):
        got = projectfile.read_ld_text(path)
        step("LD stores elements in internal order, not source order",
             sorted(got) == sorted(["n1", "X0", "X1", "Y0"]) and got != ["n1", "X0", "X1", "Y0"],
             got)
    else:
        skip("LD internal order", "capture missing")

    # 2. the .hcpp backup is a PPCH container with a zlib stream
    backup_path = None
    if os.path.isdir(MACHINE):
        for name in os.listdir(MACHINE):
            if name.lower().endswith(".hcpp"):
                backup_path = os.path.join(MACHINE, name)
    if backup_path:
        backup = projectfile.read_hcp_backup(backup_path)
        step("hcpp backup unpacks to the stored hcp",
             backup["name"].lower().endswith(".hcp")
             and backup["size"] == len(backup["hcp"])
             and backup["hcp"][:2] == b"bj",
             {k: backup[k] for k in ("name", "original_size", "size")})
    else:
        skip("hcpp backup", "no .hcpp in the machine project")

    # 3. plaintext tables of the machine project
    if os.path.isdir(MACHINE) and os.path.exists(os.path.join(MACHINE, "CrossTable.crs")):
        crossref = projectfile.read_crossref(MACHINE)
        counts = {}
        for row in crossref:
            counts[row["device"]] = counts.get(row["device"], 0) + 1
        step("crossref lists the machine program's devices",
             len(crossref) == 40 and counts.get("M10") == 5 and counts.get("T1") == 4,
             {"rows": len(crossref), "M10": counts.get("M10"), "T1": counts.get("T1")})
    else:
        skip("crossref", "machine project missing")

    # 4. the health check on a realistic program: only genuinely unread devices fire
    items = check.findings({"MAIN": MACHINE_PROGRAM}, [], [], [], None)
    dead = {i["detail"]["device"] for i in items
            if i["code"] == "W150-dead-write" and i.get("detail")}
    step("dead writes on the machine program are the unread devices",
         dead == {"M12", "M13", "T2"}, sorted(dead))
    step("used devices are not flagged",
         not ({"M10", "M11", "D0", "T0", "T1", "C0"} & dead), sorted(dead))

    # 5. every operand in the machine program is classified
    labels = {"CJ", "CJP", "LBL", "CALL", "CALLP", "STL", "MC", "MCR"}
    unknown = []
    for record in ilparse.parse(MACHINE_PROGRAM):
        roles = ilparse.roles(record["instruction"], len(record["operands"]))
        if "?" in roles and record["instruction"] not in labels:
            unknown.append(record)
    step("machine program is fully classified by ilparse (labels excepted)",
         not unknown, unknown[:3])

    bad = [r for r in RESULTS if not r[1]]
    print("\n%d/%d passed (%d skipped)" % (len(RESULTS) - len(bad), len(RESULTS),
                                           sum(1 for r in RESULTS if r[2] and "missing" in str(r[2]))))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
