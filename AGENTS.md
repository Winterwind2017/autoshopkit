# AGENTS.md — 在这个仓库里干活的第一页

## 1. 只发布跑过的能力

`docs/CAPABILITIES.md` 是唯一事实来源，每条能力都要带证据（哪个门禁、几个例子）。
没打通或条件不具备的，写进 `docs/UNSUPPORTED.md`，**不要偷偷标成能用**。
"调用返回了" ≠ "生效了"：AutoShop 里几乎每个 API 都会假成功（见 §4）。

## 2. 判据用读数，不用返回值

写程序类判据一律走**回读**：`program_il(strict=True)` 读回文本、`compile()` 数错误、
`project_check()` 数 findings、`crossref()` 数引用行、`hcp.read_project()` 读工程索引。
返回值只用来**发现异常**，不用来宣告成功。

## 3. 两条通道不要混

- **文件通道**（`projectfile` / `hcp`）：不启动 AutoShop，稳定、可重复，优先。
- **UI 通道**（`AutoShop`）：只在"必须改程序 / 必须编译"时用。
  UI 通道的状态全部来自窗口标题、树、`Scintilla`、输出窗——**不要缓存假设**。

## 4. 踩过的坑（每条都验证过）

- 命令只能走 `WM_COMMAND` + ID，`GetMenu` 是 NULL（`CMFCMenuBar`）。
- 树的 `TVITEMW` 是 40 字节手打包；`TVM_GETITEMRECT` 必须传**远程** RECT；
  折叠的子行返回的是邻居的矩形（先 `TVM_EXPAND` 父节点）。
- **双击文件夹行只是展开**，不是打开：`open_tree_child` 是"展开父 → 单击 → 核对
  `TVGN_CARET` → 双击"，成功判据是出现新文档。
- H5U 的工程树是 **cid=2**（cid=1 是器件目录，877 项），`tree()` 按根文本选。
- 写程序必须"真全选 + 剪贴板粘贴"：`SCI_SETTEXT` 只改缓冲区，切文档/保存就丢。
- 输出窗是自绘 `ListBox`，文本要靠 Frida hook `DrawTextW`；`LB_GETTEXT` 返回 NUL。
- 网格（符号表/监控表）的单元格编辑器类名是 `ATL:<hash>`，**hash 因控件而异**；
  comtypes 找不到时返回**真值 NULL 指针**，必须查 `.value`。
- `.hcp` 打开期间会被独占锁；读之前先 `stop`。
- 两个测试套件不能并行跑（抢同一个 AutoShop 实例，会报 COM 事件无订户）。
- `project_path` / `project_name` 是 **property**，不是方法。

## 5. 常用命令

```bash
python -m pytest tests -q           # 纯逻辑 80 条
python tests/e2e.py                 # 真机 14 步
python tests/e2e_check.py           # 体检 11 步
autoshopkit doctor                  # 现场自检
```

## 6. 提交前

```bash
python -m pytest tests -q && python tools/selfcheck.py
```

`tools/selfcheck.py` 检查：包能 import、CLI 有 25 个 verb、`docs/CAPABILITIES.md` 里的
能力名都能在代码里找到、`docs/` 不出现客户工程路径。
