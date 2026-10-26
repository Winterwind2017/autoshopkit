"""Acceptance for the symbol table: write a symbol through UIA, prove it resolves.

Run:  python tools/e2e_symbols.py
"""
import ctypes
import glob
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

SRC = _template.require_template("e2e_symbols.py")
WORK = r"D:\bililive\autoshopkit\sandbox\symtest"
SYMBOL = "BTN_A"
ADDRESS = "M200"
RESULTS = []


def step(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("[PASS] " if ok else "[FAIL] ") + name + ("  " + str(detail) if detail else ""))


def set_main_program(app, text):
    app.activate_document("MAIN")
    app.view_il()
    app.set_program_il(text)
    app.view_ladder()
    time.sleep(0.6)


def main():
    app = AutoShop.attach()
    if app:
        app.close()
        time.sleep(2)
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    shutil.copytree(SRC, WORK)
    hcp = [f for f in os.listdir(WORK) if f.lower().endswith(".hcp")][0]
    app = AutoShop.launch(os.path.join(WORK, hcp), wait=90, timeout_title="symtest")

    doc = app.tree_open("符号表")
    step("symbol document opens", bool(doc), app.title.split(" - ")[-1])

    cols = app.symbol_columns()
    step("grid geometry measured through UIA", cols[0][1] > cols[0][0] > 0 and cols[2] > 10, cols)

    written = app.add_symbol(SYMBOL, ADDRESS, "auto symbol", row=0)
    step("symbol written through UIA ValuePattern", written, (SYMBOL, ADDRESS))

    row = app.read_symbol(row=0)
    step("symbol row reads back", (row.get("symbol") == SYMBOL) and (row.get("address") == ADDRESS),
         row)

    table = app.read_symbols(max_rows=4)
    step("symbol table enumerates", table and table[0].get("symbol") == SYMBOL,
         table[:2])

    set_main_program(app, "LD %s\nOUT Y0\n" % SYMBOL)
    ok, lines = app.compile()
    step("program using the symbol compiles", ok, [l for l in lines if "统计" in l] or lines[-3:])

    set_main_program(app, "LD ZZZ_NOPE\nOUT Y0\n")
    bad_ok, bad_lines = app.compile()
    undefined = [l for l in bad_lines if "符号未定义" in l]
    step("unknown symbol still fails (negative control)", (not bad_ok) and bool(undefined), undefined)

    set_main_program(app, "LD %s\nOUT Y0\n" % SYMBOL)
    ok2, lines2 = app.compile()
    step("symbol survives the negative control", ok2, [l for l in lines2 if "统计" in l])

    app.cmd("save_project")
    time.sleep(2.0)

    from_file = app.symbols(source="file")
    from_ui = app.symbols(source="ui")
    step("saved VarList.gdt parses to the same rows as the grid",
         bool(from_file) and from_file == from_ui, (from_file, from_ui))
    app.close()

    bad = [r for r in RESULTS if not r[1]]
    print("\n%d/%d passed" % (len(RESULTS) - len(bad), len(RESULTS)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
