# AutoShop automation — reconnaissance record

Target: `D:\Inovance Control\AutoShop\AutoShop.exe` — 汇川 AutoShop **V4.11.0.5**
(ProductVersion 4.11.0.5, 55 MB PE32 x86, MFC + MFC Feature Pack, DuiLib only in
some dialogs).  Analysis date 2026-10-26.  Every claim below is marked with how
it was obtained: **[static]** = read from the shipped binaries/resources,
**[runtime]** = observed in the live process, **[file]** = from on-disk
artefacts of a project.

---

## 1. Process and window model  [static + runtime]

| Item | Observation |
| --- | --- |
| Process | single instance guard (`single.dll`), window class `Afx:00400000:8:...` |
| Frame title | `AutoShop V4.11.0.5  <project dir> - [<document>]` (plus `*` when dirty) |
| Menu bar | **not** a Win32 menu: `GetMenu(frame)` returns `NULL`; the menu is a `CMFCMenuBar` toolbar titled `菜单` (control id 59398) |
| Toolbars | `Afx:ToolBar` windows: `标准工具栏`(59392), `编译工具栏`(32854), `PLC工具栏`(32972), `梯形图工具栏`(32917), `顺序功能图`(33011), `缩放工具栏`(33016), `标签工具栏`(32959), `菜单`(59398), `状态工具栏`(33444) |
| Project tree | `SysTreeView32`, control id **1**, inside dock pane `工程管理` (32803) |
| Output pane | dock pane `信息输出窗口` (32804) → `Afx:TabWnd` (101) → **owner-draw ListBox** (ids 1–4) + `VSFlexGrid8N` siblings; tabs: 编译 / 通讯 / 转换 / 查找结果 / 交叉引用 |
| Documents | tabbed MDI: MDI client `MDIClient` (59648), each doc is an `Afx:...:b:` frame with an `AfxFrameOrView90u` view |
| Instruction-list editor | a real **Scintilla** control inside the document view (class `Scintilla`), reachable per document |
| Symbol table | its own document whose body is a `VSFlexGrid8N` (Visual Studio FlexGrid ActiveX, `vsflex8n.ocx`) |
| Status bar | `Afx:StatusBar` (59393); it does **not** answer `SB_GETTEXTW`/`SB_GETPARTS` cross-process, but the text is visible in screenshots ("就绪", "切换为指令列表编辑器", …) |

Rendering artefacts worth knowing: the app is DPI-aware; a *non*-DPI-aware helper
sees coordinates divided by the scale factor, so call
`SetProcessDpiAwareness(2)` before using screen coordinates.

## 2. Command dispatch  [static]

There is no COM/IDispatch, no `DllGetClassObject`, no registered CLSID for
AutoShop (`HKCR\CLSID` search: 0 hits), and no DDE/automation server.  What it
does have is a plain MFC command table: every menu/toolbar/accelerator entry
carries a 16-bit command id, and `WM_COMMAND(frame, id)` executes it exactly like
a click.  Ids were recovered from three resources of `AutoShop.exe`:

* **MENU** (78 resources, ids 128…): the classic template is
  `WORD flags, WORD id, UTF-16 text` — but popup items in this build *omit* the
  id word, which is why naive parsers mis-read every popup label.
* **RT_TOOLBAR** (241, 17 resources): `WORD ver, WORD w, WORD h, WORD n, WORD ids[n]`.
* **ACCELERATOR** (9, 22 tables): `WORD flags, WORD key, WORD cmd`.
* plus the **STRINGTABLE** (4246 entries) that supplies the MFC status-bar hints
  for those ids.

`docs/COMMANDS.md` lists the verified ids; `tools/build_catalog.py` +
`tools/scan_menu_ids.ps1` reproduce the extraction.  Confirmed by execution:
`32858` 新建工程, `32859` 打开工程, `32861` 保存工程, `32893` 监控, `32882` 下载,
`32992` 编译, `32993` 全部编译, `32867` 查看→指令列表, `32868` 查看→梯形图,
`32931` 梯形图→常开触点, `33181` 工程属性.

