# Attack plan: dependency graph and status

The user asked to *map the dependencies between the targets first* and then take
them one by one "in the way most likely to succeed".  This is that map.  Levels
are strict: a level-N capability is only reliable once level-N−1 is verified.

```
L0  window model / command dispatch      <- everything depends on this
 ├── L1a project lifecycle (launch/open/save/close)
 ├── L1b project tree read + open program
 │     └── L2a document activation (tab cycling)
 │           └── L3a instruction-list view + program read
 │                 └── L3b program write  (real input; IL syntax; LF only)
 │                       └── L4  conversion + compile + diagnostics
 │                             ├── L5a download / 生成下载文件
 │                             └── L5b monitor / online edit / write  (needs PLC)
 ├── L1c dialog layer (enumerate / fill / click)
 │     ├── L2b new project wizard
 │     ├── L2c ladder element dialogs (常开触点 …)
 │     └── L5a/L5b prompts
 └── L1d screenshot / OCR-free reading of custom-drawn views
```

## What is done and verified

| # | Capability | API | Evidence |
| --- | --- | --- | --- |
| L0-1 | attach to a running AutoShop, find the MFC frame | `AutoShop.attach()` | `python -m autoshopkit status` |
| L0-2 | launch with a project argument → project opens, doc loaded | `AutoShop.launch(path)` | e2e step 1 (~2 s) |
| L0-3 | dispatch any command by id | `command(id)` / `cmd(alias)` | 新建工程 dialog, 编译, 视图切换 all executed |
| L0-4 | command catalogue (261 menu commands, toolbar ids, accelerators) | `CMD`, `recon/catalog_commands.json` | `docs/COMMANDS.md` |
| L1a-1 | save project; close with "save changes?" answered; force fallback | `cmd("save_project")`, `close()` | e2e step 10 |
| L1b-1 | read the whole project tree (720 entries: 程序块 / 符号表 / 系统参数 / 通讯配置 / 指令集) | `tree_items()` | e2e step 2 |
| L1b-2 | open a program / document from the tree, located by exact row geometry | `tree_open(name)` | opens 符号表 on a cold project in ~3 s (e2e step 4) |
| L2a-1 | activate an already-open document (Ctrl+Tab cycling) | `activate_document(name)` | title + Scintilla parent identity |
| L2a-2 | enumerate open documents / active document | `documents()`, `active_doc_hwnd()` | e2e step 4 |
| L3a-1 | switch the active document to the instruction list | `view_il()` / `cmd("view_il")` | Scintilla appears inside the doc |
| L3a-2 | read the program text | `program_il()` | e2e step 6 |
| L3b-1 | write the program text (select-all + paste, verified by read-back) | `set_program_il(text)` | e2e step 7 |
| L4-1 | run 编译 / 全部编译 and capture the message pane | `compile()` | e2e step 8/9: `统计 - (0)错误,(31)步占用` |
| L4-2 | read the output pane on demand | `output_lines()` | compile / 转换 / 下载 panes |
| L1c-1 | list dialogs with every control (class, id, text, rect) | `dialogs()`, `dialog_controls()` | 新建工程, 常开触点, 下载, 监控 prompts |
| L1c-2 | press a dialog button / set an edit across processes | `click()`, `set_control_text()` | dialog buttons verified; edits need remote buffer (implemented) |
| L1d-1 | window screenshot (PrintWindow, DPI aware) | `snapshot(path)` | `recon/runtime/*.png` |
| L0-5 | **UI Automation** read/write layer (cross-bitness) | `autoshopkit/uia.py` | status bar text, symbol cells, tree cross-check |
| L0-6 | environment self-check for agents | `doctor()` | `tools/e2e_apply.py` step 1 |
| L0-8 | **whole-project summary** (programs, tree size, symbols, monitor, cross-ref, optional compile) | `project_summary(compile_now=)` | `tools/e2e_project.py` 9/9 |
| L1a-4 | save with **per-file verification** (reports which components were rewritten) | `save()` | `tools/e2e_project.py` step 4 |
| L4-3 | **one-call authoring loop** write → convert → compile → structured diagnostics | `apply_program(text, save=False)` | `tools/e2e_apply.py` 7/7 |
| L4-4 | structured diagnostics (`level/source/line/column/message`, summary counters) | `autoshopkit/diagnostics.py` | located error `NOP K1 K2` at line 2 |
| L4-5 | **project health check** (double coils, empty programs, uncalled subroutines, unused symbols, dangling monitor rows, dead writes, capacity) | `project_check()` / `autoshopkit/check.py` | `tools/e2e_check.py` 11/11, both directions |
| L4-6 | **IL operand roles** (read / write / read-write) and device read-write pairing | `autoshopkit/ilparse.py` | dead write located at `OUT MAIN:4` |
| L1d-2 | status-bar message (impossible with `SB_GETTEXT*`) | `statusbar_text()` | `就绪`, command hints |
| L3d-1 | **write 元件监控表 rows** (device names) and read the table offline | `add_monitor()` / `monitor_table()` | `tools/e2e_monitor.py` 6/6 (persists across reload) |
| L0-7 | decode the project files (`VarList.gdt`, `MAIN.mon`, `CrossTable.crs` chunk framing) | `autoshopkit/projectfile.py` | symbol / monitor / cross-reference tables read without the GUI, all cross-checked |
| L3a-3 | **multi-program read and write** (MAIN + subprograms + interrupt) in one call | `read_programs()` / `apply_programs({doc: text})` | `tools/e2e_programs.py` 9/9 |
| L3e-1 | device cross-reference / usage (device → program + instruction) | `crossref()` / `device_usage()` | `tools/e2e_programs.py` step 8 |
| L3c-1 | **write, read back and enumerate 符号表 rows** (符号 + 地址 + 注释) and have them resolve | `add_symbol()` / `read_symbol()` / `read_symbols()` | `tools/e2e_symbols.py` 8/8 |
| L5a-0 | 下载 prompt reached and readable | `cmd("download")` | "在下载前是否需要重新编译 …" |
| L5a-1 | **offline download artefact** 生成下载文件 → `*.updown.down` | `generate_download_file(path)` | e2e step 10: 1294-byte file produced, "生成文件成功！" |
| L2b-1 | **create a project** 新建工程 → reopen at a chosen folder | `create_project(name, dest)` | `tools/e2e_create.py` 6/6 in 9 s |
| L5b-0 | 监控 prompt reached and readable | `cmd("monitor")` | "连接状态：未连通！…" |
| L5b-1 | 离线调试 command identified and dispatched | `command(33198)` | H3U: no effect, no child process — see `docs/RECON.md` §10 |
| L5b-2 | **monitor list authored and read back** (no PLC needed) | `add_monitor(devices)` / `monitor_table()` | `tools/e2e_monitor.py` 6/6 |
| L5b-3 | live monitor values (当前值 column) | — | still needs a PLC: the column stays 0 and 监控 answers 连接状态：未连通 |
| L2c-0 | ladder element dialog reached and enumerated | `cmd("no_contact")` | ComboBox 1045 / Edit 1065 / 确定 |

