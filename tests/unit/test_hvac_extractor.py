"""暖通元素抽取层测试 (对称 test_electrical_extractor)。

验证 points → HvacDuct / HvacUnit / HvacGrille 的纯转换:
分型正确 / 占位+缺省兜底 / 字段齐全 / 不可变 (不 mutation 入参)。
不依赖规范数值 (缺省字段是占位+warning, 业务确认后可传入真实值)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.agents.src.tools.hvac_extractor import extract_hvac_points
from src.rules.src.hvac import HvacDuct, HvacUnit, HvacGrille


def test_duct_from_point():
    elems = extract_hvac_points([
        {"kind": "duct", "duct_type": "supply", "diameter_mm": 100,
         "airflow_m3h": 500.0, "velocity_ms": 4.0},
    ])
    assert len(elems) == 1
    d = elems[0]
    assert isinstance(d, HvacDuct)
    assert d.duct_type == "supply"
    assert d.diameter_mm == 100
    assert d.airflow_m3h == 500.0
    assert d.velocity_ms == 4.0


def test_unit_from_point():
    elems = extract_hvac_points([
        {"kind": "unit", "unit_type": "outdoor", "cooling_kw": 3.5,
         "location_type": "outdoor", "x": 1.0, "y": 2.0},
    ])
    assert isinstance(elems[0], HvacUnit)
    assert elems[0].unit_type == "outdoor"
    assert elems[0].cooling_kw == 3.5
    assert elems[0].location_type == "outdoor"
    assert elems[0].x == 1.0 and elems[0].y == 2.0


def test_grille_from_point():
    elems = extract_hvac_points([
        {"kind": "grille", "grille_type": "supply", "height_m": 2.5,
         "room_type": "kitchen"},
    ])
    assert isinstance(elems[0], HvacGrille)
    assert elems[0].grille_type == "supply"
    assert elems[0].height_m == 2.5
    assert elems[0].room_type == "kitchen"


def test_missing_kind_defaults_to_duct():
    elems = extract_hvac_points([{"duct_type": "return", "velocity_ms": 3.0}])
    assert isinstance(elems[0], HvacDuct)


def test_missing_fields_use_placeholder_not_silently_wrong():
    """点位没给字段 → 用占位默认 (不崩, 不当规范数据)。"""
    elems = extract_hvac_points([{"kind": "unit"}])
    assert elems[0].unit_type == "room"          # 占位默认
    assert elems[0].location_type == "indoor"    # 占位默认
    elems2 = extract_hvac_points([{"kind": "grille"}])
    assert elems2[0].height_m == 2.5             # grille 占位默认
    elems3 = extract_hvac_points([{"kind": "duct"}])
    assert elems3[0].diameter_mm == 100          # duct 占位默认


def test_mixed_points_keep_order_and_types():
    elems = extract_hvac_points([
        {"kind": "duct", "id": "d1", "velocity_ms": 4.0},
        {"kind": "unit", "id": "u1", "cooling_kw": 3.5},
        {"kind": "grille", "id": "g1", "height_m": 2.5},
    ])
    assert [type(e).__name__ for e in elems] == ["HvacDuct", "HvacUnit", "HvacGrille"]
    assert [e.id for e in elems] == ["d1", "u1", "g1"]


def test_id_generated_when_missing():
    elems = extract_hvac_points([{"kind": "unit"}])
    assert elems[0].id == "unit-0"


def test_no_mutation_of_inputs():
    """构造新元素, 不 mutation 传入的点位 dict (红线)。"""
    p = {"kind": "grille", "grille_type": "supply", "height_m": 2.5}
    snapshot = dict(p)
    extract_hvac_points([p])
    assert p == snapshot, "入参 dict 被改"