## 3. Project files  [file]

A project is a **folder**, `*.hcp` is only the entry file:

```
<project>/<name>.hcp         15 KB  obfuscated aggregate (see below)
<project>/MAIN.LD, SBR_001.LD, INT_001.LD   1234 B each  ladder program
<project>/VarList.gdt  DeviceTable.dev  CrossTable.crs  Config.sdt
<project>/PortConfig.cfg  ElemUseInfo.esi  moduleCfg.data  config.ini
<project>/Compile/<PROG>.compile             per-program compile record
<project>/ProgInfo.dat  steps.dat  Output.prg  Output.sdt
<project>/Temp, Compile/Temp
```

Every component file starts with the same 255-byte header:
`"AutoShop"`, then version strings (`2.0`…`2.4`), then at offset 0x1F the eight
bytes **`clQobtqa`** (a key/flag string, present in all files), then zeros.

`MAIN.compile` is readable plaintext (program name + UTF-8 network comments +
`FEND`), while `SBR_001.compile`, `Output.prg` and `.hcp` are byte-obfuscated
(same scheme, ~11-byte period, high bytes limited to ASCII letters).  The
encoder is *not* identified yet — see `docs/OPEN-QUESTIONS.md`; the working
hypothesis is that `clQobtqa` is the key for the routine in `EncryptionToolDll.dll`
/ the `CHcppFile::DecompressProj` path in `AutoShop.exe`.

**Consequence:** the supported authoring channel is *not* file writing but the
instruction-list editor (below).  File-level editing would require cracking the
obfuscation first.

## 4. Instruction list editor = the program interface  [runtime]

`查看 → 指令列表 (32867)` swaps the active document's ladder view for a
**Scintilla** editor holding the program as IL text:

```
//网络注释
LD		 X0
OUT		 Y0
```

* read: `SCI_SELECTALL (2013)` + `SCI_GETSELTEXT (2161)` with a buffer allocated
  in the target process (a local pointer does not work cross-process);
  `SCI_GETTEXT (2183)` returned NULs and is *not* usable.
* write: **real input only** — select all + paste.  `SCI_SETTEXT (2181)` changes
  the buffer and the text even appears on screen, but the document model never
  learns about it, so the compiler keeps the old program.  Pasting makes AutoShop
  reformat the text (tabs) and immediately run 转换 (conversion).
* line endings must be **LF**; a `\r` becomes part of the operand and the
  converter reports `X0\r: 符号未定义`.
* devices are accepted directly (`LD X0`, `OUT Y0` compile clean); a ladder
  edit that leaves a rung open reports `M0: 开路` at conversion time.

## 5. Compile / conversion diagnostics  [runtime]

`编译` writes to the 信息输出窗口, e.g.

```
------  AutoShop :  工程（<name>）  编译消息  ------
开始编译...
警告  INT_001.LD, 中断子程序没有指定中断号，不会被编译
正在编译系统配置信息...
MAIN.LD
正在生成UCODE文件...
注释-(0)步占用, 子程序名称+网络注释-(151)步占用/(500)设置容量
统计 - (0)错误,(31)步占用/(63500)总容量
```

The list box rows carry **no retrievable string** (`LB_GETTEXT` returns four
NUL characters per row — the app paints from its own array), so the text is read
by hooking the GDI text calls in-process (Frida, `autoshopkit/hooks.py`).  The
pane appends incrementally *and* occasionally repaints every row, so the capture
is collapsed by first occurrence and cut at the `统计 -` line.

## 6. Tree, documents, dialogs  [runtime]

* `TVM_GETITEMW` works cross-process **only** with a hand-packed win32-layout
  `TVITEMW` (40 bytes); `TVM_GETCOUNT`/`TVM_GETITEMHEIGHT` return 0.
