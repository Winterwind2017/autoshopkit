"""Pure logic tests for ilparse + the read/write pairing (no AutoShop needed).

Run:  python tools/test_ilparse.py       (finishes in well under a second)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from autoshopkit import check, ilparse
from autoshopkit.programs import COVERAGE_PROGRAM

RESULTS = []
LABEL_INSTRUCTIONS = {"CJ", "CJP", "LBL", "CALL", "CALLP", "STL", "MC", "MCR"}


def step(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("[PASS] " if ok else "[FAIL] ") + name + ("  " + str(detail) if detail else ""))


def roles(line):
    record = ilparse.parse(line)[0]
    return ilparse.roles(record["instruction"], len(record["operands"]))


def main():
    # 1. the family program is fully classified except for label operands
    total = unknown = 0
    unexpected = []
    for record in ilparse.parse(COVERAGE_PROGRAM):
        got = ilparse.roles(record["instruction"], len(record["operands"]))
        total += len(got)
        unknown += got.count("?")
        if "?" in got and record["instruction"] not in LABEL_INSTRUCTIONS:
            unexpected.append((record["instruction"], record["operands"], got))
    step("every operand in the family program is classified (labels excepted)",
         not unexpected, {"operands": total, "label_operands": unknown,
                          "unexpected": unexpected})

    # 2. operand roles per family
    step("contacts read", roles("LD X0") == ["r"] and roles("AND X1") == ["r"], roles("LD X0"))
    step("coils write", roles("OUT Y0") == ["w"] and roles("SET M0") == ["w"], roles("OUT Y0"))
    step("timer preset is read", roles("OUT T0 K10") == ["w", "r"], roles("OUT T0 K10"))
    step("move writes the destination", roles("MOV K1 D0") == ["r", "w"], roles("MOV K1 D0"))
    step("compare writes its result operand", roles("CMP K1 K5 M10") == ["r", "r", "w"],
         roles("CMP K1 K5 M10"))
    step("zone compare reads three operands", roles("ZCP K1 K5 D0 M20") == ["r", "r", "r", "w"],
         roles("ZCP K1 K5 D0 M20"))
    step("exchange reads and writes both", roles("XCH D0 D1") == ["rw", "rw"], roles("XCH D0 D1"))
    step("in-place transform is read+write", roles("INC D4") == ["rw"], roles("INC D4"))
    step("loop count is read", roles("FOR K5") == ["r"], roles("FOR K5"))
    step("zone reset writes both ends", roles("ZRST M30 M40") == ["w", "w"], roles("ZRST M30 M40"))
    step("block move reads source and count", roles("BMOV D0 D10 K5") == ["r", "w", "r"],
         roles("BMOV D0 D10 K5"))
    step("labels stay unclassified", roles("CJ P0") == ["?"], roles("CJ P0"))

    # 3. read/write pairing ends up in the right finding codes
    programs = {"MAIN": "LD X0\nOUT Y0\nOUT M9\nMOV K1 D10\nLD D10\n",
                "SBR_001": "//s\nLD M7\nOUT Y1\n"}
    items = check.findings(programs, [], [], [], None)
    codes = {i["code"] for i in items}
    dead = [i for i in items if i["code"] == "W150-dead-write"]
    step("dead write reported for a written-only device",
         "W150-dead-write" in codes and any("M9" in i["message"] for i in dead),
         [i["message"] for i in dead])
    step("a device that is written and read is not a dead write",
         not any("D10" in i["message"] or "Y0" in i["message"] for i in dead),
         [i["message"] for i in dead])
    step("read-only internal device is informational",
         any(i["code"] == "I120-read-only-device" and "M7" in i["message"] for i in items),
         [i["message"] for i in items if i["code"] == "I120-read-only-device"])

    # 4. physical I/O and constants never produce read/write findings
    io_codes = [i for i in items if i["code"] in ("W150-dead-write", "I120-read-only-device")
                and any(dev in i["message"].split()[0] for dev in ("X0", "Y1", "K1"))]
    step("physical I/O and constants are excluded", not io_codes, io_codes)

    bad = [r for r in RESULTS if not r[1]]
    print("\n%d/%d passed" % (len(RESULTS) - len(bad), len(RESULTS)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
