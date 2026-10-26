"""Search the recovered command catalogue by keyword (default: comms-related)."""
import io
import json
import sys

PATH = r"D:\bililive\autoshopkit\recon\catalog_commands.json"


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            if isinstance(value, (list, dict)):
                yield from walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


def main(argv):
    keys = argv[1:] or ["通讯", "通信", "连接", "设置", "驱动"]
    data = json.load(io.open(PATH, encoding="utf-8"))
    seen = set()
    for item in walk(data):
        label = item.get("label") or item.get("text") or ""
        cid = item.get("id") or item.get("cmd") or item.get("command")
        if not label or not any(k in label for k in keys):
            continue
        if (cid, label) in seen:
            continue
        seen.add((cid, label))
        hint = item.get("hint") if isinstance(item.get("hint"), str) else ""
        print("%-8s %-30s %s" % (cid, label[:28], hint[:44]))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