* **`TVM_GETITEMRECT` does work** — it needs a *remote* `RECT` whose `left` member
  carries the hitem (a local pointer silently returns 0, which is why row geometry
  first looked unavailable).  `tree_item_rect()` uses it, so a row can be located
  exactly: `TVM_ENSUREVISIBLE` → `TVM_GETITEMRECT` → double click the centre.
* **Keyboard navigation does not move the caret**: posted `WM_KEYDOWN` *and*
  genuine arrow keys leave `TVM_GETNEXTITEM/TVGN_CARET` on the root (the app only
  moves the selection on a click).  Keyboard walking is therefore useless here.
* A freshly copied project opens **collapsed**, and a collapsed row has no usable
  rect, so `tree_open()` first expands everything with recursive `TVM_EXPAND`
  (`tree_expand_all`).  Even then the rect can be one row off while the tree is
  still populating, so the caret is used as the oracle: click, read the caret,
  and if it is a different row shift the click by `target_rect.top - caret_rect.top`
  and retry (≤4 times).  With that the row opens in ~3 s on a cold project.
* **Folder rows need care.** `元件监控表` is a folder whose document is its `MAIN`
  child.  A double click on the folder row *toggles* it instead of opening the child,
  and a collapsed child has no usable rect (`TVM_GETITEMRECT` answers with the
  neighbour's rect — this cost several false "row not found" runs).  `open_tree_child()`
  therefore expands the parent with `TVM_EXPAND`, clicks once and verifies through
  `TVM_GETNEXTITEM(TVGN_CARET)`, and only then double-clicks; success is judged by a
  **new document handle**, never by the title (the child is called `MAIN`, like the
  ladder document).
* Opening a tree entry needs a **genuine double click** (`WM_LBUTTONDBLCLK`
  posted synthetically is ignored).
* `SetFocus` from outside only works after `AttachThreadInput` to the target
  thread (`focus_window()`); a synthetic click alone does not move focus.
* Documents switch with **Ctrl+Tab** cycling: `WM_MDIACTIVATE` is accepted by
  the MDI client but the visible tab does not change.
* Dialogs (`#32770`) enumerate and click fine cross-process (`BM_CLICK`), and
  `WM_SETTEXT` works once the string lives in the target's address space.
  Combos in the ladder element dialogs are owner-draw: `CB_GETLBTEXT` yields
  empty strings, so their items must be chosen with real keyboard input.

## 7. Creating a project  [runtime]

`文件 → 新建工程 (32858)` opens a `#32770` dialog: `Edit 1052` 工程名,
`Edit 1056` 保存路径 + `Button 1053` (…), `ComboBox 1046` 编辑器 (3 items),
`ComboBox 2969` 系列 (8 items) + `ComboBox 1045` 型号 (3 items),
`Edit 1048` 工程描述, `Button 1380` 新建工程 / `Button 1145` 临时工程,
`Button 1` 确定 / `Button 2` 取消.

Behaviour that had to be discovered:

* **`WM_SETTEXT` returns 0 and real clicks do nothing** on the two edits, yet
  `WM_CHAR` inserts characters (`GetWindowTextLength` grows, the field renders
  them).  Text entry therefore uses `WM_CHAR` per character (`type_chars`).
* The app **owns 保存路径**: any typed path is replaced by
  `<Documents>\<工程名>\`, so a project is always created under Documents.  To
  put it elsewhere, create it, close AutoShop, move the folder and relaunch
  (`AutoShop.create_project`).
* 确定 on an existing folder asks `文件夹已存在，是否覆盖原文件夹？`.
* The combos are owner-draw (`CB_GETLBTEXT` → empty).  **`CB_SETCURSEL` alone is
  ignored** — it sends no `CBN_SELCHANGE`, so the app keeps its old value (verified:
  every index still produced an H3U project).  `set_combo_index()` posts
  `WM_COMMAND(MAKEINTRESOURCE(id) | CBN_SELCHANGE<<16)` to the dialog as well.
  With that, the 系列/型号 combo maps to (read back from the created project's tree
  root): 3 = `H3U`, 4 = `H2U-XP`, 5 = `H1U-XP`, 6 = `H0U-XP`, 7 = `IOT-WL`;
  indices 0–2 selected module/catalog roots instead of a CPU.
* A created H3U project contains `MAIN.LD / SBR_001.LD / INT_001.LD`, `符号表`,
  `VarList.gdt`, `Config.sdt`, … and compiles as-is.

## 8. Offline download artefact  [runtime]

`PLC → 生成下载文件 (33186)` opens `下载选项` (#32770): 文件类型 PLA/物联网,
options 应用程序 / 系统参数 / 注释信息 / 软元件内存 / 禁止上载 / 上载加密 /
下载加密, buttons `生成文件 (1436)`, `生成文件(物联网专用) (1437)`, `关闭 (2)`.

`生成文件` then opens the **Windows shell 另存为 dialog** (breadcrumb + ShellView
+ `Edit` filename box + `Button 1 保存`).  That dialog is picky:

* `WM_SETTEXT` into its filename edit, `BM_CLICK` on 保存, `WM_COMMAND(IDOK)`,
  plain Enter and Alt+S are **all ignored**;
* it accepts **genuine typing in the filename field**: click the bottom-most
  `Edit`, `Ctrl+A`, paste, `Enter`.  Pasting a **full path** makes it save exactly
  there (a bare name goes to the folder it used last time);
* AutoShop then reports `生成文件成功！` and, if the target exists,
  `该文件已存在是否覆盖？` (是/否);
* produced file: `<name>.updown.down` (≈1.3 KB, obfuscated);
* a leftover `下载选项` dialog makes the *next* run fail — dismiss dialogs before
  and after (`_dismiss_all`).

## 9. Symbol table (符号表)  [runtime, solved]

The 符号表 document is a single `VSFlexGrid8N` ActiveX with five **sheet tabs**
(自定义元件 / 系统M元件 / 系统D元件 / 系统SM元件 / 系统SD元件) and the columns
**符号 | 地址 | 错误码 | 注释** (错误码 is collapsed to ~1 px in the normal view).

Window messages are not enough: cells carry no window text, `WM_SETTEXT` on the
in-cell editor returns 0, and no posted/real `Tab`/`Enter` commits the edit.  The
working path is **UI Automation**:

* the grid exposes its *header cells* (`符号`, `地址`, `注释`) and `Row 0..N`
  items, each with a real bounding rectangle — that is how column x / row pitch
  are measured at runtime (`symbol_columns()`), so no pixel guessing;
* while a cell is being edited, the editor appears as an element whose class starts
  with **`ATL:`** and which supports **`ValuePattern`** (read *and* `SetValue`) — after
  `QueryInterface` to `IUIAutomationValuePattern`, which comtypes requires because
  `GetCurrentPattern` returns a bare `IUnknown`.
* **the `ATL:` hash differs per control** — the 符号表 editor was `ATL:697A8F20`, the
  元件监控表 editor `ATL:503B8F20`.  An exact-class search therefore found one grid's
  editor and silently missed the other's (this was the real reason monitor writes kept
  "succeeding" without effect).  Match on the `ATL:` **prefix** and scope the search to
  the grid window.
* comtypes hands back a NULL `POINTER(IUnknown)` when `FindFirst` finds nothing, and such
  a pointer is **truthy** — a plain `if element:` check treats "not found" as success.
  The helper now inspects the raw pointer value.

Recipe (`AutoShop.add_symbol`):

1. click the 自定义元件 tab at grid-client `(60, 28)`;
2. click the target cell, post `WM_CHAR` to the grid so the in-cell editor opens;
3. `ValuePattern.SetValue(text)` on the `ATL:697A8F20` element;
4. commit by clicking another cell (a focus change commits; `Enter` alone does not);
5. a row needs **both** 符号 and 地址 to register — a name alone is ignored.

**Bulk read:** `read_symbols()` walks rows until the 符号 cell is empty (≈6 s per
row, because each row costs three click+F2+UIA reads).  Symbol names are
**truncated to 8 characters** by the app — `SECOND_SYM` comes back as `SECOND_S`,
`THIRD_SYM` as `THIRD_SY` (same values in `VarList.gdt`).

**On disk (after 保存工程):** `VarList.gdt` carries the names, addresses and notes
in **plain UTF-8** after its 255-byte header (288 bytes for one symbol, 330 for
three), e.g. `SECOND_S…M401…note two`.  That makes an offline bulk read possible
without parsing the obfuscated `.hcp`, even though the exact record framing (length
bytes and padding) is not fully mapped yet.

**Reading back** works through the same editor: clicking a cell does *not* open it,
but `F2` enters edit mode without changing the content, so
`ValuePattern.CurrentValue` reports the committed text (`read_symbol(row)` returns
`{'symbol','address','note'}`; `Escape` closes the editor).

Verified by `tools/e2e_symbols.py` (7/7): after writing `BTN_A = M200`,
`LD BTN_A / OUT Y0` compiles with `统计 - (0)错误`, while `LD ZZZ_NOPE` still
reports `符号未定义` (negative control).  Note the IL editor upper-cases operands.

## 9b. UI Automation  [runtime]

`UIAutomationCore` reached through comtypes works across the 32/64-bit boundary and
exposes: the dock panes, the **project tree with item text as `Value`**, the MDI
tab bars, the toolbars, the **status bar message** (`SB_GETTEXTW` cannot read it —
UIA gives `就绪`, `切换为指令列表编辑器`, or the current command hint), and the
ActiveX cell editors (§9).  **Both grid documents are hosted in a `#32770`** (符号表's children are
`Afx:ToolBar…, Afx:DockPane…, #32770, VSFlexGrid8N, ATL:697A8F20`), so the window class
cannot tell them apart — the **header cells** are the discriminator (符号/地址 vs
元件名称/数据类型), which is what `symbol_grid()` / `monitor_grid()` now check.

