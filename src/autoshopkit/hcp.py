"""Read and write the AutoShop project container (``.hcp``).

The container is not a binary structure: it is a **UTF-16LE XML document** protected by a
position-dependent byte transform.  Both the transform and the key were recovered from
``InterfaceMgr.dll`` (see ``docs/RECON.md`` and ``recon/HCP_CODEC.md``):

    KEY = b"SclSoftware"                      # 11 bytes, InterfaceMgr.dll .rdata RVA 0xa5980
    j = 0
    for i in range(len(data)):
        j = (j + 1) % 11
        b = data[i]
        if i % 2 == 0:  b ^= (i & 0xFF)
        data[i] = (b - KEY[j]) & 0xFF         # decrypt;  encrypt: ((b + KEY[j]) & 0xFF) ^ (i & 0xFF)
"""

import re

KEY = b"SclSoftware"


def decrypt(data):
    out = bytearray(data)
    j = 0
    for i in range(len(out)):
        j = (j + 1) % 11
        value = out[i]
        if i % 2 == 0:
            value ^= i & 0xFF
        out[i] = (value - KEY[j]) & 0xFF
    return bytes(out)


def encrypt(data):
    out = bytearray(data)
    j = 0
    for i in range(len(out)):
        j = (j + 1) % 11
        value = (out[i] + KEY[j]) & 0xFF
        if i % 2 == 0:
            value ^= i & 0xFF
        out[i] = value
    return bytes(out)


def seal():
    """The 8-byte marker at offset 0x1f of every component file (enciphered zeros)."""
    return encrypt(bytes(8))


def read_project(path):
    """Decrypt a ``.hcp`` and return the project index.

    ``{"path", "xml", "fields": {...}, "files": [{"id", "caption", "alias", "filename",
    "file_type", "prog_type", "created", "modified"}], "raw_fields": {...}}``
    """
    data = open(path, "rb").read()
    xml = decrypt(data).decode("utf-16-le")
    fields = {}
    for name, value in re.findall(r"<(\w+)>([^<]*)</\1>", xml):
        fields.setdefault(name, value)
    files = []
    for match in re.finditer(r'<file id="(\d+)">(.*?)</file>', xml, re.S):
        body = match.group(2)
        entry = {"id": int(match.group(1))}
        for name, value in re.findall(r"<(\w+)>([^<]*)</\1>", body):
            entry[name.lower()] = value
        files.append({
            "id": entry["id"],
            "caption": entry.get("caption", ""),
            "alias": entry.get("alias", ""),
            "filename": entry.get("filename", ""),
            "file_type": entry.get("filetype", ""),
            "prog_type": entry.get("progtype", ""),
            "created": entry.get("createtime", ""),
            "modified": entry.get("lastmodifytime", ""),
        })
    return {"path": path, "size": len(data), "xml": xml, "fields": fields, "files": files,
            "history": re.findall(r"<v\d+>(.*?)</v\d+>", xml, re.S)}


def write_project(path, xml):
    """Encrypt an XML document back into a ``.hcp`` (the app's own write path)."""
    data = xml.encode("utf-16-le")
    if not data.startswith(b"\xff\xfe"):
        data = b"\xff\xfe" + data
    open(path, "wb").write(encrypt(data))
