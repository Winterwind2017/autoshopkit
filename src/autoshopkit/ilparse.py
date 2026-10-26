"""Parse AutoShop instruction-list text into instructions with operand roles.

The IL the editor holds is one instruction per line, operands separated by tabs or
spaces (the app reformats on paste), comments start with ``//``.  Two things this module
answers for the analyser:

* ``parse(text)`` → ``[{"instruction", "operands", "line", "raw"}]``;
* ``roles(instruction, operand_count)`` → a per-operand role list using ``"r"`` (read),
  ``"w"`` (written) or ``"?"`` (unknown).  Only instructions listed here are classified;
  everything else stays ``"?"`` so a caller never invents a role.

The table is deliberately conservative — a device is only called a *dead write* when
every reference to it is a definite write, which requires all of its instructions to be
known.
"""
from __future__ import annotations

import re

# bit devices read as contacts
READ_CONTACTS = {
    "LD", "LDI", "AND", "ANI", "OR", "ORI", "LDP", "LDF", "ANDP", "ANDF", "ORP", "ORF",
    "INV", "ANB", "ORB", "MPS", "MRD", "MPP", "MEP", "MEF", "BLD", "BLDI", "BAND", "BANI",
    "BOR", "BORI", "DBLD", "DBLDI", "DBAND", "DBANI", "DBOR", "DBORI",
}
# compare contacts: two read operands
READ_COMPARE_PREFIXES = ("LD=", "LD>", "LD<", "LD<>", "LD>=", "LD<=",
                         "AND=", "AND>", "AND<", "AND<>", "AND>=", "AND<=",
                         "OR=", "OR>", "OR<", "OR<>", "OR>=", "OR<=",
                         "LD&", "LD|", "LD^", "AND&", "AND|", "AND^", "OR&", "OR|", "OR^",
                         "LDZ", "ANDZ", "ORZ", "FLDD", "FANDD", "FORD")
# single-operand outputs (the operand is written)
WRITE_OUTPUTS = {"OUT", "SET", "RST", "PLS", "PLF", "ALT", "ALTP", "BOUT", "BSET", "BRST",
                 "DBOUT", "DBSET", "DBRST", "ANR", "ANRP", "ZSET", "ZSETP"}
# data transfer: (read indices, write indices) for a standard 2-operand move
MOVES_TWO = {"MOV", "MOVP", "DMOV", "DMOVP", "DEMOV", "DEMOVP", "CML", "CMLP",
             "DCML", "DCMLP", "XCH", "XCHP", "DXCH", "DXCHP"}
# block moves: source read, destination written, count read
MOVES_BLOCK = {"BMOV", "BMOVP", "FMOV", "FMOVP", "DFMOV", "DFMOVP", "SMOV", "SMOVP"}
# both operands are reset (write, write)
ZONE_RESET = {"ZRST", "ZRSTP"}
# compare: two read operands and a written result at the end
COMPARE = {"CMP", "CMPP", "DCMP", "DCMPP", "DECMP", "DECMPP"}
# zone compare: three read operands and a written result
ZONE_COMPARE = {"ZCP", "ZCPP", "DZCP", "DZCPP", "DEZCP", "DEZCPP"}
# arithmetic: (src…, dst) — dst written, inputs read
ARITH = {"ADD", "ADDP", "SUB", "SUBP", "MUL", "MULP", "DIV", "DIVP", "DADD", "DADDP",
         "DSUB", "DSUBP", "DMUL", "DMULP", "DDIV", "DDIVP", "WAND", "WANDP", "WOR",
         "WORP", "WXOR", "WXORP", "DAND", "DANDP", "DOR", "DORP", "DXOR", "DXORP",
         "DEADD", "DESUB", "DEMUL", "DEDIV", "INT", "BCD", "BIN", "FLT", "DINT",
         "DBCD", "DBIN", "DFLT", "ABS", "NEG", "SQR", "SWAP", "GRY", "GBIN"}
# read-modify-write single operand
INCDEC = {"INC", "INCP", "DEC", "DECP", "DINC", "DINCP", "DDEC", "DDECP",
          "ROR", "RORP", "ROL", "ROLP", "SHL", "SHR", "WSFR", "WSFL",
          # in-place transforms: the single operand is read and rewritten
          "NEG", "NEGP", "DNEG", "DNEGP", "ABS", "ABSP", "DABS", "DABSP",
          "SQR", "SQRP", "DSQR", "DSQRP", "INT", "INTP", "DINT", "DINTP",
          "BCD", "BCDP", "DBCD", "DBCDP", "BIN", "BINP", "DBIN", "DBINP",
          "FLT", "FLTP", "DFLT", "DFLTP", "SWAP", "SWAPP", "DSWAP", "DSWAPP",
          "GRY", "GRYP", "DGRY", "DGRYP", "GBIN", "GBINP", "DGBIN", "DGBINP",
          "CML", "CMLP", "DCML", "DCMLP", "SWAP"}
