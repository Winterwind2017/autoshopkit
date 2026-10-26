"""Read a project's symbol table straight from ``VarList.gdt`` (no GUI needed).

Layout recovered by controlled experiments (V4.11.0.5, 2026-10-26).  The file is a
sequence of named chunks, all little-endian:

    <count:u16> <0xffff:u16> <ver:u16> <name_len:u16> <name>

``CLVTItem`` holds the temporary (local) variables, ``CGVTItem`` the global symbol
table.  A global entry is

    <name_len:u8> <name> <addr_len:u8> <addr> <note_len:u8> <note> <00 00 00 00 06 80>

i.e. three length-prefixed UTF-8 strings followed by a fixed six-byte trailer.  The
table ends at the first entry whose name length is 0.  Symbol names are limited to
8 characters by the application, and every field is plain UTF-8 — the file only has
an obfuscated *header*, not obfuscated content.

``read_symbols`` returns ``[{"symbol", "address", "note"}]``; it needs the project to
be saved first, and it cannot write (the trailer/checksums are not understood).
"""
from __future__ import annotations

import os
import struct

VARLIST = "VarList.gdt"
MONITOR = "MAIN.mon"
GLOBAL_CHUNK = b"CGVTItem"
LOCAL_CHUNK = b"CLVTItem"
TRAILER = b"\x00\x00\x00\x00\x06\x80"


def find_var_list(project_dir):
    path = os.path.join(project_dir, VARLIST)
    return path if os.path.exists(path) else None


def _read_chunk(data, marker):
    """Bytes after ``marker`` (the chunk name) up to the next chunk header."""
    index = data.find(marker)
    if index < 0:
        return None
    start = index + len(marker)
    # the next chunk starts with <count:u16><ffff><ver:u16><len:u16><name>
    probe = start
    while True:
        nxt = data.find(b"\xff\xff\x01\x00", probe)
        if nxt < 0 or nxt + 8 > len(data):
            return data[start:]
        name_len = struct.unpack_from("<H", data, nxt + 4)[0]
        if 0 < name_len <= 32:
            candidate = data[nxt + 6: nxt + 6 + name_len]
            if all(32 <= b < 127 for b in candidate):
                return data[start:nxt - 2]
        probe = nxt + 1


def _parse_entries(blob):
    rows = []
    pos = 0
    while pos < len(blob):
        name_len = blob[pos]
        if name_len == 0 or name_len > 64:
            break
        pos += 1
        name = blob[pos:pos + name_len]
        pos += name_len
        if pos >= len(blob):
            break
        addr_len = blob[pos]
        pos += 1
        address = blob[pos:pos + addr_len]
        pos += addr_len
        if pos >= len(blob):
            break
        note_len = blob[pos]
        pos += 1
        note = blob[pos:pos + note_len]
        pos += note_len
        if blob[pos:pos + len(TRAILER)] == TRAILER:
            pos += len(TRAILER)
        else:
            # tolerate a missing/renamed trailer by skipping to the next plausible name
            pos += min(6, max(0, len(blob) - pos))
        rows.append({
            "symbol": name.decode("utf-8", "replace"),
            "address": address.decode("utf-8", "replace"),
            "note": note.decode("utf-8", "replace"),
        })
        if len(rows) > 5000:
            break
    return rows


CROSS = "CrossTable.crs"
CROSS_ITEM = b"CCrossRefInfo"
MON_ITEM = b"CElemMonItem"
MON_TRAILER = b"\x06\x80"


