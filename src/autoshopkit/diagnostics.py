"""Parse AutoShop's compile / conversion output into structured diagnostics.

The pane prints lines in a few fixed shapes (verified against V4.11.0.5):

    错误  MAIN.IL ,【行1】: X0:符号未定义
    错误  SBR_001.LD ,【行2，列2】: M0:开路
    警告  INT_001.LD, 中断子程序没有指定中断号，不会被编译
    统计 - (0)错误,(31)步占用/(63500)总容量
    注释-(0)步占用, 子程序名称+网络注释-(151)步占用/(500)设置容量

Nothing here guesses: unknown lines are kept verbatim in ``other``.
"""
from __future__ import annotations

import re

STAT_RE = re.compile(r"统计\s*-\s*\((\d+)\)\s*错误\s*,\s*\((\d+)\)\s*步占用\s*/\s*\((\d+)\)\s*总容量")
POS_RE = re.compile(r"【行\s*(\d+)(?:\s*，\s*列\s*(\d+))?】")
CAPACITY_RE = re.compile(r"\((\d+)\)\s*步占用\s*/\s*\((\d+)\)\s*设置容量")
LEVELS = ("错误", "警告", "提示", "信息")


def parse(lines):
    """``{"errors": [...], "warnings": [...], "summary": {...}, "other": [...]}``."""
    errors, warnings, other = [], [], []
    summary = None
    for raw in lines or []:
        line = (raw or "").strip()
        if not line or line.startswith("---"):
            continue
        stat = STAT_RE.search(line)
        if stat:
            summary = {"errors": int(stat.group(1)), "steps": int(stat.group(2)),
                       "capacity": int(stat.group(3)), "line": line}
            continue
        cap = CAPACITY_RE.search(line)
        if cap and summary is not None:
            summary.setdefault("comment_steps", int(cap.group(1)))
            summary.setdefault("comment_capacity", int(cap.group(2)))
            continue
        matched = False
        for level in LEVELS:
            if line.startswith(level):
                body = line[len(level):].strip()
                source, rest = None, body
                if " " in body:
                    source, rest = body.split(" ", 1)
                    source = source.rstrip(",")
                pos = POS_RE.search(rest)
                entry = {
                    "level": level,
                    "source": source,
                    "line": int(pos.group(1)) if pos else None,
                    "column": int(pos.group(2)) if (pos and pos.group(2)) else None,
                    "message": POS_RE.sub("", rest).lstrip(" :,，").strip(),
                    "raw": line,
                }
                (errors if level == "错误" else warnings).append(entry)
                matched = True
                break
        if not matched:
            other.append(line)
    return {"errors": errors, "warnings": warnings, "summary": summary, "other": other}


def ok(result):
    """True when the run produced a summary and no error line."""
    summary = (result or {}).get("summary")
    return bool(summary) and summary.get("errors", 0) == 0 and not (result or {}).get("errors")
