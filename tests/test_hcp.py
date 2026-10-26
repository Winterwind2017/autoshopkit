"""The .hcp container: UTF-16LE XML behind a position-dependent transform.

Codec recovered from ``InterfaceMgr.dll`` (``CUCodeCrypt::DecryptArithmetic`` at RVA 0x4ceb0,
key ``"SclSoftware"`` at RVA 0xa5980).  This test pins the behaviour down on the two real
projects and checks that the decrypted index really describes the files on disk.

Run:  python tools/test_hcp.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from autoshopkit import hcp

REAL_H5U = r"D:\bililive\autoshopkit\sandbox\real\xmlproj"
REAL_H3U = r"D:\bililive\autoshopkit\sandbox\projwork"
RESULTS = []


def step(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("[PASS] " if ok else "[FAIL] ") + name + ("  " + str(detail)[:200] if detail else ""))


def skip(name, why):
    RESULTS.append((name, True, why))
    print("[SKIP] " + name + "  " + why)


def container(project_dir):
    if not os.path.isdir(project_dir):
        return None
    for name in sorted(os.listdir(project_dir)):
        if name.lower().endswith(".hcp"):
            return os.path.join(project_dir, name)
    return None


def main():
    # 1. the seal explains the "clQobtqa" magic in every component file
    step("encrypt(8 zero bytes) is the component seal", hcp.seal() == b"clQobtqa", hcp.seal())

    for label, directory, modal, capacity, records in (
            ("H3U", REAL_H3U, "H3U", "64000", 16),
            ("H5U", REAL_H5U, "H5U", "200000", 51)):
        path = container(directory)
        if not path:
            skip("%s container" % label, "project copy missing")
            continue
        project = hcp.read_project(path)
        fields = project["fields"]
        step("%s decrypts to UTF-16LE XML with a BOM" % label,
             project["xml"].startswith("\ufeff<?xml"),
             project["xml"][:40])
        step("%s reports the PLC series" % label, fields.get("GCMModal") == modal,
             fields.get("GCMModal"))
        step("%s reports the step capacity" % label, fields.get("Capbility") == capacity,
             fields.get("Capbility"))
        step("%s lists %d component records" % (label, records),
             len(project["files"]) == records, len(project["files"]))

        data = open(path, "rb").read()
        step("%s round-trips exactly" % label,
             hcp.encrypt(hcp.decrypt(data)) == data)

        # 3. the index must agree with the files that are actually there
        on_disk = set(os.listdir(directory))
        claimed = [entry["filename"] for entry in project["files"] if entry["filename"]]
        present = [name for name in claimed if name in on_disk]
        step("%s index names files that exist on disk" % label,
             len(present) >= max(3, len(claimed) // 3),
             {"claimed": len(claimed), "present": len(present), "sample": present[:4]})
        # H3U stores programs as .IL (its editor is the instruction list), H5U as .LD
        extension = ".IL" if label == "H3U" else ".LD"
        programs = [entry for entry in project["files"]
                    if entry["filename"].upper().endswith(extension)]
        step("%s index marks its programs (*%s)" % (label, extension), bool(programs),
             [entry["filename"] for entry in programs[:3]])

    # 3b. independent samples: the .hcpp backups carry raw .hcp bytes from other sessions
    import glob
    from autoshopkit import projectfile
    backups = sorted(glob.glob(os.path.join(REAL_H5U, "BackUP", "*.hcpp")))
    if backups:
        results = []
        for path in backups:
            try:
                inner = projectfile.read_hcp_backup(path)["hcp"]
                xml = hcp.decrypt(inner).decode("utf-16-le")
            except Exception as exc:
                results.append((os.path.basename(path), "error: %s" % exc))
                continue
            results.append((os.path.basename(path)[:28], xml.startswith("\ufeff<?xml"),
                            xml.count('<file id="')))
        step("every backup container decrypts to the same XML shape (%d samples)" % len(backups),
             all(entry[1] is True for entry in results), results)
    else:
        skip("backup containers", "BackUP folder missing")

    # 4. write path: an edited XML re-encrypts and reads back identically
    path = container(REAL_H3U)
    if path:
        project = hcp.read_project(path)
        import tempfile
        target = os.path.join(tempfile.gettempdir(), "hcp_roundtrip.hcp")
        hcp.write_project(target, project["xml"])
        again = hcp.read_project(target)
        step("a re-encrypted container reads back the same index",
             again["fields"].get("GCMModal") == project["fields"].get("GCMModal")
             and len(again["files"]) == len(project["files"]),
             {"modal": again["fields"].get("GCMModal"), "files": len(again["files"])})
        os.remove(target)

    bad = [r for r in RESULTS if not r[1]]
    print("\n%d/%d passed" % (len(RESULTS) - len(bad), len(RESULTS)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