The ladder canvas (`AfxFrameOrView90u`) exposes **no**
UIA children, so program graphics remain reachable only through the IL text and the
GDI text tap.

## 10. Offline debugging (离线调试)  [runtime, negative result]

`调试 → 离线调试` is command **33198** (string table: "离线调试进程通讯初始化失败",
"备份当前离线调试固件", "不允许同时进行离线调试").  Posted on an **H3U** project it has
no effect: no dialog, no child process, no output-pane message, and 监控 still
answers `连接状态：未连通`.  The simulator assets are H5U/Easy-specific
(`Simulator/h5u_daemon.exe`, `SimulationSkin`), and this build's 新建工程 wizard
offers no H5U family (see §7), so offline debugging could not be exercised here.

## 10b. Project file format: chunked tables in plain text  [file, partially decoded]

Every component file (`VarList.gdt`, `MAIN.mon`, `DeviceTable.dev`, `CrossTable.crs`,
`MAIN.IL`, `MAIN.LD`, …) starts with the same 0x80-byte header — `AutoShop`, version
strings, the constant `clQobtqa` — followed by a sequence of **named chunks**:

    <count:u16> <0xffff> <version:u16> <name_len:u16> <name> <payload>

Names seen: `CLVTItem` (local/temporary variables, present in every file), `CGVTItem`
(global symbols), `CElemMonItem` (monitor table).  The payloads are plain little-endian
text records, so the obfuscation is only in the header — **not** in the data.

