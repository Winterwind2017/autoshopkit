# Instruction list (IL) — the verified authoring channel

AutoShop keeps a program as instruction list text; the ladder is a view of it.
`查看 → 指令列表 (32867)` opens that text in a **Scintilla** editor, which makes
the IL the practical way for an agent to read and write programs.

`tools/il_corpus.py` compiles a corpus of snippets and writes the measured result
to [`IL-results.md`](IL-results.md) (table + every source + AutoShop's answer).
Last run: **27/27 snippets compile with `(0)错误`**.

## How to read

```python
app.activate_document("MAIN"); app.view_il()
text = app.program_il()        # SCI_SELECTALL + SCI_GETSELTEXT under the hood
```

An empty program is a list of network comments (`//网络注释`), one per network.

## How to write

`app.set_program_il(text)` = real select-all + paste, verified by reading back.
`SCI_SETTEXT` does **not** work: the buffer changes and even shows on screen, but
the document model never learns about it and the compiler keeps the old program.
`set_program_il` switches to the IL view by itself when it is not open.

Rules that were verified by compiling:

| Rule | Evidence |
| --- | --- |
| line endings **LF only** | `LD X0\r` → `错误 MAIN.IL ,【行1】: X0\r:符号未定义`; `LD X0` → `统计 - (0)错误` |
| the app reformats on paste (tabs between operator and operand) | pasted text reads back as `LD\t\t X0` |
| network comments are part of the source | `//network one` lines are preserved and count as networks |
| conversion runs immediately after the paste | the 转换 pane shows `开始转换... / <PROG>.LD / 统计 - (n)错误` |
| operands are upper-cased by the editor | typing `btn1` reads back as `BTN1` |
| a clean project copy matters | errors from other programs stay in the project error count until fixed |

## Verified instruction forms (21/21)

| Name | Source | Steps |
| --- | --- | --- |
| contact + coil | `LD X0` / `OUT Y0` | 31 |
| series | `LD X0` / `AND X1` / `OUT Y0` | 32 |
| parallel | `LD X0` / `OR X1` / `OUT Y0` | 32 |
| timer | `LD X0` / `OUT T0 K10` | 33 |
| counter | `LD X0` / `OUT C0 K5` | 33 |
| move | `LD X0` / `MOV K1 D0` | 35 |
| double move | `LD X0` / `DMOV K10 D0` | 39 |
| set / reset | `LD X0` / `SET Y0` / `LD X1` / `RST Y0` | 33 |
| compare contact | `LD> D0 K5` / `OUT Y1` | 35 |
| stack | `LD X0` / `MPS` / `AND X1` / `OUT Y0` / `MRD` / `AND X2` / `OUT Y1` / `MPP` / `OUT Y2` | 38 |
| pulse | `LD X0` / `PLS M0` | 32 |
| zone reset | `LD X0` / `ZRST M0 M10` | 35 |
| master control | `LD X0` / `MC N0 M100` / `LD X1` / `OUT Y0` / `MCR N0` | 37 |
| for / next | `LD X0` / `FOR K5` / `INC D0` / `NEXT` | 37 |
| jump | `LD X0` / `CJ P0` … / `LBL P0` | 36 |
| label only | `LD X0` / `OUT Y0` / `LBL P1` | 32 |
| jump to end | `LD X0` / `CJEND` | 33 |
| call a subprogram | `LD X0` / `CALL SBR_001` / `LD X1` / `OUT Y0` | 35 |
| sequential (STL) | `STL S0` / `LD X0` / `SET S1` / `RET` | 34 |
| two networks | `LD X0` / `OUT Y0` / `LD X1` / `OUT Y1` | 33 |
| networks + comments | `//net one` / `LD X0` / `OUT Y0` / `//net two` / `LD X1` / `OUT Y1` | 33 |

A realistic multi-network program (timer + `MOV`/`DMOV` + `CJ`/`LBL` + `MPS`/`MPP`
+ `FOR`/`NEXT`, see `autoshopkit/programs.py: KITCHEN_SINK`) compiles to
`统计 - (0)错误,(69)步占用` — that program is part of the acceptance suite.

## Syntax rules that cost attempts

| Attempt | AutoShop's answer | What it means |
| --- | --- | --- |
| `P0` on its own line | `P0:输入了错误的指令` | a jump target is not a bare line |
| `P0:` | `P0::输入了错误的指令` | no colon suffix either |
| `LBL P0` | compiles | **`LBL` is the label instruction** (manual: CJ 条件跳转 + LBL 标号指令) |
| `FOR K1 K5` | `FOR:操作数数目错误` | this family's `FOR` takes **one** operand (`FOR K5`) |
| `CALL P1` | `P1:子程序未定义` | `CALL` takes a **subprogram name** (`CALL SBR_001`), not a pointer |
| `CMP K1 K5 D0` | `错误 … CMP…` | `CMP` writes its result to a **bit** device: `CMP K1 K5 M10` |

## Operand roles (`autoshopkit/ilparse.py`)

The same corpus grounds the operand-role table used by `project_check`': for every
verified instruction the parser knows which operand is read and which is written
(`MOV src dst`, `ADD a b dst`, `CMP a b result`, `XCH a b` = both, `INC d` = read+write,
`OUT T0 K10` = coil written + preset read, contacts read).  Instructions outside the
table yield `?` and are excluded from inference, so a device is never called a dead write
on a guess.

`python tools/test_ilparse.py` checks the table without starting AutoShop (17 assertions,
<1 s): one instruction per family from `programs.COVERAGE_PROGRAM`, the specific role of
each family, and that the findings land in `W150`/`I120` — while physical I/O and constants
(`X`, `Y`, `K`) are never reported.

**Note:** the sample project used for these tests has *empty* programs (its ladder shows 15
networks with only `网络注释`, and the IL view holds no instruction).  So the corpus is
authored by the kit itself; measuring coverage on real customer code is what
`tools/probes/il_coverage.py` is for — run it on a populated project to see which
instructions still yield `?`.

## Not yet covered

* symbolic operands inside IL (the 符号表 is writable now — see `docs/RECON.md` §9 —
  but only device operands have been exercised in the corpus);
* floating-point / motion instructions (`CAMRD`, `CCW`, `DRVA`, …) from the manual's
  catalogue: each needs a device set the project actually has;
* ST documents (`.st`): `STCompiler.dll` / `StLang.exe` exist, but ST is a separate
  document type and is not reachable through this IL view.

Add a snippet to `tools/il_corpus.py` and re-run it to extend the table; the tool
writes → converts → compiles → reports, so a regression is visible immediately.
