"""
电气专业规范规则 — 插座 / 开关 安装高度检查
Phase 4 第三专业接入（照 Phase 3 给排水范式）。

设计取舍（沿用开放封闭范式）:
- 元素模型 (ElectricalOutlet / ElectricalSwitch) 在这里定义, 规则走
  DSL (default.json 里 electrical-* 条目), 不建硬编码规则类 —— 与
  34 个已有类互不干扰。
- 阈值暂用占位默认值并标 TBD, 规范条文由业务侧确认后填入
  default.json, 不用重开一轮改代码 (改 JSON 即可)。

参考: GB 50096 / GB 50303 (建筑电气工程施工质量验收规范) —
具体条文号/数值待业务确认。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ElectricalOutlet:
    """插座元素 — 电气专业检查的对象。

    字段:
        id: 唯一标识
        height_m: 安装高度 (m, 如 0.3 低位插座 / 1.3 常规台面插座)
        room_type: 所在房间类型 (kitchen 厨房 / living 客厅 / bedroom 卧室 ...)
        x: 平面坐标 x (m, 占位, 供后续定位类规则用)
        y: 平面坐标 y (m, 占位)
        has_earthing: 是否具备接地 (bool, 厨房/卫生间插座接地检查用)
    """

    id: str
    height_m: float
    room_type: str
    x: float = 0.0
    y: float = 0.0
    has_earthing: bool = True


@dataclass
class ElectricalSwitch:
    """开关元素 — 电气专业检查的对象。

    字段:
        id: 唯一标识
        height_m: 安装高度 (m, 如 1.3 常规开门侧安装高度)
        room_type: 所在房间类型 (door 门厅侧 / living 客厅 ...)
        x: 平面坐标 x (m, 占位)
        y: 平面坐标 y (m, 占位)
    """

    id: str
    height_m: float
    room_type: str
    x: float = 0.0
    y: float = 0.0