`VarList.gdt` → `CGVTItem`, one record per symbol:

    <name_len:u8> <name> <addr_len:u8> <addr> <note_len:u8> <note> <00 00 00 00 06 80>

`CrossTable.crs` → `CCrossRefInfo`, one record per device use:

    <name_len:u8> <device> <flag:u8> <program path…> <instr_len:u8> <instruction> <line:u32> <7 bytes> <8×ff> <00> <8×ff>

The path carries no length, so it is scanned up to the last `.IL`/`.LD` before the
instruction length byte; the last record ends at EOF instead of with the trailer.
Measured on the three-program test project (8 records for 8 uses) — it is the offline
"where is this device used" view: `M0 → MAIN.IL OUT (line 5)` and `M0 → SBR_001.IL LD
(line 2)`, `X2 → INT_001.LD`, etc.

`MAIN.mon` → `CElemMonItem`, one record per monitor row:

    <data_type:u32> <display_format:u32> <value:u32> <err:u8> <name_len:u8> <name> <06 80>

with `data_type` 1 = bit device (`M`/`X`/`Y`/`T` contact) and 2 = word device
(`D`/`T` current), and `display_format` 1 (bit) / 4 (16-bit decimal).

Read them with `autoshopkit/projectfile.py` (`read_symbols`, `read_locals`,
`read_monitor`, `read_crossref`) — no GUI, no save-format guessing.  Measured on 2026-10-26 by writing
through the GUI and diffing the files (`tools/probes/gdt_layout.py`,
`tools/probes/monitor_add.py`); the two channels agree exactly
(`tools/e2e_symbols.py` step 9, `tools/e2e_monitor.py`).

