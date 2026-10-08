"""
AI-CAD GUI 桥 — 共享层 (被多个域段子模块 + 主 bridge.py 复用的公共符号)。

从 bridge.py 上提的最小共享层, 解耦 B 段 (api_rules_batch_verify) 对 F 段
(_load_sample_raw) 的跨段引用, 使 B / F 域段后续可独立物理搬 (各自 import 本层,
不再互相引用函数)。纯增量, 0 行为改变 (函数体逐字搬移, 判据不变)。

约定 (对齐 CLAUDE.md 重构纪律): 共享层只放「多个域段都引用、且自身无域段归属」的
符号。加新共享符号先 grep 全仓引用面, 确认 ≥2 域段消费才上提, 否则留在原域段。
"""
from __future__ import annotations

import json
import os

# 与 bridge.py 同源的项目根定位 (子模块也在 <root>/src/gui/ 下, 上溯两级)。
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


# ─── 碰撞检测样本键 (M4) + 读样本顶层元素数据 (B/F 域段共用) ───
# 顶层元素数据各带 id, 只取碰撞检测/批量校验用到的键; 键缺失优雅取空 dict。
_CLASH_SAMPLE_KEYS = [
    "structural_beams", "structural_columns", "pipes", "hvac_ducts",
    "outlets", "hvac_grilles",
]


def _load_sample_raw(sample: str) -> dict:
    """读 data/sample/<sample> 顶层元素数据 (键缺失/缺键优雅取空 dict)。

    文件不存在 → HTTPException 404 (诚实报错, 不造假数据)。
    (HTTPException 懒 import, 保持本层无 fastapi 硬依赖面 — 端点调用时才需要。)"""
    from fastapi import HTTPException
    p = os.path.join(ROOT, "data", "sample", sample)
    if not os.path.exists(p):
        raise HTTPException(404, f"样本不存在: {sample}")
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    # 顶层是元素数据 (doors/pipes/... 各带 id), 只取碰撞检测用到的键
    return {k: data.get(k, []) for k in _CLASH_SAMPLE_KEYS}
