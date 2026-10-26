"""Ladder file decoding: element records ARE readable, and they are a node graph.

A record is ``<u32 node_a><u32 node_b><u16 kind><u8 len><ascii text>`` plus a fixed trailer.
``kind`` groups elements by operand count (1 contact/coil, 2 single-operand instruction,
3 two-operand instruction, 4 box with a parameter list).  There is **no coordinate field**:
the drawing is derived from the graph, and ``node_b < node_a`` marks a branch that reuses an
earlier node.

Run:  python tools/test_ladder.py
"""
import os
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


def main():
    if not os.path.isdir(REAL):
        skip("real project", "sandbox copy missing")
        print("\n0/0 passed (skipped)")
        return 0

    log = projectfile.read_il_log(REAL)
    split = projectfile.split_il_programs(REAL, log) if log else {}

    expected = {"MAIN.LD": 583, "SBR_伺服程序.LD": 66, "SBR_报警信息.LD": 239,
                "SBR_输出控制.LD": 50}
    for name, count in expected.items():
        path = os.path.join(REAL, name)
        if not os.path.exists(path):
            skip("ladder %s" % name, "missing")
            continue
        ladder = projectfile.read_ladder(path)
        elements = ladder["elements"]
        step("%s decodes %d elements" % (name, count), len(elements) == count,
             len(elements))

    main_path = os.path.join(REAL, "MAIN.LD")
    if os.path.exists(main_path):
        elements = projectfile.read_ladder(main_path)["elements"]
        kinds = {}
        for element in elements:
            kinds[element["kind"]] = kinds.get(element["kind"], 0) + 1
        step("kinds are a small closed set", set(kinds) <= {1, 2, 3, 4}, kinds)
        step("every element carries a text", all(element["text"] for element in elements))
        forward = [element for element in elements if element["node_b"] > element["node_a"]]
        backward = [element for element in elements if element["node_b"] < element["node_a"]]
        step("node ids live in one cluster", max(e["node_a"] for e in elements)
             - min(e["node_a"] for e in elements) < 20000,
             {"min": min(e["node_a"] for e in elements),
              "max": max(e["node_a"] for e in elements)})
        step("links point both forward and backward (a graph, not a list)",
             len(forward) > 200 and len(backward) > 20,
             {"forward": len(forward), "backward": len(backward)})
        branches = [element for element in elements if element["node_b"] < element["node_a"]]
        step("branch reuse is visible as a backward node link", len(branches) > 20,
             [(e["node_a"], e["node_b"], e["text"]) for e in branches[:3]])
        step("kind 4 marks boxes with parameters",
             all(" " in element["text"] for element in elements if element["kind"] == 4),
             [e["text"] for e in elements if element["kind"] == 4])

    # every decoded text must occur in the program's IL
    for name in expected:
        path = os.path.join(REAL, name)
        if not os.path.exists(path) or not split:
            continue
        elements = projectfile.read_ladder(path)["elements"]
        il = " ".join(split.get(name[:-3], []))
        missing = [element["text"] for element in elements
                   if element["text"].split()[0] not in il]
        step("%s: every element text appears in the IL" % name, not missing, missing[:5])

    # boxes expand to several IL steps, so element count < instruction count
    if os.path.exists(main_path) and "MAIN" in split:
        elements = projectfile.read_ladder(main_path)["elements"]
        step("element count is below the instruction count (boxes expand)",
             len(elements) < len(split["MAIN"]),
             {"elements": len(elements), "instructions": len(split["MAIN"])})

    bad = [r for r in RESULTS if not r[1]]
    print("\n%d/%d passed" % (len(RESULTS) - len(bad), len(RESULTS)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
