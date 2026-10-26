# 编辑器矩阵：指令表 / 梯形图 / ST 谁有、怎么获得

AutoShop 里"程序"有三种承载方式，**编辑器由程序的存储形态决定**，不是由菜单决定。
这份文档只写实测到的，附命令 ID 与判据。

## 1. 三种承载

| 程序存储 | 出现在 | 编辑器 | 判据 |
| --- | --- | --- | --- |
| `.IL`（指令表文本） | H3U 系列工程（`.hcp` 索引里 `<FileName>MAIN.IL</FileName>`） | 打开即有一个 `Scintilla`；`32883/32884` 在「指令列表 ⇄ 梯形图」之间切 | 打开程序后 `len(app.find("Scintilla")) == 1` |
| `.LD`（梯形图图结构） | H5U 系列工程（`<FileName>MAIN.LD</FileName>`） | 只有一个自绘 `AfxFrameOrView90u`；**发 32883 不产生任何编辑器、不产生新文档** | 发 32883 后 `Scintilla` 仍为 0、`documents()` 不变 |
| 编译产物 | 每次转换/编译后 | 只读：项目目录下 `il_log.log` 与 `Compile\*.compile` | `projectfile.read_il_log()` 非空 |

程序语言在 V4.11 里只有两种，资源表里是相邻的两条字符串（`ChsRes.dll` / `AutoShop.exe` 均能查到）：

```
结构化文本(LiteST)      ← 文本程序
梯形图(LD)              ← 图程序
```

**没有"指令表(IL)"这一项**。`指令列表` 只作为"视图/编辑器切换"的名字存在（14 处），
所以：**IL 视图 = 给"以 IL 存储的程序"看的视图**，不是一个可以选择写入的程序语言。

## 2. 命令 ID（实测，别再猜）

| 命令 | ID | 说明 |
| --- | --- | --- |
| 切换为指令列表编辑器 | **32883** | H3U 上有效；H5U 上无效果 |
| 切换为梯形图编辑器 | **32884** | H3U 上把 IL 文档切回梯形图 |
| 切换为步进状态图编辑器 | **32885** | SFC |
| 新建工程 | 32858 | 另见 `new_project` 的坑（路径由程序决定） |

> **踩过的坑**：早期把 `32867/32868/32869` 当成"查看→指令表/梯形图/SFC"，实际它们是
> SFC 的「添加并行分支 / 添加并行汇合 / 添加一个梯形图块」。用它做"切到指令表"会静默无效，
> 在 SFC 文档上还会真的插入一个分支。`tools/selfcheck.py` 现在会拿本地命令目录核对这三个 ID。

## 3. 那么"怎样才能获得指令表编辑器"

1. **用 H3U 系列**（或任何程序以 `.IL` 存储的机型）：打开程序就有，`32883/32884` 切换。
2. **在 H5U 工程里拿不到**。已实测：EtherCAT 阻塞排除后、正确 ID 32883，
   `Scintilla` 仍为 0、无新文档、`program_il()` 为空。原因是 H5U 程序存 `.LD`，
   没有"IL 文档"这种东西。
3. **在 H5U 上想要"文本编辑器"**，只有 `结构化文本(LiteST)` 一条路：新建一个 LiteST 程序块
   （程序语言列表里唯一带文本编辑器的），它的编辑器是 `Scintilla`，可读可写可编译。
   *状态：未验证*（需要在 H5U 工程里新增程序块；现成的梯形图程序不能直接变成 LiteST，
   只能新建后重写逻辑或调用原程序块）。想验证时用 `sandbox/` 里的副本，别碰客户工程。

## 4. 没有编辑器时怎么读 H5U 的 IL

```bash
autoshopkit illog --project <工程目录> --paths      # 全部程序
autoshopkit illog --project <工程目录> --program MAIN
```

```python
from autoshopkit import projectfile
log = projectfile.read_il_log(project_dir)
programs = projectfile.split_il_programs(project_dir, log)
```

判据：`len(programs["MAIN"])` 等于 `Compile\MAIN.compile` 里记录的指令数。
读到的 IL 与编辑器里看到的 H3U 指令表**同构**（`LD/AND/OR/OUT/SET/RST/...`），
只是 H5U 这份是编译产物，不能反写回程序。

## 5. 写入通道对照

| 目标 | H3U | H5U |
| --- | --- | --- |
| 改程序 | ✅ `apply_program()`（真全选 + 粘贴，回读校验） | ❌（除非走 LiteST 程序块，未验证） |
| 改符号表 | ✅ 网格 | ✅ 网格 |
| 改监控表 | ✅ 网格 | ✅ 网格 |
| 读程序文本 | ✅ Scintilla | ✅ `il_log.log`（只读） |
| 编译 + 诊断 | ✅ | ✅（需要工程引用的 ESI 齐全，否则每次命令弹模态框） |
