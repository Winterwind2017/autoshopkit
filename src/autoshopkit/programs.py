"""The kitchen-sink program: every verified IL feature in one program.

Used by the acceptance suite to prove that a realistic program (not just isolated
snippets) converts and compiles.
"""
KITCHEN_SINK = """//network one: output + timer
LD X0
OUT Y0
LD X1
OUT T0 K10
//network two: data move
LD T0
MOV K1 D0
DMOV K10 D2
//network three: conditional jump over a rung
LD X2
CJ P0
LD X3
OUT Y1
LBL P0
//network four: loop and stack
LD X4
MPS
AND X5
OUT Y2
MPP
FOR K3
INC D1
NEXT
"""

# One instruction from each family that ``ilparse`` classifies, all verified to compile
# (see docs/IL-results.md).  Used by ``tools/test_ilparse.py`` to keep the operand-role
# table honest without needing AutoShop.
COVERAGE_PROGRAM = """//contacts and coils
LD X0
AND X1
OR X2
OUT Y0
SET M0
RST M0
PLS M1
//timers and counters
LD X0
OUT T0 K10
OUT C0 K5
//data transfer and arithmetic
LD X0
MOV K1 D0
DMOV K10 D2
ADD D0 D1 D3
CMP K1 K5 M10
ZCP K1 K5 D0 M20
XCH D0 D1
SWAP D2
NEG D3
BMOV D0 D10 K5
ZRST M30 M40
//stack and control
LD X0
MPS
AND X1
OUT Y1
MPP
OUT Y2
FOR K5
INC D4
NEXT
LD X0
CJ P0
LBL P0
CJEND
LD X0
CALL SBR_001
"""

# A realistic machine sequence used as the "real program" for validation and for the
# ladder-geometry experiments.  Every instruction here is in the verified corpus
# (docs/IL-results.md), so it compiles clean on an H3U project.
MACHINE_PROGRAM = """//网络1 原点与气源条件
LD X0
AND X1
OUT M0
//网络2 运行自锁
LD X2
OR M10
ANI X3
OUT M10
//网络3 上料气缸
LD M10
AND M0
ANI X4
OUT Y0
//网络4 上料到位延时
LD X4
OUT T0 K5
//网络5 夹紧
LD T0
OR M11
ANI X5
OUT M11
OUT Y1
//网络6 冲压
LD M11
AND X5
ANI X6
OUT Y2
//网络7 保压延时
LD X6
OUT T1 K20
//网络8 退料
LD T1
OUT Y3
//网络9 循环计数
LD T1
OUT C0 K100
//网络10 计数到达报警
LD C0
OUT M12
//网络11 节拍计时
LD M10
OUT T2 K300
//网络12 产量写入寄存器
LD T1
INC D0
//网络13 产量比较
LD>= D0 K10
OUT M13
//网络14 报警复位
LD X7
CALL SBR_001
//网络15 停止时清输出
LDI M10
ZRST M11 M13
"""
