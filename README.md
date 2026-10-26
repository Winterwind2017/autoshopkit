# autoshopkit

汇川 **AutoShop V4.11** 自动化内核：**工程文件格式解码 + UI 自动化通道 + 可复核的门禁**。
宿主侧负责"读工程 / 改程序 / 编译 / 报结论"，所有碰窗口的代码都在 `autoshopkit` 包里，
不依赖插件、不改编译器，只用 Win32 消息、UIA 与 Frida 三样东西。

> 与 [nxkit](https://github.com/Winterwind2017/nxkit)、[autocad-agent-kit](https://github.com/Winterwind2017/autocad-agent-kit)
> 同构：**能力表 + 判据 + 证据**，不写"没验证过"的能力。用法与坑见独立技能仓库
> [ww-autoshop-automation](https://github.com/Winterwind2017/ww-autoshop-automation)。

## 为什么需要一个内核

AutoShop 是 MFC MDI 程序，**没有 COM、没有 DDE、没有脚本接口**，菜单是 `CMFCMenuBar`
（`GetMenu` 返回 NULL）。要让它被 agent 驱动，必须自己打通三层：

1. **文件层**：工程 = `AutoShop` 头 + 具名 chunk 的明文部件（`.gdt`/`.mon`/`.crs`/`.LD`）
   加一个加密容器（`.hcp`）。读文件比读界面稳，也更快。
2. **界面层**：命令只能靠 `WM_COMMAND` + 数字 ID；树是 40 字节手打包的 `TVITEMW`；
   程序编辑器是 `Scintilla`（**只有 H3U 有**，H5U 是自绘梯形图画布）。
3. **产物层**：编译把诊断写进自绘输出窗（hook `DrawTextW` 才读得到）；H5U 还会把整工程 IL
   写进 `il_log.log` —— 这是 H5U 唯一可读的"程序文本"。

## 装

```bash
pip install -e .                 # 只读文件的能力，不需要 UI 依赖
pip install -e ".[ui]"           # 需要驱动 AutoShop 时（comtypes / pywin32 / frida）
autoshopkit status               # 是否已连上运行中的 AutoShop
autoshopkit doctor               # 连上 + 自检：树/文档/编辑器/输出窗/Frida/版本
```

要求：本机装 AutoShop（默认 `D:\Inovance Control\AutoShop\AutoShop.exe`，可用
`AUTOSHOPKIT_EXE` 覆盖）；UI 侧要求进程内外 DPI awareness 一致。

## 两条通道

**离线（不启动 AutoShop）**

```bash
autoshopkit hcp --project <工程目录>       # .hcp 容器 → UTF-16LE XML 工程索引（系列/容量/组件表）
autoshopkit illog --project <工程目录>     # H5U：编译产物 il_log.log → 按程序拆分的 IL
autoshopkit check --offline <工程目录>     # 符号/监控/交叉引用/梯形图文本的静态体检
```

**在线（驱动 AutoShop）**

```bash
autoshopkit start <工程.hcp>     # 启动并等树填充
autoshopkit tree                 # 工程树（会自动避开器件目录那棵树）
autoshopkit open 程序块 MAIN      # 打开程序：展开父节点 → 单击 → 核对 TVGN_CARET → 双击
autoshopkit il                   # 读当前程序的指令表
autoshopkit apply -f prog.il     # 写入：真全选 + 剪贴板粘贴（不是 SCI_SETTEXT）
autoshopkit compile              # 转换/编译并解析诊断
autoshopkit check                # 体检（双线圈/死写入/未用符号/容量…）
autoshopkit save                 # 保存，并报告被重写的部件
```

Python 侧同一套东西：

```python
from autoshopkit import AutoShop

app = AutoShop.launch(r"D:\work\demo\demo.hcp")
print(app.project_tree_texts())                    # 工程树
app.open_program("MAIN")                           # 打开（含标题+自有编辑器双判）
print(app.program_il(strict=True))                 # 当前程序
app.apply_program("LD X0\nOUT Y0\n", save=True)    # 写入并保存
ok, lines = app.compile()
print(app.project_check()["counts"])               # 体检
```

## 门禁（本仓库可复现的部分）

```bash
python -m pytest tests -q          # 6 个纯逻辑套件 / 80 条断言 / 约 0.4 s
python tests/e2e.py                # 需要 AutoShop：14 步真机
python tests/e2e_programs.py       # 需要 AutoShop：9 步（三个程序读写）
```

| 套件 | 覆盖 |
| --- | --- |
| `test_ilparse.py` | IL 解析 / 操作数角色 / 合并（W150、I120 的底座） |
| `test_projectfile.py` | `.LD` 元素文本、`.hcpp` 备份、交叉引用与符号表 |
| `test_hcp.py` | `.hcp` 容器加解密（H3U + H5U 双向 + 4 个备份样本） |
| `test_h5u_il.py` | `il_log.log` 拆分（MAIN 长度等于 `Compile/*.compile` 的指令数） |
| `test_ladder.py` | 梯形图元件记录（图链接 + kind + 文本；文件里没有坐标表） |
| `test_offline_audit.py` | 离线体检在真实工程上的读数 |

真机门禁：`e2e 14/14`、`e2e_create 6/6`、`e2e_apply 7/7`、`e2e_symbols 9/9`、
`e2e_monitor 6/6`、`e2e_programs 9/9`、`e2e_project 9/9`、`e2e_check 11/11`、`e2e_cli 17/17`。

> 两类门禁吃不同数据：真机跑在 `sandbox/` 的自建工程上；离线套件在缺数据时打印 `SKIP`
> 并返回 0，所以**干净 clone 上 `pytest` 是绿的**。

## 目录

```
src/autoshopkit/   app(UI 通道) / projectfile(格式) / hcp(容器) / ilparse / check / cli
tests/             test_*.py 纯逻辑套件 + e2e_*.py 真机脚本
tools/             一次性脚本与探针（probes/ 是逆向现场，不进发布面）
docs/              RECON / HCP-FORMAT / LADDER / COMMANDS / IL / CHECK / VERIFY / UNSUPPORTED
local/ recon/ sandbox/   仅本地：客户工程、逆向 dump、沙箱副本（.gitignore 挡住）
```

## 不做的事

- **不做**在线监控读数与真正的 PLC 下载：前者要真机，后者要连机授权（见 `docs/UNSUPPORTED.md`）。
- **不假装**能写 H5U 梯形图：H5U 文档没有指令表编辑器，梯形图是自绘画布；写入通道只对 H3U 成立。
- **不发布**没跑过的能力：`docs/CAPABILITIES.md` 每条都标了证据来源。

MIT © Winterwind2017