def read_crossref(project_dir, filename=CROSS):
    """Device cross-reference (which program/instruction uses a device).

    ``CrossTable.crs`` → ``CCrossRefInfo``, one record per use::

        <name_len:u8> <device><byte> <path…> <instr_len:u8> <instruction> <fields…> 00 00 00 00 06 80

    The path has no explicit length, so it is scanned up to the last ``.IL``/``.LD``
    before the instruction length byte.  AutoShop writes this file on save, so it is an
    offline view of "where is this device used"; the trailing integers are kept raw
    (their meaning was not established).
    """
    path = os.path.join(project_dir, filename)
    if not os.path.exists(path):
        return []
    with open(path, "rb") as fh:
        data = fh.read()
    index = data.find(CROSS_ITEM)
    if index < 0:
        return []
    count = struct.unpack_from("<H", data, index - 6)[0]
    pos = index + len(CROSS_ITEM)
    rows = []
    for _ in range(count):
        if pos >= len(data):
            break
        name_len = data[pos]
        pos += 1
        if name_len == 0 or name_len > 32 or pos + name_len >= len(data):
            break
        device = data[pos:pos + name_len].decode("utf-8", "replace")
        pos += name_len
        flag = data[pos]
        pos += 1
        # scan for the program path: printable ASCII ending in .IL / .LD
        end = data.find(b"\x00\x00\x00\x00\x06\x80", pos)
        if end < 0:
            end = len(data)          # the last record can end at EOF
        window = data[pos:end]
        last = max(window.rfind(b".IL"), window.rfind(b".LD"))
        if last < 0:
            pos = end + len(b"\x00\x00\x00\x00\x06\x80")
            continue
        path_end = last + 3
        program_path = window[:path_end].decode("utf-8", "replace")
        tail = window[path_end:]
        instruction = ""
        if tail:
            instr_len = tail[0]
            instruction = tail[1:1 + instr_len].decode("utf-8", "replace")
        rows.append({"device": device, "flag": flag, "program": program_path,
                     "instruction": instruction, "tail": tail[1 + len(instruction):].hex(" ")})
        pos = end + len(b"\x00\x00\x00\x00\x06\x80")
    return rows


def read_monitor(project_dir, filename=MONITOR):
    """The 元件监控表 (monitor table) of a saved project.

    Each entry is ``<data_type:u32><display_format:u32><value:u32><err:u8>
    <name_len:u8><name><06 80>`` where ``data_type`` is 1 for bit devices (M/X/Y/T
    contact) and 2 for word devices (D/T current).  Verified by writing five devices
    through the GUI and diffing the file (M100/D10/X0/Y5/T3 → the five records).
    """
    path = os.path.join(project_dir, filename)
    if not os.path.exists(path):
        return []
    with open(path, "rb") as fh:
        data = fh.read()
    index = data.find(MON_ITEM)
    if index < 0:
        return []
    count = struct.unpack_from("<H", data, index - 6)[0]
    pos = index + len(MON_ITEM)
    rows = []
    for _ in range(count):
        if pos + 12 > len(data):
            break
        data_type, display_format, value = struct.unpack_from("<III", data, pos)
        pos += 12
        errcode = data[pos]
        name_len = data[pos + 1]
        pos += 2
        if name_len == 0 or name_len > 64 or pos + name_len > len(data):
            break
        name = data[pos:pos + name_len].decode("utf-8", "replace")
        pos += name_len
        if data[pos:pos + 2] == MON_TRAILER:
            pos += 2
        rows.append({"device": name, "data_type": data_type,
                     "format": display_format, "value": value, "error": errcode})
    return rows


def read_symbols(project_dir):
    """Global symbols of a *saved* project, or ``[]`` when there are none."""
    path = find_var_list(project_dir)
    if not path:
        return []
    with open(path, "rb") as fh:
        data = fh.read()
    blob = _read_chunk(data, GLOBAL_CHUNK)
    if not blob:
        return []
    records = _parse_symbol_records(blob)
    return records or _parse_entries(blob)


def read_locals(project_dir):
    """Temporary (local) variables, same framing under ``CLVTItem``."""
    path = find_var_list(project_dir)
    if not path:
        return []
    with open(path, "rb") as fh:
        data = fh.read()
    blob = _read_chunk(data, LOCAL_CHUNK)
    if not blob:
        return []
    records = _parse_symbol_records(blob)
    return records or _parse_entries(blob)