**Negative result:** `ElemUseInfo.esi` does **not** change when the program changes
(0 changed bytes across four different programs), so it is not a device-usage cache —
use `crossref()` (from `CrossTable.crs`) for "where is this device used".

A save does **not** rewrite everything: with a program edit, `MAIN.IL`/`MAIN.LD`/`.hcp`
kept their old mtimes while `VarList.gdt`, `CrossTable.crs`, `Output.prg` and the
`.hcpp` backup were rewritten.  `App.save()` therefore compares every project file
before/after and reports `changed_files`, instead of trusting the `.hcp` mtime.

### Real H5U project measured (2026-10-26)

`D:\<客户目录>\<客户目录>\<客户>\<产线>\…\<H5U 工程>` (copied to the sandbox, never
touched in place) is the first *populated* project available; it also showed where the file
formats differ from H3U:

| file | H3U | H5U (this project) |
| --- | --- | --- |
| `VarList.gdt` `CGVTItem` | `<00><name_len><name><addr_len><addr><note_len><note><00 00 00 00 06 80>` | same **without the address field** (613 records: `M0/工作`, `M201/报警标志`, …) |
| `VarNameAndAddr.csv` | absent | **UTF-16 tab table**: `name \t address(0X…) \t comment \t bits` — 1412 rows, system variables included |
| `MAIN.mon` | `CElemMonItem` records | only `CLVTItem` — the quick monitor table lives elsewhere (`H530QUICKMONTABLE.qmt`) |
| `.LD` | ladder with element text | same; 6 files, **2957 element texts** (`ZRST M420 M421`, `MC_Power K1 S261 - - -`, `WBIT D2015 Y0 K4`, …) |
| `CrossTable.crs` | small | 1.4 MB, **8809 rows / 3692 devices**, attributed per program |
| IL channel | available | **no IL text for ladder-only programs** (`read_programs()` returns nothing until the program is opened as 指令列表) |

The project needs its EtherCAT slave descriptions; without them AutoShop refuses to load it
(“没有找到X5_7SEtherCAT_9对应的xml设备文件!”). Removing the EtherCAT files **from the copy**
lets it open (877 tree items), and compiling then reports 12 `未定义变量` errors for the servo
FB instances — i.e. the removal, not the project, is what breaks. Everything that does not
need the device descriptions (symbols, cross-reference, ladder text, offline audit) works on
the untouched copy.

### The IL channel exists for H5U — as a compile artifact, not an editor

