"""H5U IL channel: the numbered list that 转换/编译 writes to ``il_log.log``.

H5U ladder documents have no instruction-list editor (verified: the document owns a single
``AfxFrameOrView90u`` view, 查看→指令表 creates no Scintilla, and ``read_programs()`` through
the editor comes back empty).  The compile step still writes the whole project as numbered IL,
and that log splits cleanly into programs.  This test pins that down on the real project.

Run:  python tools/test_h5u_il.py
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from autoshopkit import projectfile

REAL = r"D:\bililive\autoshopkit\sandbox\real\xmlproj"
RESULTS = []


def step(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("[PASS] " if ok else "[FAIL] ") + name + ("  " + str(detail)[:200] if detail else ""))


def skip(name, why):
    RESULTS.append((name, True, why))
    print("[SKIP] " + name + "  " + why)


def compiled_count(project_dir, program):
    path = os.path.join(project_dir, "Compile", program + ".compile")
    if not os.path.exists(path):
        return None
    data = open(path, "rb").read()
    if data[:3] != b"SAY":
        return None
    return struct.unpack_from("<H", data, 4)[0]


def main():
    if not os.path.isdir(REAL):
        skip("real H5U project", "sandbox copy missing")
        print("\n0/0 passed (skipped)")
        return 0

    log = projectfile.read_il_log(REAL)
    step("il_log.log is present and numbered", log is not None and log["steps"] > 1000,
         log and {"steps": log["steps"]})
    if not log:
        print("\n0/1 passed")
        return 1

    split = projectfile.split_il_programs(REAL, log)
    step("every step belongs to exactly one program",
         sum(len(lines) for lines in split.values()) == log["steps"],
         {"split": sum(len(v) for v in split.values()), "log": log["steps"]})

    expected_main = compiled_count(REAL, "MAIN")
    step("MAIN length equals the instruction count in Compile/MAIN.compile",
         expected_main is not None and len(split.get("MAIN", [])) == expected_main,
         {"split": len(split.get("MAIN", [])), "compile": expected_main})
    step("MAIN ends with MAINEND", split.get("MAIN", [""])[-1].strip().upper() == "MAINEND",
         split.get("MAIN", [""])[-1])
    step("MAIN starts with the first ladder instruction",
         split.get("MAIN", [""])[0].startswith("LD "), split.get("MAIN", [""])[0])

    subprograms = {name: lines for name, lines in split.items()
                   if name.startswith("SBR_")}
    step("four subprograms found", len(subprograms) == 4, list(subprograms))
    step("each subprogram starts with P and ends with SRET",
         all(lines[0].strip() == "P" and lines[-1].strip() == "SRET"
             for lines in subprograms.values()),
         {name: (lines[0].strip(), lines[-1].strip())
          for name, lines in subprograms.items()})
    step("subprogram names come from the cross-reference device sets",
         not any(name.startswith("SBR_#") for name in subprograms), list(subprograms))

    fb = {name: lines for name, lines in split.items() if name.startswith("FB:")}
    servo = [lines for name, lines in fb.items() if lines[0].startswith("CALL_FB 伺服")]
    step("servo FB instances are inlined once per instance",
         len(servo) == 12 and {len(lines) for lines in servo} == {176},
         {"instances": len(servo), "sizes": sorted({len(lines) for lines in servo})})

    text = "\n".join(split["MAIN"])
    step("MAIN calls every subprogram",
         all(("CALL " + name) in text for name in subprograms),
         [name for name in subprograms if ("CALL " + name) not in text])

    bad = [r for r in RESULTS if not r[1]]
    print("\n%d/%d passed" % (len(RESULTS) - len(bad), len(RESULTS)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
