# Project health check (`project_check`)

```python
report = app.project_check()          # compiles first, then audits
report["compiles"]                    # True / False
report["counts"]                      # {'errors': 0, 'warnings': 7, 'infos': 2, 'codes': [...]}
for f in report["findings"]:
    print(f["level"], f["code"], f["message"])
```

Every finding is derived from data the kit can verify — nothing is inferred:

| source | used for |
| --- | --- |
| compile pane (全部编译) | errors, warnings, capacity counters |
| `CrossTable.crs` (`crossref()`) | which device is used where, by which instruction |
| `VarList.gdt` (`symbols()`) | declared symbols |
| `MAIN.mon` (`monitor_table()`) | monitor rows |
| the program texts (`read_programs()`) | empty programs, `CALL` targets |

## Finding codes

| code | level | meaning |
| --- | --- | --- |
| `E100-compile` | error | a compile error, with `source` and `line` |
| `W100-warning` | warning | any other compiler warning, passed through verbatim |
| `W101-double-coil` | warning | `双线圈输出` — the same output driven in more than one place |
| `W102-interrupt-number` | warning | interrupt subroutine without an interrupt number |
| `W110-empty-program` | warning | a program document that holds only comments |
| `W120-uncalled-subprogram` | warning | an `SBR*` program that no program `CALL`s |
| `W130-unused-symbol` | warning | a symbol declared in 符号表 with no cross-reference entry |
| `W140-monitor-not-in-program` | warning | a 元件监控表 device that appears in no program |
| `I100-capacity` | info | `步占用 / 总容量` with a percentage |
| `I101-network-comments` | info | network/comment capacity |
| `W150-dead-write` | warning | an internal device that is **only ever written** (located by program and line) |
| `I110-write-only-device` | info | devices that only appear as `OUT`/`SET`/`RST`/`PLS`/`PLF` (cross-reference view) |
| `I120-read-only-device` | info | an internal device that is only ever read (may be written by an HMI) |

`W150` comes from a different source than `I110`: `autoshopkit/ilparse.py` parses the IL
text and knows **which operand of an instruction is read or written** (`MOV src dst`, `ADD
a b dst`, `INC d` = read+write, contacts = read, …).  Instructions outside that table give
`?` and are excluded, so a device is only called a dead write when *every* reference to it
is a definite write.  `I110` stays informational because the cross-reference records only
the instruction name, not the operand position.

`X`/`Y` are physical I/O and are never reported by `W150`/`I120`; `K`/`H`/numeric operands
are constants and are skipped.

## Why `W120` only covers `SBR*`

Interrupt programs (`INT*`) are entered by the interrupt controller, so "no `CALL`" is
**not** a defect there — flagging them was a false positive observed on a clean H3U
project, and the check now skips them.

## Coverage of the role table

`W150`/`I120` are only as good as `ilparse`'s table.  `tools/test_ilparse.py` asserts that
every operand in `programs.COVERAGE_PROGRAM` (one instruction per family) is classified
except label operands (47 operands, 3 label ones), so a newly added instruction family
cannot silently degrade the analysis.  For a real project, `tools/probes/il_coverage.py`
prints the share of `?` operands and the instructions that still need a role.

## Offline audit (no AutoShop at all)

`check --offline <project dir>` / `check.offline_findings(dir)` audits a saved project from
its plaintext tables only: `VarList.gdt` + `VarNameAndAddr.csv` (symbols), `MAIN.mon`
(monitor rows), `CrossTable.crs` (device usage) and the `.LD` texts (network comments and
element text).  Codes it can emit: `W130-unused-symbol`, `W140-monitor-not-in-program`,
`I100-capacity` (cross-reference summary) and `I130-ladder-read` (how much ladder text was
readable).  Compile diagnostics and the per-instruction read/write pairing need the app and
are therefore **not** claimed offline.

Measured on the real H5U project: 613 symbols, 1412 variable rows, 8809 cross-reference
rows, 2957 ladder element texts, `W130` naming 6 entities that no ladder program references
(`D3067/D3066/D3065` = PLC 年月日 write-only, `D3`, `D1010`, `D212`) — plausible, since those
are HMI-facing.

## Validation on a realistic program

The only project on this machine (`D:\<客户目录>\<H3U 工程>`) turned out to be **empty**, so
a realistic 15-network machine sequence was authored with the kit and used as the test
subject: `programs.MACHINE_PROGRAM` (start/stop latch, feed cylinder, clamp, press with a
dwell timer, eject, cycle counter, throughput compare, alarm reset call, stop-clear).
It compiles clean (`89 步`), produces 40 cross-reference rows, and the check reports
`W150-dead-write` for exactly the three devices that are genuinely never read
(`M12` alarm coil, `M13` compare result, `T2` cycle timer) while every used device stays
quiet.  That is the sanity evidence for the criteria; a real customer project would still be
the better subject (see `docs/OPEN-QUESTIONS.md`).

## Acceptance

`python tools/e2e_check.py` → 9/9:

1. a clean project raises none of the planted warning codes (`W101`, `W110`, `W130`, `W140`);
2. the clean project compiles inside the check;
3. capacity is reported;
4. after planting defects — double coil, an empty `SBR_001`, a declared-but-unused symbol,
   a monitor row for an unused device — each code fires;
5. `I110` lists the write-only devices;
6. the counts add up.

The test asserts **both** directions (presence and absence), so a check that fires on
everything would fail it.
