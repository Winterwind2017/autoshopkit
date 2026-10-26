"""Acceptance for the CLI: an agent's eye view — every verb as a subprocess, JSON out.

Run:  python tools/e2e_cli.py
"""
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = _template.require_template("e2e_cli.py")
WORK = r"D:\bililive\autoshopkit\sandbox\clitest"
RESULTS = []


def step(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("[PASS] " if ok else "[FAIL] ") + name + ("  " + str(detail)[:220] if detail else ""))


def run(*arguments, expect_ok=True):
    """Run one CLI verb and return its parsed JSON."""
    command = [sys.executable, "-m", "autoshopkit"] + list(arguments)
    done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)
    if done.returncode != 0:
        if expect_ok:
            raise RuntimeError("verb %s failed (%d): %s\n%s" % (
                arguments[0], done.returncode, done.stdout[-800:], done.stderr[-800:]))
        return None
    body = done.stdout.strip()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        pass
    for index, char in enumerate(body):          # tolerate a leading log line
        if char in "[{":
            try:
                return json.loads(body[index:])
            except json.JSONDecodeError:
                continue
    return {"raw": body}


def main():
    run("stop", expect_ok=False)
    time.sleep(2)
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    shutil.copytree(SRC, WORK)
    hcp = [f for f in os.listdir(WORK) if f.lower().endswith(".hcp")][0]
    project = os.path.join(WORK, hcp)

    started = run("start", project)
    step("start opens the project", started.get("pid") and "AutoShop" in started.get("title", ""),
         started.get("title"))

    status = run("status")
    step("status reports the project", status.get("project") == WORK, status.get("project"))

    tree = run("tree")
    step("tree returns the whole tree", len(tree) > 600, len(tree))

    opened = run("open", "MAIN")
    step("open reaches a document", opened.get("document") is not None, opened)

    cli_program = os.path.join(WORK, "prog.txt")
    with open(cli_program, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("//from cli\nLD X0\nOUT Y0\nMOV K7 D20\n")

    applied = run("apply", cli_program, "--doc", "MAIN")
    step("apply writes and compiles", applied.get("converted") or applied.get("ok"),
         {k: applied.get(k) for k in ("converted", "ok", "errors")})

    readback = run("il", "--doc", "MAIN", "--view")
    normalised = " ".join((readback.get("il") or "").split())
    step("il reads the program back", "MOV K7 D20" in normalised, normalised[:60])

    compiled = run("compile")
    step("compile reports a clean build", compiled.get("ok") is True, compiled.get("lines", [])[:2])

    summary = run("summary", "--compile")
    step("summary describes the project",
         summary.get("program_names", [])[:1] == ["MAIN"] and summary.get("tree_items", 0) > 600,
         {k: summary.get(k) for k in ("program_names", "tree_items")})

    symbols = run("symbols", "--add", "CLI_LAMP", "Y12", "--note", "from cli")
    step("symbols --add writes one row", symbols.get("written") is True,
         len(symbols.get("symbols", [])))

    monitor = run("monitor", "--add", "M30", "D30")
    step("monitor --add accepts two devices",
         monitor.get("written", []) == ["M30", "D30"], monitor.get("written"))

    saved = run("save", "--settle", "4")
    step("save reports what it rewrote", saved.get("ok") is True, saved.get("changed_files", [])[:3])

    checked = run("check")
    codes = (checked.get("counts") or {}).get("codes", [])
    step("check returns finding codes", bool(codes), codes)

    usage = run("crossref")
    step("crossref lists devices", bool((usage.get("usage") or {})), list((usage.get("usage") or {}))[:5])

    shot_path = os.path.join(WORK, "cli.png")
    shot = run("shot", shot_path)
    step("shot writes a PNG", os.path.isfile(shot_path) and os.path.getsize(shot_path) > 1000,
         shot.get("size"))

    commands = run("commands")
    step("commands lists ids", "compile" in commands, list(commands)[:4])

    dialog_report = run("dialogs")
    step("dialogs is empty after the run", dialog_report == [], dialog_report)

    stopped = run("stop")
    step("stop closes the app", stopped.get("closed") is True, stopped)

    bad = [r for r in RESULTS if not r[1]]
    print("\n%d/%d passed" % (len(RESULTS) - len(bad), len(RESULTS)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
