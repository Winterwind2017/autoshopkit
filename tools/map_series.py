"""Map the 新建工程 系列/型号 combo indices to PLC families.

The combos are owner-draw (``CB_GETLBTEXT`` returns nothing), so the family is
read back from the created project's tree root label, e.g. ``demo [H3U]``.
"""
import ctypes
import os
import shutil
import sys
import time

sys.path.insert(0, r"D:\bililive\autoshopkit")

from autoshopkit.app import AutoShop

DEST = r"D:\bililive\autoshopkit\sandbox\series"


def family(app):
    for depth, text, _c, _h in app.tree_items():
        if depth == 0:
            return text
    return ""


def main(argv):
    series_range = range(int(argv[1]) if len(argv) > 1 else 8)
    model_index = int(argv[2]) if len(argv) > 2 else None
    os.makedirs(DEST, exist_ok=True)
    rows = []
    for idx in series_range:
        name = "ser%d" % idx
        target = os.path.join(DEST, name)
        if os.path.isdir(target):
            shutil.rmtree(target)
        try:
            app, project = AutoShop.create_project(name, DEST, series_index=idx,
                                                   model_index=model_index)
            label = family(app)
            rows.append((idx, label))
            print("series_index=%d -> %r" % (idx, label), flush=True)
            app.close()
        except Exception as exc:  # noqa: BLE001 - report and continue
            rows.append((idx, "ERROR %s" % exc))
            print("series_index=%d -> ERROR %s" % (idx, exc), flush=True)
        time.sleep(1.0)
        if os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)
    print("\nsummary:")
    for idx, label in rows:
        print("  %d : %s" % (idx, label))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