def _parse_symbol_records(payload):
    """Walk ``CGVTItem`` records, tolerating both layouts.

    H3U: ``<00><name_len><name><addr_len><addr><note_len><note><00 00 00 00 06 80>``
    H5U: ``<00><name_len><name><note_len><note><00 00 00 00 06 80>`` — H5U projects use
    named variables and keep the address in ``VarNameAndAddr.csv`` instead.
    """
    trailer = b"\x00\x00\x00\x00\x06\x80"
    records = []
    position = 0
    limit = len(payload)
    while position + 4 < limit:
        if payload[position] != 0:
            position += 1
            continue
        name_len = payload[position + 1]
        if not 1 <= name_len <= 40:
            position += 1
            continue
        start = payload[position + 2]
        start = position + 2
        name = payload[start:start + name_len]
        if len(name) < name_len or not all(32 <= byte < 127 for byte in name):
            position += 1
            continue
        cursor = start + name_len
        parsed = None
        for with_address in (True, False):
            point = cursor
            address = ""
            try:
                if with_address:
                    address_len = payload[point]
                    if not 1 <= address_len <= 12:
                        continue
                    address = payload[point + 1:point + 1 + address_len].decode("ascii")
                    if not address or not address[0].isalpha():
                        continue
                    point += 1 + address_len
                note_len = payload[point]
                if note_len > 250:
                    continue
                note = payload[point + 1:point + 1 + note_len].decode("utf-8", "replace")
                end = point + 1 + note_len
                if payload[end:end + 6] != trailer:
                    continue
            except (IndexError, UnicodeDecodeError):
                continue
            parsed = {"symbol": name.decode("ascii", "replace"),
                      "address": address, "note": note}
            position = end + 6
            break
        if parsed:
            records.append(parsed)
        else:
            position += 1
    return records


def read_var_table(project_dir):
    """Rows of ``VarNameAndAddr.csv``: ``{name, address, note, bits}``.

    The file is UTF-16 tab-separated (``name \t address \t comment \t bits``) and H5U
    projects export the whole table, system variables included — the most convenient
    offline source of names and addresses.
    """
    import os

    path = os.path.join(project_dir, "VarNameAndAddr.csv")
    if not os.path.exists(path):
        return []
    raw = open(path, "rb").read()
    text = None
    for encoding in ("utf-16", "utf-16-le", "utf-8-sig", "gbk"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return []
    rows = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.split("\t")]
        if len(parts) < 3 or not parts[0]:
            continue
        parts[0] = parts[0].lstrip("\ufeff")
        rows.append({"name": parts[0], "address": parts[1], "note": parts[2],
                     "bits": parts[3] if len(parts) > 3 else ""})
    return rows


DEVICE_RE = None


def _devices_in_text(text):
    """Device names mentioned in an IL line (``M104``, ``X37``, ``D1002``, ``S600`` …)."""
    import re

    global DEVICE_RE
    if DEVICE_RE is None:
        DEVICE_RE = re.compile(r"\b([XYMDSCTBWR]\d{1,6})\b")
    return set(DEVICE_RE.findall(text.upper()))


def read_ladder(path):
    """Elements of a ladder file (``.LD``) in file order.

    A record is ``<u32 node_a><u32 node_b><u16 kind><u8 len><ascii text>`` followed by a
    fixed trailer.  ``node_a``/``node_b`` are graph node ids (they are allocated in
    increasing order and reused at branch points), ``kind`` groups the element by how many
    operands it carries (1 = plain contact/coil, 2 = single-operand instruction such as
    ``SET``/``RST``/``PLS``, 3 = two-operand instruction such as ``ZRST``/``LD=``/``DEMOV``,
    4 = box with a parameter list such as ``TONR``).  **No pixel/grid coordinates are stored**
    — the drawing is derived from the node graph, which is why nothing in the file tracks the
    on-screen position of an element.

    Returns ``{"elements": [{"node_a", "node_b", "kind", "text", "offset"}], "comments": [...]}``.
    """
    data = open(path, "rb").read()
    elements = []
    comments = []
    position = 0x80
    limit = len(data) - 12
    while position < limit:
        try:
            node_a, node_b, kind = struct.unpack_from("<IIH", data, position)
        except struct.error:
            break
        if position + 11 > len(data):
            break
        length = data[position + 10]
        start = position + 11
        if 1 <= length <= 60 and start + length <= len(data):
            body = data[start:start + length]
            if all(32 <= byte < 127 for byte in body) and any(chr(b).isalnum() for b in body):
                text = body.decode("ascii")
                # the trailer starts right after the text and is the same for every element
                trailer = data[start + length:start + length + 4]
                plausible = (0 < node_a < 0x7FFFFFFF and 0 < node_b < 0x7FFFFFFF
                             and 1 <= kind <= 4
                             and trailer[:2] in (b"\x00\x00", b"\x01\x00", b"\x05\x00"))
                if plausible:
                    elements.append({"node_a": node_a, "node_b": node_b, "kind": kind,
                                     "text": text, "offset": position})
                    position = start + length
                    continue
        position += 1
    return {"elements": elements, "comments": comments}