H5U ladder documents have **no instruction-list view**: the document owns a single
`AfxFrameOrView90u` child, 查看→指令表 (32867) creates no `Scintilla`, and `read_programs()`
through the editor returns `{}` even after a clean compile.  But 转换/编译 rewrites
`il_log.log` next to the project with the whole program set as numbered IL:

    0000	LD M207
    0001	OR X34
    0002	AND X35
    0003	TONR K200 - S500 -
    …
    03967	FBRET 伺服

3968 steps for the real project.  The structure is `MAIN` up to a `MAINEND` marker, then each
subprogram from a lone `P` to its `SRET`, then the FB bodies up to `FBRET <fb>`.
`projectfile.read_il_log()` / `split_il_programs()` decode it, and `AutoShop.read_programs()`
falls back to it when the Scintilla channel is empty, so H5U programs *are* readable per
program: MAIN 709 (equals the instruction count stored in `Compile/MAIN.compile`), the four
subprograms 4/342/349/124, and 12 servo FB instances of 176 steps each.

`Compile/<program>.compile` additionally holds per-program compiled records
(`"SAY"` + `<u16 count>` + `<mnemonic><operand>`), plaintext for `MAIN`/`*.fb` but obfuscated
with the same shifted-letter scheme for several `SBR_*` files.

### `.hcp` — SOLVED: UTF-16LE XML behind a position-dependent transform

The container is **not** a binary structure: it is a UTF-16LE XML document encrypted with a
position-dependent, length-preserving transform.  Both the transform and the key were recovered
from `InterfaceMgr.dll` (not from the 52 MB exe):

    KEY = b"SclSoftware"        # 11 bytes, .rdata RVA 0xa5980
    j = 0
    for i in range(len(data)):
        j = (j + 1) % 11
        b = data[i]
        if i % 2 == 0: b ^= (i & 0xFF)
        data[i] = (b - KEY[j]) & 0xFF        # decrypt
        # encrypt: b = ((b + KEY[j]) & 0xFF) ^ (i & 0xFF)

| RVA (InterfaceMgr.dll, base 0x10000000) | export | role |
| --- | --- | --- |
| 0x4c810 | `?UCodeDecrypt@CUCodeCrypt@@QAEHPB_W0@Z` | read: Open→Read→`DecryptArithmetic`→write plaintext |
| 0x4caa0 | `?UCodeFileEncrypt@CUCodeCrypt@@QAEHPB_W@Z` | write: read → `EncryptArithmetic` → seek 0 → write in place |
| 0x4ce60 / 0x4ceb0 | `?EncryptArithmetic` / `?DecryptArithmetic` | the loops |
| 0x36550 / 0x365f0 | `?g_Encrypt` / `?g_Decrypt` | same transform for 8-byte field values |
| 0xa5980 | `"SclSoftware"` | key |

Runtime confirmation: Frida hooks on `base+0x4ceb0` / `base+0x4ce60` showed
`dec_arith len=18304 head=626a8d6f…` and `enc_arith len=18304 head=fffe3c00…`, and the live key
bytes read `53 63 6c 53 6f 66 74 77 61 72 65 00`.

Why earlier attempts failed: the plaintext is UTF-16LE, so **odd offsets are the high bytes and
are 0**, no XOR runs there, and the odd ciphertext byte equals the key byte — that produced the
"11-letter, 22-byte cycle" and hid the additive transform.  The 8-byte run at 0x1f of every
component file is `EncryptArithmetic(8 zero bytes) == 63 6c 51 6f 62 74 71 61 == "clQobtqa"`,
which is why that string exists in project data but in no shipped binary as a literal.

Decrypted content (`projectfile.read_hcp`, `autoshopkit hcp --project DIR`): `<Version>`,
`<ProjectDesc>`, `<DefaultEditor>`, `<GCMModal>`, `<CPUVersion>`, `<Capbility>`, `MaxFileID` /
`MaxSubID` / `MaxIntID` / `MaxMCID` / `MaxCncID`, `<HardwareFile>`, `<historycount>`,
`<projnameex>`, `<asversion>`, `<ProjVersion>`, plus one `<file id="N">` record per component
(`FileType`, `ProgType`, `Caption`, `Alias`, `FileName`, `CreateTime`, `LastModifyTime`,
`POUID`, `Encrypted`, …).

