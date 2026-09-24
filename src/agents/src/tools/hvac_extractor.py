"""暖通元素从 DXF 的抽取层（对称 electrical_extractor）。

给排水把「管道线段」配对成 PlumbingPipe；电气把「插座/开关点位」转成
Outlet/Switch；暖通把「风口点位 + 机组点位」转成 HvacGrille / HvacUnit，
供规则引擎（default.json 的 hvac-* DSL 条目）做检查。

对称点 + 一处务实取舍（照 electrical_extractor）:
- 暖通风口/机组在不同 DWG 里画法不统一，本项目尚未有既定约定。
  本抽取层只做「点位 dict → 元素 dataclass」的纯转换, 不臆造图层画法。
- 点位 dict 约定（上游 get_hvac_points 的产出）:
      {"kind": "grille"|"unit"|"duct", ...}
      grille: {"grille_type": str(可选), "height_m": float(可选),
               "room_type": str(可选), "airflow_m3h": float(可选), x/y}
      unit:   {"unit_type": str(可选), "cooling_kw": float(可选),
               "location_type": str(可选), x/y}
      duct:   {"duct_type": str(可选), "diameter_mm": int(可选),
               "velocity_ms": float(可选), "airflow_m3h": float(可选)}
- 各字段缺省用占位默认值并记 warning (不当规范数据, 也不崩)。
- 不可变: 全部构造新元素, 不 mutation 入参。
"""
from __future__ import annotations

import logging

from src.rules.src.hvac import HvacDuct, HvacUnit, HvacGrille

logger = logging.getLogger(__name__)

# 占位默认值 — 业务确认规范后由上游点位传真实值覆盖。全部 TBD 待确认。
_PLACEHOLDER = {
    "duct": {"duct_type": "supply", "diameter_mm": 100, "velocity_ms": 0.0,
             "airflow_m3h": 0.0},
    "unit": {"unit_type": "room", "cooling_kw": 0.0, "location_type": "indoor"},
    "grille": {"grille_type": "supply", "height_m": 2.5, "airflow_m3h": 0.0,
               "room_type": "living"},
}
_DEFAULT_KIND = "duct"


def _coerce(kind: str, key: str, raw, cast=str) -> object:
    """点位带该字段用之; 没带用占位默认并记 warning (不当规范数据, 也不崩)。"""
    if raw is not None:
        return cast(raw)
    default = _PLACEHOLDER[kind].get(key)
    logger.warning(
        "暖通点位 %s 未提供 %s, 用占位默认 %r (TBD 待业务确认)", kind, key, default
    )
    return cast(default)


def extract_hvac_points(points: list[dict]) -> list:
    """把已解析的暖通点位转成 HvacDuct / HvacUnit / HvacGrille 实例。

    points: 上游 get_hvac_points 的产出, 每项 dict 见模块 docstring 的点位约定。
    返回元素列表 (duct → HvacDuct, unit → HvacUnit, grille → HvacGrille),
    顺序与入参一致, 供 rule_check_node 的分发表 / engine.check 消费。
    """
    elems = []
    for i, p in enumerate(points):
        kind = p.get("kind", _DEFAULT_KIND)
        base_id = p.get("id") or f"{kind}-{i}"

        if kind == "unit":
            elems.append(HvacUnit(
                id=base_id,
                unit_type=_coerce(kind, "unit_type", p.get("unit_type")),
                cooling_kw=_coerce(kind, "cooling_kw", p.get("cooling_kw"), float),
                location_type=_coerce(kind, "location_type", p.get("location_type")),
                x=float(p.get("x", 0.0)),
                y=float(p.get("y", 0.0)),
            ))
        elif kind == "grille":
            elems.append(HvacGrille(
                id=base_id,
                grille_type=_coerce(kind, "grille_type", p.get("grille_type")),
                height_m=_coerce(kind, "height_m", p.get("height_m"), float),
                airflow_m3h=_coerce(kind, "airflow_m3h", p.get("airflow_m3h"), float),
                room_type=_coerce(kind, "room_type", p.get("room_type")),
                x=float(p.get("x", 0.0)),
                y=float(p.get("y", 0.0)),
            ))
        else:
            elems.append(HvacDuct(
                id=base_id,
                duct_type=_coerce(kind, "duct_type", p.get("duct_type")),
                diameter_mm=_coerce(kind, "diameter_mm", p.get("diameter_mm"), int),
                airflow_m3h=_coerce(kind, "airflow_m3h", p.get("airflow_m3h"), float),
                velocity_ms=_coerce(kind, "velocity_ms", p.get("velocity_ms"), float),
            ))
    return elems
