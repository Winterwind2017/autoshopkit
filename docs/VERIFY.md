# 复现（干净 clone）

本文件是"换个机器也能跑出同样数字"的口径。两条线：**离线**（不需要 AutoShop）和
**真机**（需要 AutoShop 与本机授权）。

## 0. 装

```bash
git clone <repo>
cd autoshopkit
pip install -e ".[dev]"          # 只跑离线也装 dev 就够
```

## 1. 离线门禁（干净 clone 必绿）

```bash
python -m pytest tests -q -s
```

期望（2026-10-26，Python 3.12）：

```
17/17 passed                 # test_ilparse
11/11 passed (0 skipped)     # test_projectfile   ← 缺数据时会 SKIP
17/17 passed                 # test_hcp           ← 缺数据时会 SKIP
10/10 passed                 # test_h5u_il        ← 缺数据时会 SKIP
15/15 passed                 # test_ladder        ← 缺数据时会 SKIP
10/10 passed                 # test_offline_audit ← 缺数据时会 SKIP
6 passed in 0.36s
```

`test_projectfile` / `test_hcp` / `test_h5u_il` / `test_ladder` / `test_offline_audit`
吃的是**真实工程样本**，这些样本不进仓库（`sandbox/` 与客户工程都被 `.gitignore` 挡住）。
放一份样本到 `sandbox/real/` 下，它们就会从 SKIP 变成真正的断言。

## 2. 真机门禁（需要 AutoShop）

```bash
python tests/e2e.py            # 14 步：启动/树/文档/IL/编译/保存/关闭
python tests/e2e_create.py     # 6 步：新建工程（向导 + 系列选择）
python tests/e2e_apply.py      # 7 步：写程序并回读
python tests/e2e_symbols.py    # 9 步：符号表读写
python tests/e2e_monitor.py    # 6 步：监控表读写
python tests/e2e_programs.py   # 9 步：三个程序一起读写
python tests/e2e_project.py    # 9 步：工程汇总 + 打包/另存
python tests/e2e_check.py      # 11 步：体检 findings
python tests/e2e_cli.py        # 17 步：CLI 每个 verb 跑一遍（子进程）
```

全部在 `sandbox/` 里自建工程，**不要**指向客户工程。跑之前关掉其它套件
（抢同一个 AutoShop 实例会报 `COMError 事件无法调用任何订户`）。

## 3. 现场自检

```bash
autoshopkit doctor
```

期望字段：`project_open=true`、`has_tree=true`、`has_document=true`、
`il_editor=true`（H3U）、`output_pane=true`、`frida`/`comtypes` 版本、`dialogs_open=[]`。

## 4. 提交前

```bash
python -m pytest tests -q && python tools/selfcheck.py
```
