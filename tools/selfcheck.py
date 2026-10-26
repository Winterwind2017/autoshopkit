"""Pre-commit self-check for the autoshopkit kernel.

Checks that do not need AutoShop:

1. the package imports from ``src/`` and the CLI exposes the documented verbs;
2. every ``autoshopkit <verb>`` mentioned in ``docs/`` is a real verb;
3. every ``python tests/<file>.py`` mentioned in ``docs/`` exists;
4. no customer identifiers leaked into the tracked tree.

    python tools/selfcheck.py            # 报告
    python tools/selfcheck.py --check    # 有问题退出 4
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
CLI = os.path.join(SRC, "autoshopkit", "cli.py")

# 客户/现场标识，禁止出现在会发布的文件里
FORBIDDEN = [
    "申万", "奥特龙", "西汇", "瀛臻", "方管折弯机", "客户资料",
    r"1号机_H5U", r"H5U-1614MTD",
]
SKIP_DIRS = {"local", "recon", "sandbox", "probes", ".git", "__pycache__", ".pytest_cache"}
TEXT_EXT = {".md", ".py", ".toml", ".json", ".yml", ".yaml", ".txt", ".cfg", ".ini"}


def verbs() -> list[str]:
    text = open(CLI, encoding="utf-8").read()
    return sorted(set(re.findall(r'sub\.add_parser\(\s*"([a-z0-9_]+)"', text)))


def walk_text_files(skip_self=False):
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if os.path.splitext(name)[1].lower() not in TEXT_EXT:
                continue
            path = os.path.join(base, name)
            if skip_self and os.path.abspath(path) == os.path.abspath(__file__):
                continue          # this file carries the blacklist itself
            yield path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="exit 4 on problems")
    args = parser.parse_args(argv)

    problems: list[str] = []

    if SRC not in sys.path:
        sys.path.insert(0, SRC)
    try:
        import autoshopkit  # noqa: F401
        from autoshopkit import app, check, hcp, ilparse, projectfile  # noqa: F401
        print("[ok] package imports")
    except Exception as exc:  # noqa: BLE001 - report and continue
        problems.append("import failed: %s" % exc)
        print("[!!] import failed:", exc)

    known = verbs()
    print("[ok] CLI verbs: %d (%s)" % (len(known), ", ".join(known)))
    if len(known) < 20:
        problems.append("CLI looks truncated: %d verbs" % len(known))

    docs_text = ""
    for path in walk_text_files():
        docs_text += open(path, encoding="utf-8", errors="replace").read()

    command_lines = "\n".join(line for line in docs_text.splitlines()
                               if line.strip().startswith("autoshopkit "))
    for verb in sorted(set(re.findall(r"^autoshopkit\s+([a-z0-9_]+)", command_lines,
                                     re.M))):
        if verb not in known:
            problems.append("docs mention unknown verb: %s" % verb)
    if not problems:
        print("[ok] every documented CLI verb exists")

    for name in sorted(set(re.findall(r"tests/([A-Za-z0-9_]+\.py)", docs_text))):
        if not os.path.exists(os.path.join(ROOT, "tests", name)):
            problems.append("docs mention missing test: %s" % name)
    print("[ok] documented test scripts resolve")

    catalog = os.path.join(ROOT, "recon", "catalog_commands.json")
    if os.path.exists(catalog):
        import json
        commands = json.load(open(catalog, encoding="utf-8")).get("commands", {})
        sys.path.insert(0, SRC)
        from autoshopkit.app import CMD
        for name in ("view_il", "view_ladder", "view_sfc"):
            ident = CMD[name]
            entry = commands.get(str(ident), {})
            hint = entry.get("hint", "")
            expected = {"view_il": "指令列表", "view_ladder": "梯形图", "view_sfc": "步进"}[name]
            if expected not in hint:
                problems.append("CMD[%s]=%d 的目录条目是 %r，和名字不符" % (name, ident, hint[:40]))
        if not problems:
            print("[ok] 编辑器切换命令 ID 与命令目录一致")
    else:
        print("[--] 没有本地命令目录，跳过 CMD ID 校验")

    leaked = []
    for path in walk_text_files(skip_self=True):
        text = open(path, encoding="utf-8", errors="replace").read()
        for token in FORBIDDEN:
            if re.search(token, text):
                leaked.append("%s: %s" % (os.path.relpath(path, ROOT), token))
    if leaked:
        problems.extend("customer identifier leaked -> " + item for item in leaked)
    else:
        print("[ok] no customer identifiers in the tracked tree")

    for line in problems:
        print("[!!]", line)
    if problems:
        return 4 if args.check else 0
    print("\nselfcheck: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
