# Open questions

* **H5U 工程被 EtherCAT 设备描述锁住（2026-10-26 新发现）**：`EtherCat.dat` 里配了 12 个从站
  （设备类型 `X5_7SEtherCAT`，实例名 `X5_7SEtherCAT_1…_11`）。用户提供的 `X5_7S_V001.xml`
  已经是同一设备（`<Type>X5_7SEtherCAT</Type>`、vendor `#x00000766`），但 AutoShop 仍弹
  “没有找到X5_7SEtherCAT_9对应的xml设备文件!”，而且这个模态框会在**每次发工程级命令**
  （编译/导入/导出）时重新弹出 → 这些命令当前不可用。
  已试无效：`xml\` 目录下按 `<名字>.xml`、`<类型>_<版本>.xml` 命名（共 13 个猜测文件，已清理）。
  下一步应走 GUI 的“设备库/ESI 导入”，或拿到厂家原始的 12 个 XML 包；未验证。


* ~~**`.hcp` decryption**~~ — **solved 2026-10-26**: see `RECON.md`; the container is UTF-16LE
  XML behind `b = (b - "SclSoftware"[j]) & 0xff` with a per-offset XOR, recovered from
  `InterfaceMgr.dll`.  Remaining minor unknown: the exact `AutoShop.exe` call-site RVA for
  project open/save (only seen through the import-thunk table), and whether every save path
  uses the in-place encrypt.  Superseded notes kept below for the record.
* **`.hcp` decryption was open** after a second attempt.  New evidence: the mask is
  position-only (three different projects with different content share the identical 18-byte
  header ciphertext), the odd-offset bytes are the 11-letter cycle, the file varies by only
  ~11 bytes between projects (so it holds settings, not programs), Frida can dump the
  decrypted image from memory (`recon\hcp_plain_memory.bin`), and the `.hcpp` backup itself
  stores the still-obfuscated bytes.  Attempts that did **not** work: byte/word periodicity
  of the mask, XOR of the memory image with the file (image is a parsed structure, not the
  file image), zlib/bz2/lzma, single-byte XOR, and static xref hunting for the loader (rizin
  is unavailable on this Windows host; targeted capstone walks around the captured
  `.hcpp`-write stack frames did not land in a transform loop).  Closing it needs a real
  Ghidra session on the 52.7 MB executable (29 MB of `.text`) — a multi-hour job that was not
  started here.
* **No populated AutoShop project existed here originally.**  `D:\<客户目录>` (and every fixed
  drive) holds exactly one `.hcp`, and its programs are empty (15 networks with only
  网络注释).  A real one was found later under
  `D:\<客户目录>\<客户目录>\<客户>\<产线>\…\<H5U 工程>` and is now the subject of
  `tools/test_offline_audit.py` (613 symbols, 8809 cross-reference rows, 2957 ladder texts).
  `W150`/`I120` still cannot run on it without compiling, and H5U ladder programs have no IL
  text, so the per-instruction read/write pairing remains H3U-only.
* **`.hcp` on-disk transform**: the plaintext is readable in memory and has the normal
  component layout, but the file-level mask is only characterised (11 constant ASCII bytes
  at odd offsets per 22-byte period; even bytes vary per word).  Closing it needs the reader
  routine from the 52.7 MB executable — Ghidra analysis of that image was not attempted here.
* **`.LD` geometry**: element text and network comments are recovered
  (`projectfile.read_ld_text`), but the type byte, the node blob and the coordinate pair are
  still unnamed. / next attacks

Each item states the question, what is already known, and the first concrete
action.  Ordered by value ÷ cost.

## 1. Symbolic (variable) programs — is the 变量 editor mode usable offline?

*Resolved:* the earlier `X0: 符号未定义` was **our own** `\r` inside the operand
(`LD X0\r`), not a project mode.  With LF line endings, devices (`X0`, `Y0`,
`T0`, `D0`, `K10`) compile cleanly in this project — see `docs/IL.md`.

*Still open:* whether a project created with the 变量/符号 editor mode needs
declarations in 符号表, and how to fill that VSFlexGrid — see §6 for the current
state (the text reaches the cell editor but cannot be committed yet).

*Next:* create such a project through `新建工程` (编辑器 combo) and retry the IL
corpus there.

## 2. File obfuscation (`.hcp`, `*.LD`, `Output.prg`, some `*.compile`)

*Known:* every project file begins with a 255-byte header: `"AutoShop"`,
version words, then `clQobtqa` at offset 0x1F, then zeros.  `MAIN.compile` is
plaintext; `SBR_001.compile`, `.hcp` and `Output.prg` are obfuscated with the
same scheme (11-ish byte period, high bytes limited to ASCII letters, looks like
a byte-wise transform rather than compression — no zlib signature).

*Next (static):* `open_binary AutoShop.exe` in Ghidra, `search_strings "clQobtqa"`,
xrefs → the encrypt/decrypt routine; corroborate with `EnDecrypt.dll`,
`EncryptionToolDll.dll`, `KSDecode.dll`, `crc32.dll`. Also `CHcppFile::DecompressProj`
/ `GenFileFromData` (symbol names are present in the exe).

*Value:* offline project generation without the GUI.  Not required for the
current agent workflow (the IL channel already writes programs).

## 3. IL dialect coverage

*Known:* `LD <dev>` / `OUT <dev>` compile; the app reformats with tabs; `\r` in an
operand breaks it (`X0\r: 符号未定义`); network comments are `//网络注释` lines and
the IL text is the whole program (comments included).