def read_il_log(project_dir):
    """The numbered instruction list that 转换/编译 writes to ``il_log.log``.

    Returns ``{"path", "steps": N, "items": [{"step", "text"}], "text"}`` or ``None`` when the
    file is absent.  H5U projects have **no instruction-list editor** (the ladder document
    exposes no Scintilla view and 查看→指令表 does nothing), but every compile rewrites this
    log with the whole project: ``0000\tLD M207``, ``0001\tOR X34`` … up to ``FBRET 伺服``.
    """
    import os

    for name in ("il_log.log", "newil_log.log"):
        path = os.path.join(project_dir, name)
        if not os.path.exists(path):
            continue
        raw = open(path, "rb").read()
        text = raw.decode("utf-8", "replace")
        items = []
        for line in text.splitlines():
            if "\t" not in line:
                continue
            step, _, body = line.partition("\t")
            if not step.strip().isdigit():
                continue
            items.append({"step": int(step), "text": body})
        if items:
            return {"path": path, "steps": len(items), "items": items, "text": text}
    return None


def split_il_programs(project_dir, log=None):
    """Split the IL log into ``MAIN``, the ``SBR_*`` bodies and the FB bodies.

    Structure measured on a real H5U project (3968 steps):
    ``MAIN`` runs from 0 to the ``MAINEND`` marker, then each subprogram starts at a lone
    ``P`` and ends at ``SRET``, and everything after the last ``SRET`` is FB bodies
    (``FBRET <fb>``).  ``MAIN``'s length equals the instruction count stored in
    ``Compile/MAIN.compile`` (709), which is the check that the split is right.

    Subprogram names are matched to the ``SBR_*.LD`` files by comparing the devices the
    block mentions with the per-program rows of ``CrossTable.crs``; a block whose best match
    is ambiguous keeps the label ``SBR_#N``.
    """
    import os

    if log is None:
        log = read_il_log(project_dir)
    if not log:
        return {}
    texts = [item["text"] for item in log["items"]]
    result = {}

    main_end = next((index for index, text in enumerate(texts)
                     if text.strip().upper() == "MAINEND"), None)
    if main_end is None:
        main_end = len(texts) - 1
    result["MAIN"] = texts[:main_end + 1]

    blocks = []
    index = main_end + 1
    while index < len(texts):
        if texts[index].strip() == "P":
            end = index + 1
            while end < len(texts) and texts[end].strip() != "SRET":
                end += 1
            blocks.append(texts[index:end + 1])
            index = end + 1
        else:
            index += 1

    fb_start = len(texts)
    if blocks:
        consumed = main_end + 1 + sum(len(block) for block in blocks)
        fb_start = consumed

    # name the subprogram blocks by matching their devices against the cross-reference
    crossref = read_crossref(project_dir) or []
    per_program = {}
    for row in crossref:
        program = os.path.basename(row.get("program") or "")
        if program.lower().endswith(".ld"):
            per_program.setdefault(program[:-3], set()).add(row["device"].upper())
    taken = set()
    for order, block in enumerate(blocks, start=1):
        devices = set()
        for line in block:
            devices |= _devices_in_text(line)
        best, best_score = None, 0.0
        for name, wanted in per_program.items():
            if name in taken or not wanted:
                continue
            overlap = len(devices & wanted)
            score = overlap / float(len(devices | wanted) or 1)
            if score > best_score:
                best, best_score = name, score
        label = best if best and best_score >= 0.10 else "SBR_#%d" % order
        if label != "SBR_#%d" % order:
            taken.add(label)
        result[label] = block

    if fb_start < len(texts):
        fb_lines = texts[fb_start:]
        current, buffer = None, []
        for line in fb_lines:
            match = line.strip().split()
            if match and match[0].upper() == "CALL_FB" and len(match) > 2:
                current = "FB:%s" % match[2]
            buffer.append(line)
            if match and match[0].upper() == "FBRET":
                result.setdefault(current or "FB:body", []).extend(buffer)
                buffer = []
        if buffer:
            result.setdefault("FB:tail", []).extend(buffer)
    return result


