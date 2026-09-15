"""
给排水专业规范规则 — 管径 / 坡度 / 间距检查
Phase 3 第二专业接入。

设计取舍（沿用 Phase 2 开放封闭范式）:
- 元素模型 (PlumbingPipe) 在这里定义, 规则走 DSL (default.json 里
  plumbing-* 条目), 不建硬编码规则类 —— 与 34 个已有类互不干扰。
- 阈值暂用占位默认值并标 TBD, 规范条文由业务侧确认后填入 default.json,
  不用重开一轮改代码 (改 JSON 即可, 这是 DSL 化的本意)。

参考: GB 50015 (建筑给水排水设计标准) — 具体条文号/数值待业务确认。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlumbingPipe:
    """排水管道元素 — 给排水专业检查的对象。

    字段:
        id: 唯一标识
        pipe_type: 管类 (waste 排污 / vent 通气管 / drain 排水横管 ...)
        diameter_mm: 公称管径 (mm, 如 DN50 -> 50)
        slope: 坡度, 百分比数值 (2 表示 2%)
        distance_to_manhole_m: 距检查井/立管距离 (m, 间距检查用)
    """

    id: str
    pipe_type: str
    diameter_mm: int
    slope: float
    distance_to_manhole_m: float = 0.0


def register_plumbing_elements() -> None:
    """占位注册点: 未来给排水元素在 CAD 出图侧的映射钩子。

    本 Phase 3 骨架阶段只做规则侧, 元素从 DWG 抽取的接线
    由后续「给排水元素提取」任务负责, 此处留接口不实现。
    """
