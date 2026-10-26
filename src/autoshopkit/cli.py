"""Command line interface: ``python -m autoshopkit <verb>``.

Every verb prints JSON so an agent can consume it without parsing prose.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from .app import AutoShop, CMD, EXE
from . import win32 as w


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def get_app(args):
    app = AutoShop.attach()
    if app is None:
        if not getattr(args, "launch", False):
            raise SystemExit("AutoShop is not running (use --launch or the 'start' verb)")
        app = AutoShop.launch(getattr(args, "project", None))
    return app


def main(argv=None):
    p = argparse.ArgumentParser(prog="autoshopkit", description="Drive Inovance AutoShop")
    sub = p.add_subparsers(dest="verb", required=True)

    s = sub.add_parser("status", help="attach and print a summary")
    s.add_argument("--launch", action="store_true")
    s.add_argument("--project")

    s = sub.add_parser("start", help="launch AutoShop, optionally opening a project")
    s.add_argument("project", nargs="?")

    s = sub.add_parser("stop", help="close AutoShop")

    s = sub.add_parser("tree", help="dump the project tree")

    s = sub.add_parser("open", help="open a program/document from the project tree")
    s.add_argument("name")

    s = sub.add_parser("cmd", help="dispatch a WM_COMMAND by alias or numeric id")
    s.add_argument("name")

    s = sub.add_parser("compile", help="run 全部编译 and report messages")
    s.add_argument("--one", action="store_true", help="compile the current document only")
    s.add_argument("--timeout", type=float, default=90.0)

    s = sub.add_parser("output", help="read the information/output pane")

    s = sub.add_parser("il", help="read/write the instruction list of a document")
    s.add_argument("--doc", help="activate this document (title prefix) first")
    s.add_argument("--read", action="store_true")
    s.add_argument("--write", metavar="FILE", help="replace the program text with FILE's content")
    s.add_argument("--view", action="store_true", help="switch the active document to 指令列表 first")

    s = sub.add_parser("new", help="create a project (via 新建工程) and open it")
    s.add_argument("name")
    s.add_argument("--dest", help="directory that should hold the new project folder")

    s = sub.add_parser("dlfile", help="生成下载文件: write the offline *.updown artefact")
    s.add_argument("path", nargs="?", help="where to move the produced file")

    s = sub.add_parser("apply", help="write a program, convert, compile, report diagnostics")
    s.add_argument("file", help="file with instruction-list text (LF endings)")
    s.add_argument("--doc", default="MAIN", help="document to write into (default MAIN)")
    s.add_argument("--save", action="store_true", help="save the project afterwards")

    s = sub.add_parser("summary", help="project overview: programs, tree, symbols, monitor, compile")
    s.add_argument("--compile", action="store_true", help="also convert+compile first")

    s = sub.add_parser("hcp", help="read a .hcp project index (decrypts the container)")
    s.add_argument("--project", help="project directory or a .hcp file")
    s.add_argument("--xml", action="store_true", help="include the whole XML")
    s.add_argument("--write-xml", metavar="FILE",
                   help="encrypt this XML back into a .hcp (needs --project FILE.hcp)")

    s = sub.add_parser("illog", help="numbered IL from il_log.log (works for H5U)")
    s.add_argument("--project", help="project directory (defaults to the open project)")
    s.add_argument("--program", help="only this program (MAIN, SBR_xxx, FB:…)")
    s.add_argument("--paths", action="store_true", help="programs and step counts only")

    s = sub.add_parser("check", help="project health check (double coils, dead writes, …)")
    s.add_argument("--no-compile", action="store_true", help="skip the compile step")
    s.add_argument("--offline", metavar="DIR",
                   help="audit a saved project directory without starting AutoShop")

    s = sub.add_parser("save", help="save the project and report which files were rewritten")
    s.add_argument("--settle", type=float, default=3.0)

    s = sub.add_parser("symbols", help="read or extend the symbol table")
    s.add_argument("--add", nargs=2, metavar=("NAME", "ADDRESS"), help="append one symbol")
    s.add_argument("--note", default="", help="note for --add")
    s.add_argument("--row", type=int, default=0)

    s = sub.add_parser("monitor", help="read or extend the 元件监控表")
    s.add_argument("--add", nargs="+", metavar="DEVICE", help="append devices")
    s.add_argument("--row", type=int, default=0)

    s = sub.add_parser("crossref", help="device usage from the cross-reference")

    s = sub.add_parser("doctor", help="environment self-check (project, UIA, frida, editor)")

    s = sub.add_parser("dialogs", help="list open dialogs and their controls")
    s.add_argument("--close", action="store_true", help="cancel/close every listed dialog")

    s = sub.add_parser("shot", help="capture the main window as PNG")
    s.add_argument("path")

    s = sub.add_parser("commands", help="print the built-in command id table")

    args = p.parse_args(argv)

    if args.verb == "hcp":
        import os

        from . import hcp
        target = args.project
        if not target:
            app = AutoShop.attach()
            if not app:
                raise SystemExit("no AutoShop instance; pass --project DIR|FILE.hcp")
            target = app.project_path
        if os.path.isdir(target):
            found = sorted(name for name in os.listdir(target) if name.lower().endswith(".hcp"))
            if not found:
                raise SystemExit("no .hcp in %s" % target)
            target = os.path.join(target, found[0])
        if args.write_xml:
            xml = open(args.write_xml, "r", encoding="utf-16").read()
            hcp.write_project(target, xml)
            emit({"written": target, "bytes": os.path.getsize(target)})
            return 0
        report = hcp.read_project(target)
        report.pop("xml", None) if not args.xml else None
        report.pop("history", None)
        emit(report)
        return 0
    if args.verb == "illog":
        from . import projectfile
        project_dir = args.project
        if not project_dir:
            app = AutoShop.attach()
            if not app:
                raise SystemExit("no AutoShop instance; pass --project DIR")
            project_dir = app.project_path()
        log = projectfile.read_il_log(project_dir)
        if not log:
            emit({"project": project_dir, "found": False,
                  "hint": "转换/编译 once and AutoShop writes il_log.log"})
            return 1
        split = projectfile.split_il_programs(project_dir, log)
        if args.paths:
            emit({"project": project_dir, "steps": log["steps"],
                  "programs": {name: len(lines) for name, lines in split.items()}})
            return 0
        if args.program:
            lines = split.get(args.program, [])
            emit({"project": project_dir, "program": args.program,
                  "instructions": len(lines), "il": "\n".join(lines)})
            return 0
        emit({"project": project_dir, "steps": log["steps"],
              "programs": {name: "\n".join(lines) for name, lines in split.items()}})
        return 0
    if args.verb == "check" and args.offline:
        from . import check as project_check
        items = project_check.offline_findings(args.offline)
        emit({"findings": items, "counts": project_check.summarize(items),
              "project": args.offline, "offline": True})
        return 0
    if args.verb == "commands":
        emit(CMD)
        return 0
    if args.verb == "start":
        app = AutoShop.launch(args.project)
        emit({"pid": app.pid, "title": app.title})
        return 0
    if args.verb == "status":
        app = get_app(args)
        s = app.summary()
        s.pop("tree", None)
        emit(s)
        return 0
    if args.verb == "new":
        app, project = AutoShop.create_project(args.name, args.dest)
        emit({"pid": app.pid, "project": project, "title": app.title})
        return 0
    if args.verb == "stop":
        app = AutoShop.attach()
        emit({"closed": bool(app and app.close())})
        return 0

    app = get_app(args)

    if args.verb == "tree":
        emit([{"depth": d, "text": t} for d, t, _c, _h in app.tree_items()])
    elif args.verb == "open":
        doc = app.tree_open(args.name)
        emit({"document": hex(doc) if doc else None, "documents": [t for _h, t in app.documents()]})
    elif args.verb == "cmd":
        cid = CMD.get(args.name)
        if cid is None:
            cid = int(args.name, 0)
        app.command(cid)
        emit({"sent": cid, "dialogs": [w.window_text(h) for h in app.dialogs()]})
    elif args.verb == "compile":
        ok, lines = app.compile(all_programs=not args.one, timeout=args.timeout)
        emit({"ok": ok, "lines": lines})
    elif args.verb == "output":
        emit({"lines": app.output_lines()})
    elif args.verb == "il":
        if args.doc:
            if not app.activate_program(args.doc):
                raise SystemExit("program document %r is not open" % args.doc)
            time.sleep(0.4)
        if args.view:
            app.view_il()
        if args.write:
            with open(args.write, encoding="utf-8") as fh:
                text = fh.read()
            length = app.set_program_il(text)
            emit({"written": length, "output": app.output_lines()})
        else:
            emit({"il": app.program_il()})
    elif args.verb == "apply":
        with open(args.file, encoding="utf-8") as fh:
            text = fh.read()
        result = app.apply_program(text, document=args.doc, save=args.save)
        emit(result)
    elif args.verb == "summary":
        emit(app.project_summary(compile_now=args.compile))
    elif args.verb == "check":
        emit(app.project_check(compile_now=not args.no_compile))
    elif args.verb == "save":
        emit(app.save(settle=args.settle))
    elif args.verb == "symbols":
        if args.add:
            name, address = args.add
            written = app.add_symbol(name, address, args.note, row=args.row)
            emit({"written": written, "symbols": app.symbols()})
        else:
            emit({"symbols": app.symbols(), "columns": app.symbol_columns()})
    elif args.verb == "monitor":
        if args.add:
            emit({"written": app.add_monitor(args.add, start_row=args.row),
                  "rows": app.monitor_table()})
        else:
            emit({"rows": app.monitor_table()})
    elif args.verb == "crossref":
        emit({"usage": app.device_usage()})
    elif args.verb == "doctor":
        emit(app.doctor())
    elif args.verb == "dlfile":
        ok, path = app.generate_download_file(args.path)
        emit({"ok": ok, "path": path})
    elif args.verb == "dialogs":
        if args.close:
            emit({"closed": app.close_dialogs()})
        else:
            out = []
            for h in app.dialogs():
                out.append({"title": w.window_text(h), "rect": w.rect(h),
                            "controls": [{"cls": c.cls, "id": c.cid, "text": c.text, "rect": c.rect}
                                         for c in app.dialog_controls(h)]})
            emit(out)
    elif args.verb == "shot":
        emit({"size": app.snapshot(args.path), "path": args.path})
    return 0


if __name__ == "__main__":
    sys.exit(main())