**Acceptance:** `python tools/e2e.py` → 11/11 steps pass, three consecutive runs
(2026-10-26).  It copies a real project to `sandbox/e2e`, writes `LD X0 / OUT Y0`
into MAIN, compiles, saves and closes.

## What is partial

| Capability | State | Blocker / next action |
| --- | --- | --- |
| L2b-2 保存路径 inside 新建工程 | app-owned: it recomputes `Documents\<name>\` and discards anything typed | create with the default, then move the folder (`create_project` does this); driving the `…` folder picker is untried |
| L2b-3 编辑器 / 系列与型号 in 新建工程 | `CB_SETCURSEL` by index works; item strings unreadable (owner-draw) | select by index and verify through the created project's tree root (`<name> [H3U]`) |
| L2c ladder element dialogs | dialog reached, buttons clickable | combo items unreadable via `CB_GETLBTEXT`; type the device class + number with real keys |
| L3b-2 IL syntax coverage | **27 forms compile clean**, including `MPS/MRD/MPP`, `CJ`+`LBL`, `CALL <subprogram>`, `FOR`/`NEXT`, `STL/RET`, `DMOV`, `ZRST`, `MC`/`MCR`, `CMP`, `ZCP`, `XCH`, `SWAP`, `NEG`, `BMOV`, multi-network — see `docs/IL-results.md` | add symbolic operands and motion instructions |
| L4-7 | **pure-logic tests** for the IL role table and findings (no AutoShop) | `tools/test_ilparse.py` | 17/17 in under a second |
| L1b-3 | **ladder file text**: element operands/expressions and network comments read out of `.LD` | `projectfile.read_ld_text()` | verified on 8 controlled `.LD` captures |
| L1b-3b | **H5U symbol/variable tables** (`VarList.gdt` without addresses + `VarNameAndAddr.csv` with 0X addresses) | `projectfile.read_symbols` / `read_var_table` | real project: 613 symbols, 1412 variables |
| L1b-8 | **`.hcp` container**: decrypt to the UTF-16LE XML project index (series, capacity, hardware dll, all component records) and encrypt back | `autoshopkit.hcp`, `projectfile.read_hcp`, `autoshopkit hcp --project DIR` | `tools/test_hcp.py` 16/16 on H3U + H5U |
| L1b-6 | **H5U IL channel**: per-program IL from the compile log (`il_log.log`), including the `P`/`SRET`/`FBRET` split and FB instances | `projectfile.read_il_log` / `split_il_programs`, `AutoShop.read_programs` fallback, `autoshopkit illog` | `tools/test_h5u_il.py` 10/10 |
| L1b-7 | **ladder decode**: element records (graph links + kind + operand text), no coordinates | `projectfile.read_ladder()` | `tools/test_ladder.py` 15/15 on a real project |
| L1b-5 | **offline audit** of a saved project (no AutoShop): unused symbols, dangling monitor rows, cross-reference summary, ladder readability | `check.offline_findings()` / `autoshopkit check --offline DIR` | `tools/test_offline_audit.py` 10/10 |
| L1b-4 | **`.hcpp` backup**: `PPCH` + zlib → name, sizes, byte-exact `.hcp` copy | `projectfile.read_hcp_backup()` | `tools/test_projectfile.py` |
| L0-9 | **agent-facing CLI**: 21 verbs, every one printing JSON (`summary`, `check`, `apply`, `symbols`, `monitor`, `crossref`, `save`, …) | `python -m autoshopkit <verb>` | `tools/e2e_cli.py` 17/17 as subprocesses |
| L1d-2 reading the ladder canvas | screenshot only | the canvas is custom-drawn; use the Frida text tap for labels or an OCR step |
| 符号表 *bulk* read speed | `read_symbols()` is exact but costs ≈6 s/row (three click+F2+UIA reads); the plaintext `VarList.gdt` (after 保存工程) is the fast offline route | next: map `VarList.gdt`'s record framing |

## What is blocked (and why)

| Capability | Blocker |
| --- | --- |
| L5b real monitor / write / run-stop | needs a PLC (USB/Ethernet) or the H5U offline debugger; this build's wizard offers no H5U family and 离线调试 does nothing on H3U, so no live loop could be established on this machine |
| L5a real download (to a PLC) | 下载 needs a connected PLC; the offline `生成下载文件` flow is automated and verified |
| offline program authoring by writing project files | `.hcp` / `*.LD` / `Output.prg` / some `.compile` files are obfuscated; see `docs/OPEN-QUESTIONS.md` |
| driving the ladder canvas geometrically | no window handles and no accessibility tree inside the view; not needed while the IL channel works |

## Suggested order for the next session

1. **IL corpus + syntax table** — more instruction forms (stack ops, `CJ`/`CALL`,
   `FOR`, multi-network boundaries), each with compile evidence.
2. **Monitor loop with hardware** — start the bundled H5U simulator (or attach a
   PLC) and turn `监控` / `写入` / `运行` from "prompt reached" into a live loop.
3. **Symbol table write** (VSFlexGrid) — only needed for variable-mode projects;
   device-mode programs compile without it (the earlier `符号未定义` was a `\r`
   inside the operand, see `docs/IL.md`).
3. **New-project wizard** — gives repeatable fixtures for everything above.
4. **`生成下载文件`** (offline) then real 下载 once a PLC/simulator is attached.
5. **File format** — only if offline project generation is required (Ghidra on
   `EncryptionToolDll.dll` / `CHcppFile::DecompressProj`).
