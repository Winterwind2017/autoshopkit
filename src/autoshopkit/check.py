"""Project health check: findings derived only from data the kit can verify.

Every finding names the evidence it came from, so nothing here is a guess:

* compile diagnostics (errors, warnings such as ``双线圈输出`` or a missing interrupt
  number) come from the output pane after 全部编译;
* device usage comes from ``CrossTable.crs`` (``projectfile.read_crossref``);
* symbols come from ``VarList.gdt`` (``projectfile.read_symbols``);
* monitor rows come from ``MAIN.mon`` (``projectfile.read_monitor``).

The checks are deliberately conservative: a symbol is called *unused* only when the
cross-reference holds no entry for it, and a subroutine only *uncalled* when no program
mentions it in a ``CALL`` instruction.
"""
from __future__ import annotations

from . import ilparse

CALL_RE = "CALL"
CONSTANT_PREFIXES = ("K", "H", "E", "K0", "H0")


def _device_entries(crossref):
    """``{program_basename: [rows]}`` plus ``{device: [rows]}``."""
    by_program, by_device = {}, {}
    for row in crossref:
        program = (row.get("program") or "").replace("\\", "/").rsplit("/", 1)[-1]
        by_program.setdefault(program, []).append(row)
        by_device.setdefault(row.get("device") or "", []).append(row)
    return by_program, by_device


def _instruction_set(rows):
    return {(row.get("instruction") or "").strip().upper() for row in rows}


def findings(programs, crossref, symbols, monitor, diagnostics=None):
    """Build the finding list from already-collected project data.

    ``programs`` is ``{name: IL text}``, ``diagnostics`` is the parsed compile result
    (``{"errors": [...], "warnings": [...], "summary": {...}}``) or ``None``.
    """
    out = []
    by_program, by_device = _device_entries(crossref)
    diagnostics = diagnostics or {}
    summary = diagnostics.get("summary") or {}

    def add(level, code, message, detail=None):
        out.append({"level": level, "code": code, "message": message, "detail": detail})

    # 1. compile results
    for error in diagnostics.get("errors") or []:
        add("error", "E100-compile",
            "%s 第%s行: %s" % (error.get("source"), error.get("line"), error.get("message")),
            error.get("raw"))
    for warning in diagnostics.get("warnings") or []:
        text = warning.get("message") or ""
        code = "W101-double-coil" if "双线圈" in text else (
            "W102-interrupt-number" if "中断" in text else "W100-warning")
        add("warning", code, "%s: %s" % (warning.get("source"), text), warning.get("raw"))

    # 2. capacity
    if summary.get("capacity"):
        used = summary.get("steps") or 0
        total = summary["capacity"] or 1
        pct = round(100.0 * used / total, 2)
        add("info", "I100-capacity", "步占用 %d/%d (%.2f%%)" % (used, total, pct),
            {"steps": used, "capacity": total, "percent": pct})
    if summary.get("comment_capacity"):
        add("info", "I101-network-comments",
            "网络注释 %d/%d" % (summary.get("comment_steps") or 0, summary["comment_capacity"]),
            {"steps": summary.get("comment_steps"), "capacity": summary["comment_capacity"]})

    # 3. programs that hold nothing but comments
    for name, text in (programs or {}).items():
        body = [line for line in (text or "").splitlines()
                if line.strip() and not line.strip().startswith("//")]
        if not body:
            add("warning", "W110-empty-program", "程序 %s 只有注释，没有指令" % name,
                {"lines": len((text or "").splitlines())})

    # 4. subroutines never called
    #
    # Only ``SBR*`` documents are CALL targets.  Interrupt programs (``INT*``) are entered
    # by the interrupt controller, so "no CALL" is not a defect for them — flagging them
    # was a false positive (seen on a clean H3U project).
    whole = "\n".join(text or "" for text in (programs or {}).values()).upper()
    for name in (programs or {}):
        if not name.upper().startswith("SBR"):
            continue
        called = ("CALL " + name.upper()) in whole or ("CALL\t" + name.upper()) in whole
        if not called:
            add("warning", "W120-uncalled-subprogram",
                "子程序 %s 从未被 CALL 引用" % name)

    # 5. symbols declared but never used
    declared = [row.get("symbol") or "" for row in (symbols or [])]
    unused = []
    for name in declared:
        if not name:
            continue
        hits = by_device.get(name.upper()) or by_device.get(name) or []
        if not hits:
            unused.append(name)
    if unused:
        add("warning", "W130-unused-symbol",
            "%d 个符号只声明未使用: %s" % (len(unused), ", ".join(unused[:10])), unused)

    # 6. monitor rows for devices that never appear in a program
    dangling = []
    for row in (monitor or []):
        device = row.get("device") or ""
        if device and not by_device.get(device.upper()):
            dangling.append(device)
    if dangling:
        add("warning", "W140-monitor-not-in-program",
            "监控表里有程序未使用的元件: %s" % ", ".join(dangling[:10]), dangling)

    # 7. read/write pairing from the instruction list itself (precise roles)
    per_program = {name: ilparse.analyse(text) for name, text in (programs or {}).items()}
    merged = ilparse.merge(per_program)
    dead_writes, read_only = [], []
    for device, buckets in merged.items():
        if not device or device[0] in "KHE" or device.replace(".", "").isdigit():
            continue                          # constants, not devices
        if not ilparse.is_internal(device):
            continue                          # X/Y are physical I/O, not program state
        reads, writes = buckets["reads"], buckets["writes"]
        if writes and not reads:
            dead_writes.append({"device": device, "writes": writes,
                                "programs": buckets["programs"]})
        elif reads and not writes:
            read_only.append({"device": device, "reads": reads,
                              "programs": buckets["programs"]})
    for item in dead_writes:
        first = item["writes"][0]
        add("warning", "W150-dead-write",
            "%s 只被写入（%s %s:%d），没有任何读取" % (
                item["device"], first["instruction"], first.get("program"),
                first["line"]),
            {"device": item["device"], "references": item["writes"][:5],
             "programs": item["programs"]})
    for item in read_only:
        first = item["reads"][0]
        add("info", "I120-read-only-device",
            "%s 只被读取（%s %s:%d），程序内没有写入" % (
                item["device"], first["instruction"], first.get("program"),
                first["line"]),
            {"device": item["device"], "references": item["reads"][:5]})

    # 8. devices that only appear as a coil/assignment (informational)
    write_only = []
    for device, rows in by_device.items():
        instructions = _instruction_set(rows)
        if instructions and instructions <= {"OUT", "SET", "RST", "PLS", "PLF"}:
            write_only.append(device)
    if write_only:
        add("info", "I110-write-only-device",
            "%d 个元件只被写入（未作为触点读取）: %s" % (
                len(write_only), ", ".join(sorted(write_only)[:10])), sorted(write_only))

    order = {"error": 0, "warning": 1, "info": 2}
    out.sort(key=lambda item: (order.get(item["level"], 3), item["code"]))
    return out