Measured: H3U empty project 18 304 B → 16 records, `GCMModal H3U`, capacity 64 000, programs
stored as **`.IL`**; H5U real project 54 926 B → 51 records, `GCMModal H5U`, capacity 200 000,
programs stored as **`.LD`**, `projnameex = <产线>折弯产线_<H5U 工程>`.  That also explains the
editor difference: the container index names the programs, and H3U's are instruction lists while
H5U's are ladder files.

The transform is invertible (`autoshopkit.hcp.encrypt`), so the kit can write a container back;
`tools/test_hcp.py` checks both directions plus that the index names files that actually exist.

Independent samples: the four `.hcpp` backups in the real project's `BackUP` folder (2024-02 to
2026-03, 32.5–45.9 KB) each hold raw `.hcp` bytes; all four decrypt to the same UTF-16LE XML
shape (`H5U`, 36/40/41/47 `<file>` records) — so the codec is not fitted to one file.

One caveat on the *live* proof: re-opening the decrypted-and-re-encrypted project in AutoShop did
not complete, but neither does the untouched copy any more — the app now greets both with
“没有找到X5_7SEtherCAT_9对应的xml设备文件!” even though the ESI is installed, and its log shows
`CM_Reenumerate_DevNode failed: 33` plus crash dumps.  The container write itself is proven
byte-identical for an unmodified XML (`decrypt` → `encrypt` reproduces the file exactly) and the
edited XML re-reads with all records intact; the open failure is an environment/device-enumeration
problem on this machine, and it appeared after the earlier successful open+compile (25026 steps)
had already been recorded.

### `.hcp` — earlier measurements

The project container is **not** plaintext like its component files, and it is not simple
XOR either.  What is established by measurement:

* 18 304 bytes; reading it as a 16-bit word stream, the bytes at **odd offsets** repeat one
  of eleven ASCII letters per position (`l o t a e c S f w r S`, period 22 bytes, ~99 % of
  rows) while the even offsets carry the varying data;
* two copies of the same project with *different programs, symbols and monitor rows* differ
  in only **11 bytes**, and all eleven sit at even offsets (e.g. `0xfe` holds ASCII `b`/`c`);
  so the container is a large fixed template plus a handful of counters — the program itself
  lives in the component files, not here;
* neither byte stream (even or odd), nor their XOR/sum/difference, decodes as UTF-8/GBK/UTF-16;
* the repeating letter pattern is **not a literal in any shipped binary** (searched 183
  exe/dll files, both ASCII and UTF-16), so it is derived at run time rather than stored.

Conclusion: decoding it needs REA work on the AutoShop reader routine, and it is **not on the
critical path** — settings are reachable through the UI (系统参数 document + UIA), and
symbols / monitor rows / cross-reference / programs are all readable from the plaintext
component files or the instruction-list channel.  Recorded here so nobody repeats the blind
cryptanalysis.

Still undecoded: `.hcp` itself, `MAIN.LD` (ladder geometry is binary, the IL text is
not stored as text there), and the `CLVTItem` payload layout.

## 11. Tooling environment

* REA 6.5.0 (Ghidra 12.1.4 provider available; Frida provider reports
  `capability_unavailable` because its native binding is not built).
* The driver therefore uses `frida` (Python, 17.24.3) directly for the in-process
  text tap, plain `ctypes` for window messages and input, and **`comtypes`**
  (1.4.16) for UI Automation.  `pywin32` happens to be installed but is not used.
* Keep one DPI awareness setting for the whole process: UIA reports physical
  rectangles, so mixing an aware client with unaware screen coordinates shifts
  every measured column by the scale factor (1.5 here).
