"""Acceptance on a *real* H5U project (offline): symbols, var table, cross-reference, ladder.

The copy lives in the sandbox; the test is skipped when it is absent so the suite still runs
on a clean machine.

Run:  python tools/test_offline_audit.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from autoshopkit import check, projectfile

REAL = r"D:\bililive\autoshopkit\sandbox\real\1号机"
RESULTS = []


def step(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("[PASS] " if ok else "[FAIL] ") + name + ("  " + str(detail)[:200] if detail else ""))


def skip(name, why):
    RESULTS.append((name, True, why))
    print("[SKIP] " + name + "  " + why)


def main():
    if not os.path.isdir(REAL):
        skip("real project", "sandbox copy missing")
        print("\n0/0 passed (skipped)")
        return 0

    # 1. H5U symbol table: named variables, no address column
    symbols = projectfile.read_symbols(REAL)
    step("H5U symbol table parses", len(symbols) > 500, len(symbols))
    step("H5U symbols carry their comments",
         any(row["symbol"] == "M0" and row["note"] == "工作" for row in symbols),
         [row for row in symbols if row["symbol"] == "M0"])

    # 2. the exported variable table gives names + PLC addresses
    variables = projectfile.read_var_table(REAL)
    step("variable table parses", len(variables) > 1000, len(variables))
    step("variable table has addresses",
         any(row["name"] == "M8000" and row["address"].upper().startswith("0X")
             for row in variables),
         [row for row in variables if row["name"] == "M8000"])

    # 3. cross-reference of the real project
    crossref = projectfile.read_crossref(REAL)
    per_program = {}
    for row in crossref:
        program = os.path.basename(row.get("program") or "")
        per_program[program] = per_program.get(program, 0) + 1
    step("cross-reference covers every program", len(crossref) > 8000, len(crossref))
    step("cross-reference is attributed per program",
         per_program.get("MAIN.LD", 0) > 7000
         and per_program.get("SBR_伺服程序.LD", 0) > 500,
         per_program)

    # 4. ladder files expose their element text offline
    ladder = {}
    for name in sorted(os.listdir(REAL)):
        if name.lower().endswith(".ld"):
            ladder[name] = projectfile.read_ld_text(os.path.join(REAL, name))
    total = sum(len(tokens) for tokens in ladder.values())
    step("ladder element text is readable", total > 2500, {"files": len(ladder),
                                                          "tokens": total})
    step("ladder text contains real instructions",
         any("ZRST M420 M421" in " ".join(tokens) for tokens in ladder.values()),
         ladder.get("MAIN.LD", [])[:8])

    # 5. offline audit produces the expected findings
    items = check.offline_findings(REAL)
    codes = {item["code"] for item in items}
    step("offline audit reports the declared-but-unused symbols",
         "W130-unused-symbol" in codes,
         [item["message"] for item in items if item["code"] == "W130-unused-symbol"])
    step("offline audit summarises the cross-reference",
         any(item["code"] == "I100-capacity" for item in items), sorted(codes))

    bad = [r for r in RESULTS if not r[1]]
    print("\n%d/%d passed" % (len(RESULTS) - len(bad), len(RESULTS)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
