"""
结构 (Structural) 专业规范规则 — 梁 / 柱 / 承重墙 检查
Phase 6 第四专业接入（照 Phase 3 给排水 / Phase 4 电气 / Phase 5 暖通范式）。

设计取舍（沿用开放封闭范式, 详见 docs/structural-upstream-contract.md）:
- 元素模型 (StructuralBeam / StructuralColumn) 在这里定义, 规则走
  DSL (default.json 里 structural-* 条目), 不建硬编码规则类 —— 与
  硬编码规则类互不干扰 (守硬编码类零改动红线)。
- 阈值暂用占位默认值并标 TBD, 规范条文由业务侧确认后填入 default.json,
  不用重开一轮改代码 (改 JSON 即可, 这是 DSL 化的本意)。

参考: GB 50010 (混凝土结构设计规范) / GB 50011 (建筑抗震设计规范)
— 具体条文号/数值待业务确认。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StructuralBeam:
    """梁 / 承重墙元素 — 结构专业检查的对象（线段类, 上游走 LINE/LWPOLYLINE）。

    字段:
        id: 唯一标识
        beam_type: 梁类 (main 主梁 / secondary 次梁 / shear_wall 承重墙)
        width_mm: 截面宽 (mm, 占位)
        depth_mm: 截面高 (mm, 占位, 梁高宽比 / 最小截面检查用)
        x: 平面坐标 x (m, 占位, 供后续定位类规则用)
        y: 平面坐标 y (m, 占位)
    """

    id: str
    beam_type: str
    width_mm: int
    depth_mm: int
    x: float = 0.0
    y: float = 0.0


@dataclass
class StructuralColumn:
    """柱 / 基础 / 节点元素 — 结构专业检查的对象（块类, 上游走 INSERT 块）。

    字段:
        id: 唯一标识
        column_type: 柱类 (frame 框架柱 / construction 构造柱 / foundation 基础)
        section_mm: 截面短边 (mm, 占位, 最小截面尺寸检查用)
        x: 平面坐标 x (m, 占位)
        y: 平面坐标 y (m, 占位)
    """

    id: str
    column_type: str
    section_mm: int
    x: float = 0.0
    y: float = 0.0
