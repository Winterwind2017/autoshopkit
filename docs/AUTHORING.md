# The authoring loop: `apply_program` and `doctor`

Two calls cover what an agent normally needs; everything below them is still
available when something goes wrong.

## `doctor()` — is this environment usable?

```python
app = AutoShop.launch(r"D:\work\demo.hcp")
app.doctor()
# {'frame': '0x6e20bd6', 'title': '…', 'project': 'D:\\work\\demo',
#  'project_open': True, 'has_tree': True, 'has_document': True,
#  'statusbar': '就绪', 'frida': '17.24.3', 'comtypes': '1.4.16',
#  'uia': True, 'il_editor': True, 'output_pane': True, 'dialogs_open': []}
```

It checks the process/window binding, whether a project is open, the tree, the
open documents, the status bar (UIA), the optional Python dependencies
(`frida` for the output pane, `comtypes` for UIA), whether the IL editor and the
output pane are reachable, and lists any dialog that is still open (a leftover
dialog silently swallows the next command).  CLI: `python -m autoshopkit doctor`.

## `apply_program(text, document="MAIN", save=False)` — write → convert → compile

```python
from autoshopkit.programs import KITCHEN_SINK
result = app.apply_program(KITCHEN_SINK, save=True)
result["compiles"]      # True
result["summary"]       # {'errors': 0, 'steps': 69, 'capacity': 63500, 'line': '统计 - …'}
result["errors"]        # []
result["readback_ok"]   # True  – the pasted text came back from the editor
```

On a broken program the same call reports *where* AutoShop objected:

```python
bad = app.apply_program("LD X0\nNOP K1 K2\nOUT Y0\n")
bad["compiles"]   # False
bad["errors"]     # [{'level': '错误', 'source': 'MAIN.IL', 'line': 2, 'column': None,
                  #   'message': 'NOP:操作数数目错误',
                  #   'raw': '错误  MAIN.IL ,【行2】: NOP:操作数数目错误'}]
```

CLI: `python -m autoshopkit apply prog.il --doc MAIN --save`.

The result also carries `converted` — the same parse applied to the 转换 pane right
after the paste — so a conversion failure is distinguishable from a compile failure.

## `diagnostics.parse()` — the line grammar

`autoshopkit/diagnostics.py` turns those lines into dicts:

| line shape | parsed |
| --- | --- |
| `错误  MAIN.IL ,【行1】: X0:符号未定义` | level, source, line, message |
| `错误  SBR_001.LD ,【行2，列2】: M0:开路` | + column |
| `警告  INT_001.LD, …` | goes to `warnings` |
| `统计 - (0)错误,(31)步占用/(63500)总容量` | `summary.errors/steps/capacity` |
| `注释-(0)步占用, … -(151)步占用/(500)设置容量` | `summary.comment_steps/comment_capacity` |

Unknown lines are preserved verbatim in `other`, so nothing is silently dropped.

## Acceptance

`python tools/e2e_apply.py` → 7/7: doctor, apply (write/convert/compile), read-back,
structured summary, a located error on a broken program, recovery, and the saved
project on disk.
