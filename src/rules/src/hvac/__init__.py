"""
暖通 (HVAC) 专业规范规则 — 风管 / 空调机组 / 风口 检查
Phase 5 第三专业接入（照 Phase 3 给排水 / Phase 4 电气范式）。

设计取舍（沿用开放封闭范式）:
- 元素模型 (HvacDuct / HvacUnit / HvacGrille) 在这里定义, 规则走
  DSL (default.json 里 hvac-* 条目), 不建硬编码规则类 —— 与
  34 个已有类互不干扰。
- 阈值暂用占位默认值并标 TBD, 规范条文由业务侧确认后填入
  default.json, 不用重开一轮改代码 (改 JSON 即可)。

参考: GB 50736 (民用建筑空调设计规范) / GB 50189 (公共建筑节能设计标准)
— 具体条文号/数值待业务确认。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HvacDuct:
    """风管元素 — 暖通专业检查的对象。

    字段:
        id: 唯一标识
        duct_type: 风管类型 (supply 送风 / return 回风 / exhaust 排风)
        diameter_mm: 公称管径/矩形短边 (mm, 占位)
        airflow_m3h: 风量 (m3/h, 占位)
        velocity_ms: 风速 (m/s, 风速区间检查用)
    """

    id: str
    duct_type: str
    diameter_mm: int
    airflow_m3h: float
    velocity_ms: float


@dataclass
class HvacUnit:
    """空调机组元素 — 暖通专业检查的对象。

    字段:
        id: 唯一标识
        unit_type: 机组类型 (room 室内机 / outdoor 室外机 / ah 空调机组)
        cooling_kw: 制冷量 (kW, 占位)
        location_type: 安装位置类型 (indoor 室内 / outdoor 室外)
        x: 平面坐标 x (m, 占位, 供后续定位类规则用)
        y: 平面坐标 y (m, 占位)
    """

    id: str
    unit_type: str
    cooling_kw: float
    location_type: str = "indoor"
    x: float = 0.0
    y: float = 0.0


@dataclass
class HvacGrille:
    """风口元素 — 暖通专业检查的对象。

    字段:
        id: 唯一标识
        grille_type: 风口类型 (supply 送风口 / return 回风口)
        height_m: 安装高度 (m, 如 2.5 常规风口 / 吊顶上方高位送风)
        airflow_m3h: 通过风量 (m3/h, 占位)
        room_type: 所在房间类型 (kitchen 厨房 / living 客厅 / bedroom 卧室 ...)
        x: 平面坐标 x (m, 占位)
        y: 平面坐标 y (m, 占位)
    """

    id: str
    grille_type: str
    height_m: float
    airflow_m3h: float = 0.0
    room_type: str = "living"
    x: float = 0.0
    y: float = 0.0
