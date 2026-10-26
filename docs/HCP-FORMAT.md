# AutoShop 工程文件格式

四类文件，两种编码：**明文部件**与**加密容器**。全部实测，样本来自两个真实工程
（H3U 与 H5U 各一）加四个 `.hcpp` 备份。

## 1. 明文部件：`0x80` 头 + 具名 chunk

`.gdt`（符号/变量）、`.mon`（监控）、`.crs`（交叉引用）、`.LD`（梯形图）、`Config.sdt` 等：

```
偏移 0x00  "AutoShop"                       8 字节
     0x08  00 × 12
     0x14  "2.6"        版本                 （H3U 另见 "2.0"/"2.1"）
     0x19  "6.0"
     0x1f  "clQobtqa"                        8 字节封印（见 §3）
     0x27  00 × …
     0x7c  <count:u16><0xffff><ver:u16><name_len:u16><name>
```

chunk 名实测：`CLVTItem`（局部变量）、`CGVTItem`（全局符号）、`CElemMonItem`（监控）、
`CCrossRefInfo`（交叉引用）。

### `CGVTItem` 记录（两代不同）

```
H3U: <00><name_len><name><addr_len><addr><note_len><note utf-8><00 00 00 00 06 80>
H5U: <00><name_len><name><note_len><note utf-8><00 00 00 00 06 80>      ← 没有地址字段
```

H5U 的地址在 `VarNameAndAddr.csv`（UTF-16、Tab 分隔）：`名字 \t 0X地址 \t 注释 \t 位宽`。

### `.LD` 梯形图：图，不是图元坐标

每条记录：

```
<u32 a><u32 b><u16 kind><u8 len><ascii text><固定尾部>
```

- `kind` 按操作数族分：`1` 触点/线圈，`2` 单操作数（`SET`/`RST`/`PLS`），
  `3` 双操作数（`ZRST`/`LD=`/`DEMOV`），`4` 带参数框（`TONR`）。
- `a`/`b` 是**图链接**，不是坐标：真实工程 `MAIN.LD` 583 个元件里 428 个前向、155 个后向
  （后向=并联分支复用前面的节点），节点 id 落在同一个分配器簇里。
- **文件里没有屏幕位置字段** —— 绘制由拓扑推导。这是"找不到坐标"的正确答案。

## 2. `.hcpp` 备份：`PPCH` + zlib

```
"PPCH" <00 03> … 然后一条 zlib 流，解压得：
<u32 原长><u32 名字长><name utf-8><u32 长度><原始 .hcp 字节（仍然加密）>
```

`projectfile.read_hcp_backup()` 直接给名字/长度/字节。

## 3. `.hcp` 容器：UTF-16LE XML + 位置相关变换

`.hcp` 不是二进制结构，而是**一份 UTF-16LE 的 XML**，用逐字节、与位置相关的可逆变换保护。
算法来自 `InterfaceMgr.dll`（image base `0x10000000`）：

```
KEY = b"SclSoftware"        # 11 字节，.rdata RVA 0xa5980
j = 0
for i in range(len(data)):
    j = (j + 1) % 11
    b = data[i]
    if i % 2 == 0: b ^= (i & 0xFF)
    data[i] = (b - KEY[j]) & 0xFF        # 解密
    # 加密：b = ((b + KEY[j]) & 0xFF) ^ (i & 0xFF)
```

| RVA | 导出 | 作用 |
| --- | --- | --- |
| `0x4c810` | `?UCodeDecrypt@CUCodeCrypt@@QAEHPB_W0@Z` | 读：Open→Read→解密→写明文 |
| `0x4caa0` | `?UCodeFileEncrypt@CUCodeCrypt@@QAEHPB_W@Z` | 写：读→原地加密→seek 0→写回 |
| `0x4ce60` / `0x4ceb0` | `?EncryptArithmetic` / `?DecryptArithmetic` | 循环本体 |
| `0x36550` / `0x365f0` | `?g_Encrypt` / `?g_Decrypt` | 同一变换（8 字节字段用） |
| `0xa5980` | `"SclSoftware"` | 密钥 |

**为什么它看起来像"22 字节周期的掩码"**：明文是 UTF-16LE，奇数偏移是高字节且恒为 0，
而偶数偏移才 XOR —— 于是密文的奇数字节正好等于密钥字节，形成 11 个字母的循环，
把真正的加法变换遮住了。

**封印**：`EncryptArithmetic(8 个 0 字节) == 63 6c 51 6f 62 74 71 61 == "clQobtqa"`，
就是每个明文部件 0x1f 处那 8 字节 —— 这也解释了为什么这串在工程数据里有、
在任何发布二进制里都找不到字面量。

## 4. 解密后是什么

```xml
<?xml version="1.0" encoding="UTF-16"?>
<project>
  <Version>1</Version><ProjectDesc>…</ProjectDesc><DefaultEditor>0</DefaultEditor>
  <GCMModal>H5U</GCMModal><CPUVersion>RT1.0</CPUVersion><Capbility>200000</Capbility>
  <MaxFileID>43</MaxFileID><MaxSubID>6</MaxSubID><MaxIntID>1</MaxIntID>
  <HardwareFile>H5U.dll</HardwareFile><historycount>5</historycount>
  <projnameex>…</projnameex><asversion>AutoShop V4.8.2.4</asversion>…
  <file id="1"><FileType>1</FileType><ProgType>0</ProgType><Caption>MAIN</Caption>
    <FileName>MAIN.LD</FileName><CreateTime>…</CreateTime>…</file>
  …
</project>
```

实测：H3U 工程 18 304 B → 16 条组件记录、`Capbility 64000`、程序存 **`.IL`**；
H5U 工程 54 926 B → 51 条、`Capbility 200000`、程序存 **`.LD`**。
容器索引因此还告诉你"这台机器的程序是哪种源码形态"。

API：`autoshopkit.hcp.read_project(path)` / `write_project(path, xml)`，
CLI：`autoshopkit hcp --project DIR [--xml] [--write-xml FILE]`。
