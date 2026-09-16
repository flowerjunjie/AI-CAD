"""电气元素从 DXF 的抽取层（对称 plumbing_extractor）。

给排水把「管道线段」配对成 PlumbingPipe；电气把「插座/开关点位」转成
ElectricalOutlet / ElectricalSwitch，供规则引擎（default.json 的 electrical-*
DSL 条目）做检查。

对称点 + 一处务实取舍:
- 给排水抽取依赖图层名 (PIPE_WASTE 等, 有行业约定); 电气插座/开关在不同 DWG
  里画法不统一 (可能是 INSERT 块 / 圆点 / 图层命名各异), 本项目尚未有既定约定。
  所以本层把「图层→点位」的解析放在 get_electrical_points (见 cad_tools),
  本抽取层只做「点位 dict → 元素 dataclass」的纯转换, 不臆造图层画法。
- 点位 dict 约定 (get_electrical_points 的产出):
      {"kind": "outlet"|"switch", "x": float, "y": float,
       "height_m": float(可选, 缺省按 kind 给占位), "room_type": str(可选),
       "has_earthing": bool(可选, outlet 用)}
- 高度是电气规则的核心字段, 但点位若没带 height_m, 用占位默认值并记 warning
  (不静默给错高度当规范数据, 也不崩)。
- 不可变: 全部构造新元素, 不 mutation 入参。
"""
from __future__ import annotations

import logging

from src.rules.src.electrical import ElectricalOutlet, ElectricalSwitch

logger = logging.getLogger(__name__)

# 占位默认高度 (m) — 业务确认规范后由 get_electrical_points 传真实 height_m 覆盖。
_PLACEHOLDER_HEIGHT = {"outlet": 0.3, "switch": 1.3}  # TBD: 待业务确认
_DEFAULT_ROOM_TYPE = "living"  # 点位没标房间时兜底


def _coerce_height(kind: str, raw) -> float:
    """点位带 height_m 用之; 没带用占位默认并记 warning (不当规范数据, 也不崩)。"""
    if raw is not None:
        return float(raw)
    logger.warning(
        "电气点位 %s 未提供 height_m, 用占位默认 %.2fm (TBD 待业务确认)", kind, _PLACEHOLDER_HEIGHT.get(kind, 0.0)
    )
    return _PLACEHOLDER_HEIGHT.get(kind, 0.0)


def extract_electrical_points(points: list[dict]) -> list:
    """把已解析的插座/开关点位转成 ElectricalOutlet / ElectricalSwitch 实例。

    points: get_electrical_points 的产出, 每项 dict 见模块 docstring 的点位约定。
    返回元素列表 (outlet → ElectricalOutlet, switch → ElectricalSwitch),
    顺序与入参一致, 供 rule_check_node 的分发表 / engine.check 消费。
    """
    elems = []
    for i, p in enumerate(points):
        kind = p.get("kind", "outlet")
        base = dict(id=p.get("id") or f"{kind}-{i}",
                    height_m=_coerce_height(kind, p.get("height_m")),
                    room_type=p.get("room_type", _DEFAULT_ROOM_TYPE),
                    x=float(p.get("x", 0.0)),
                    y=float(p.get("y", 0.0)))
        if kind == "switch":
            elems.append(ElectricalSwitch(**base))
        else:
            base["has_earthing"] = bool(p.get("has_earthing", True))
            elems.append(ElectricalOutlet(**base))
    return elems