# no operand / control
NO_OPERAND = {"EI", "DI", "SRET", "IRET", "RET", "CJEND", "NEXT", "WDT", "WDTSP",
              "NOP", "END"}
# one operand, meaning depends on the document (labels, subprograms)
LABELS = {"LBL", "CJ", "CJP", "CALL", "CALLP", "SSRET", "MC", "MCR", "STL"}


def parse(text):
    """Split instruction-list text into instruction records (comments dropped)."""
    out = []
    for index, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        parts = [p for p in re.split(r"[\t ]+", line) if p]
        if not parts:
            continue
        out.append({"line": index, "instruction": parts[0].upper(),
                    "operands": parts[1:], "raw": line})
    return out


def roles(instruction, count):
    """Per-operand roles for one instruction (``r``/``w``/``?``)."""
    name = (instruction or "").upper()
    unknown = ["?"] * count
    if name in NO_OPERAND:
        return unknown
    if name in LABELS:
        return unknown                      # label / subprogram names, not devices
    if name in READ_CONTACTS:
        return ["r"] * count
    if name in WRITE_OUTPUTS:
        # OUT T0 K10 / OUT C0 K5: the coil is written, the preset/count is read
        return (["w"] + ["r"] * (count - 1)) if count else []
    if name.startswith(READ_COMPARE_PREFIXES):
        return ["r"] * count
    if name in ("LD>", "LD<", "LD="):
        return ["r"] * count
    if name in ("FOR", "FORP", "FORI") and count >= 1:
        return ["r"] + ["?"] * (count - 1)
    if name in ("XCH", "XCHP", "DXCH", "DXCHP") and count >= 2:
        return ["rw"] * count
    if name in ZONE_RESET and count >= 2:
        return ["w"] * count
    if name in COMPARE and count >= 3:
        return ["r", "r"] + ["w"] + ["?"] * (count - 3)
    if name in ZONE_COMPARE and count >= 4:
        return ["r", "r", "r"] + ["w"] + ["?"] * (count - 4)
    if name in MOVES_TWO and count >= 2:
        return ["r"] + ["w"] + ["?"] * (count - 2)
    if name in MOVES_BLOCK and count >= 2:
        return ["r", "w"] + ["r"] * (count - 2)
    if name in ARITH and count >= 2:
        return ["r"] * (count - 1) + ["w"]
    if name in INCDEC and count >= 1:
        return ["rw"] + ["?"] * (count - 1)
    return unknown


def analyse(text):
    """``{device: {"reads": [...], "writes": [...], "unknown": [...]} }`` for one text.

    Each reference is ``{"instruction", "line", "operand"}``.
    """
    buckets_by_role = {"r": ("reads",), "w": ("writes",), "rw": ("reads", "writes")}
    usage = {}
    for record in parse(text):
        names = record["operands"]
        for operand, role in zip(names, roles(record["instruction"], len(names))):
            if role == "?":
                continue
            target = usage.setdefault(operand.upper(),
                                      {"reads": [], "writes": [], "unknown": []})
            reference = {"instruction": record["instruction"], "line": record["line"],
                         "operand": operand, "role": role}
            for key in buckets_by_role.get(role, ()):
                target[key].append(reference)
    return usage


def merge(per_program):
    """Merge several ``analyse`` results (``{program: usage}``) into one map."""
    merged = {}
    for program, usage in per_program.items():
        for device, buckets in usage.items():
            target = merged.setdefault(device, {"reads": [], "writes": [], "unknown": [],
                                                "programs": set()})
            for key in ("reads", "writes", "unknown"):
                for reference in buckets.get(key, []):
                    item = dict(reference)
                    item["program"] = program
                    target[key].append(item)
            target["programs"].add(program)
    for device, buckets in merged.items():
        buckets["programs"] = sorted(buckets["programs"])
    return merged


def is_internal(device):
    """Internal devices whose values a program is normally expected to write."""
    if not device:
        return False
    return device[0].upper() in ("M", "D", "T", "C", "V", "Z", "S")
