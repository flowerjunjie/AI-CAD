"""
pytest 根 conftest — 把「项目根进 sys.path」收敛到一处。

此前每个测试文件各自 `sys.path.insert(0, dirname×N(__file__))` 手插,
且 N 各写各的 (3 层/4 层混用), 是「dirname 层数数错导致 import 不到 src.*」
反复踩坑的根源。统一在这里插一次, 所有测试 (unit + integration) 自动可用
`import src.rules.src...` / `import src.agents.src...`, 无需再手插。

只加不删: 不改动任何既有测试文件, 它们的手插逻辑保留 (幂等, 多插无害),
本 conftest 提供的是「即使新测试忘手插也能 import 到」的兜底。
"""
import os
import sys

# 项目根 (本文件所在目录) — src/ 包就在这里
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