def summarize(items):
    return {"errors": sum(1 for i in items if i["level"] == "error"),
            "warnings": sum(1 for i in items if i["level"] == "warning"),
            "infos": sum(1 for i in items if i["level"] == "info"),
            "codes": sorted({i["code"] for i in items})}


def offline_findings(project_dir):
    """Audit a saved project **without starting AutoShop**.

    Works from the plaintext tables only: ``VarList.gdt`` / ``VarNameAndAddr.csv``
    (symbols), ``MAIN.mon`` (monitor rows), ``CrossTable.crs`` (device usage) and the
    ``.LD`` texts (network comments + element text).  What needs the app — compile
    diagnostics and the per-instruction read/write pairing — is simply not reported here.
    """
    import os

    from . import projectfile

    symbols = projectfile.read_symbols(project_dir) or []
    variables = projectfile.read_var_table(project_dir) or []
    if variables:
        known = {row["name"] for row in variables}
        symbols = symbols or [{"symbol": name, "address": "", "note": ""}
                              for name in sorted(known)]
        addresses = {row["name"]: row["address"] for row in variables}
        notes = {row["name"]: row["note"] for row in variables}
    else:
        addresses, notes = {}, {}
    monitor = projectfile.read_monitor(project_dir) or []
    crossref = projectfile.read_crossref(project_dir) or []

    used = {row["device"].upper() for row in crossref if row.get("device")}
    out = []

    def add(level, code, message, detail=None):
        out.append({"level": level, "code": code, "message": message, "detail": detail})

    # unused symbols: declared, never referenced by the cross-reference
    unused = [entry["symbol"] for entry in symbols
              if entry.get("symbol") and entry["symbol"].upper() not in used]
    if unused:
        add("warning", "W130-unused-symbol",
            "%d 个符号只声明未使用: %s" % (len(unused), ", ".join(unused[:10])), unused)

    # monitor rows that no program references
    dangling = [row["device"] for row in monitor
                if row.get("device") and row["device"].upper() not in used]
    if dangling:
        add("warning", "W140-monitor-not-in-program",
            "监控表里有程序未使用的元件: %s" % ", ".join(dangling[:10]), dangling)

    # ladder files: report what could be read, so a gap is visible
    ladder = []
    for name in sorted(os.listdir(project_dir)):
        if not name.lower().endswith(".ld"):
            continue
        tokens = projectfile.read_ld_text(os.path.join(project_dir, name))
        ladder.append({"file": name, "tokens": len(tokens), "sample": tokens[:4]})
    if ladder:
        add("info", "I130-ladder-read",
            "%d 个梯形图文件可离线读取（%d 个元素文本）" % (
                len(ladder), sum(item["tokens"] for item in ladder)), ladder)

    devices = {}
    for row in crossref:
        devices[row["device"]] = devices.get(row["device"], 0) + 1
    add("info", "I100-capacity",
        "交叉引用 %d 行，%d 个不同元件" % (len(crossref), len(devices)),
        {"rows": len(crossref), "devices": len(devices),
         "top": sorted(devices.items(), key=lambda item: -item[1])[:10]})

    order = {"error": 0, "warning": 1, "info": 2}
    out.sort(key=lambda item: (order.get(item["level"], 3), item["code"]))
    return out