*Next:* build `tests/il/*.il` covering contact/coil/timer/counter/`MOV`/`CMP`/
`SET`/`RST`/`MPS`-`MRD`-`MPP`, compile each, record the diagnostics.  This turns
the IL channel into a documented authoring language.

## 4. New-project wizard — *solved*, with one residual

*Solved:* `AutoShop.create_project(name, dest)` creates through `32858`, moves the
folder and reopens it (`tools/e2e_create.py` 6/6).  Findings:

* the `工程名` / `保存路径` edits **reject `WM_SETTEXT` (returns 0) and even real
  clicks**; they do accept `WM_CHAR`, which is how text gets in (`type_chars`);
* the app **owns 保存路径**: it recomputes `<Documents>\<name>\` and discards a
  typed path, so the project always lands in Documents and must be moved;
* `确定` with an existing folder asks `文件夹已存在，是否覆盖原文件夹？` (是/否);
* the 编辑器 / 系列与型号 combos are owner-draw (no strings), but `CB_SETCURSEL`
  by index works and the created project's tree root confirms the choice
  (`<name> [H3U]`).

*Residual:* drive the `…` (Button 1053) folder picker to land the project directly
in a chosen directory, avoiding the create-then-move step.

## 5. Download / monitor without hardware

*Solved (offline):* `生成下载文件` (33186) → 下载选项 → 生成文件 (1436) → the
Windows shell 另存为 dialog → `生成文件成功！` → a `*.updown.down` artefact.
`AutoShop.generate_download_file(path)` automates the whole chain (e2e step 10,
1294-byte file).  Two quirks are documented in `docs/RECON.md` §8: the shell
dialog accepts **only genuine typing in its filename field** (full path works, so
the file lands exactly where asked), and a leftover 下载选项 dialog makes the next
run fail — `_dismiss_all()` clears it.

*Still open:* a live 监控 / 写入 / 运行 loop.  `离线调试` (33198, the built-in
simulator mode) does nothing on an H3U project, and this build's 新建工程 wizard
offers no H5U family, so the H5U offline debugger (`Simulator/h5u_daemon.exe`)
could not be reached.  On a machine with a real PLC, or an AutoShop build that
offers H5U, the next steps are: create an H5U project, `33198`, then `32893`
(监控) and read the monitor table through the same text tap.

## 6. 符号表 — *solved*, one residual

Solved through UI Automation: the in-cell editor (`ATL:697A8F20`) supports
`ValuePattern.SetValue`, column x / row pitch come from UIA header rectangles, and a
row registers once 符号 **and** 地址 are set.  Proven by `tools/e2e_symbols.py`
(6/6): the written symbol compiles, an unknown symbol still fails.  Details and the
exact recipe are in `docs/RECON.md` §9.

Read-back is solved too: `read_symbol(row)` clicks a cell, presses **F2** (edit
mode without changing content) and reads the editor's `ValuePattern`.

Enumeration exists (`read_symbols()`) but costs ≈6 s per row.  A faster route is
already visible: after 保存工程, **`VarList.gdt` holds the names/addresses/notes in
plain UTF-8** (288 bytes for one symbol, 330 for three).  *Next:* map its record
framing (length bytes + padding) so a whole table can be read from disk in one go.

## 6b. Reading custom-drawn surfaces (ladder canvas)

*Known:* the GDI text tap (`autoshopkit/hooks.py`) captures every string the app
paints, with the target window handle; the output pane is fully readable that way.

*Next:* filter the tap by the ladder view's hwnd to extract rung labels and device
names (rung structure still needs geometry/OCR).

## 7. Smaller annoyances worth fixing

* `statusbar()` — `SB_GETTEXTW`/`SB_GETPARTS` return 0 cross-process; the text is
  only visible in screenshots.  Try MSAA (`AccessibleObjectFromWindow`) or the
  text tap on the status bar hwnd.
* `close()` — when several modal prompts are stacked it may need more than the
  20 s budget; it now falls back to `TerminateProcess`.
* `tree_open()` — the click row is computed from a fixed 20 px pitch; if the user
  changes tree font size, re-derive the pitch (screenshot or `TVM_GETITEMHEIGHT`
  once a working message is found).
* `view_il` on a *dirty* LD document (one SBR_001 case) did not create the IL
  view; writing/undoing the pending edit first may be required.  Reproduce and
  document.