def read_ld_text(path):
    """Element texts and network comments from a ladder file (``.LD``).

    ``.LD`` is not opaque: every element stores its operand or whole expression as
    ``<len:u8><ascii>``, and a network comment is stored the same way.  Verified against
    controlled programs:

        LD X0 / OUT Y0          -> ["n1", "X0", "Y0"]
        LD> D0 K5 / OUT Y0      -> ["n1", "LD> D0 K5", "Y0"]
        LD X0 / MOV K7 D20      -> ["n1", "X0", "MOV K7 D20"]
        LD X0 / OUT T0 K10      -> ["n1", "X0", "T0 K10"]

    The geometry fields around each text are not decoded yet (see ``docs/OPEN-QUESTIONS.md``),
    so this returns the *content* only, in file order.
    """
    data = open(path, "rb").read()
    out = []
    index = 0
    while index < len(data) - 1:
        length = data[index]
        if 1 <= length <= 48 and index + 1 + length <= len(data):
            body = data[index + 1:index + 1 + length]
            if all(32 <= byte < 127 for byte in body):
                text = body.decode("ascii")
                if any(char.isalnum() for char in text):
                    out.append(text)
                    index += 1 + length
                    continue
        index += 1
    return out


def read_hcp_backup(path):
    """Unpack a ``.hcpp`` backup: returns ``{"name", "size", "hcp"}``.

    Format (measured): ``PPCH`` header, then a zlib stream that inflates to
    ``<u32 original_size><u32 name_len><name utf-8><u32 size><raw .hcp bytes>``.
    The payload is the *stored* (obfuscated) container, byte for byte.
    """
    import struct
    import zlib

    data = open(path, "rb").read()
    if data[:4] != b"PPCH":
        raise ValueError("not a PPCH backup: %r" % data[:4])
    for offset in range(0, min(len(data) - 2, 4096)):
        if data[offset] == 0x78 and data[offset + 1] in (0x01, 0x5E, 0x9C, 0xDA):
            try:
                stream = zlib.decompress(data[offset:])
            except Exception:
                continue
            if len(stream) < 12:
                continue
            original, name_len = struct.unpack_from("<II", stream, 0)
            name = stream[8:8 + name_len].decode("utf-8", "replace")
            payload_size = struct.unpack_from("<I", stream, 8 + name_len)[0]
            payload = stream[12 + name_len:12 + name_len + payload_size]
            return {"name": name, "original_size": original, "size": payload_size,
                    "hcp": payload, "stream_offset": offset}
    raise ValueError("no zlib stream found in %s" % path)


def read_hcp(project_dir):
    """Project index from ``<name>.hcp`` (see :mod:`autoshopkit.hcp`).

    Returns ``{"fields", "files", "xml"}`` where ``fields`` carries ``GCMModal`` (PLC series),
    ``Capbility`` (step capacity), ``CPUVersion``, ``HardwareFile``, ``projnameex``,
    ``historycount`` and ``files`` lists every component record (id, caption, filename, …).
    """
    import glob
    import os

    from . import hcp

    matches = sorted(glob.glob(os.path.join(project_dir, "*.hcp")))
    if not matches:
        return None
    return hcp.read_project(matches[0])
