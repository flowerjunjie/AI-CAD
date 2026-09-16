"""电气元素抽取层测试 (对称 test_plumbing_extractor)。

验证 points → ElectricalOutlet / ElectricalSwitch 的纯转换:
分型正确 / 高度占位+缺省兜底 / 字段齐全 / 不可变 (不 mutation 入参)。
不依赖规范数值 (height_m 缺省时是占位+warning, 业务确认后可传入真实值)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.agents.src.tools.electrical_extractor import extract_electrical_points
from src.rules.src.electrical import ElectricalOutlet, ElectricalSwitch


def test_outlet_from_point():
    elems = extract_electrical_points([
        {"kind": "outlet", "x": 1.0, "y": 2.0, "height_m": 0.3,
         "room_type": "kitchen", "has_earthing": False},
    ])
    assert len(elems) == 1
    o = elems[0]
    assert isinstance(o, ElectricalOutlet)
    assert o.height_m == 0.3
    assert o.room_type == "kitchen"
    assert o.has_earthing is False
    assert o.x == 1.0 and o.y == 2.0


def test_switch_from_point():
    elems = extract_electrical_points([
        {"kind": "switch", "x": 0.5, "y": 0.5, "height_m": 1.3, "room_type": "door"},
    ])
    assert isinstance(elems[0], ElectricalSwitch)
    assert elems[0].height_m == 1.3
    assert elems[0].room_type == "door"


def test_missing_kind_defaults_to_outlet():
    elems = extract_electrical_points([{"x": 1.0, "y": 1.0, "height_m": 0.3}])
    assert isinstance(elems[0], ElectricalOutlet)


def test_missing_height_uses_placeholder_not_silently_wrong():
    """点位没给 height_m → 用占位默认 (不崩, 不当规范数据)。"""
    elems = extract_electrical_points([{"kind": "switch", "x": 0.0, "y": 0.0}])
    assert elems[0].height_m == 1.3  # switch 占位默认
    elems2 = extract_electrical_points([{"kind": "outlet", "x": 0.0, "y": 0.0}])
    assert elems2[0].height_m == 0.3  # outlet 占位默认


def test_missing_room_type_falls_back():
    elems = extract_electrical_points([{"kind": "outlet", "height_m": 0.3}])
    assert elems[0].room_type == "living"
    assert elems[0].has_earthing is True  # outlet 默认接地


def test_mixed_points_keep_order_and_types():
    elems = extract_electrical_points([
        {"kind": "outlet", "height_m": 0.3, "id": "o1"},
        {"kind": "switch", "height_m": 1.3, "id": "sw1"},
        {"kind": "outlet", "height_m": 0.5, "id": "o2"},
    ])
    assert [type(e).__name__ for e in elems] == ["ElectricalOutlet", "ElectricalSwitch", "ElectricalOutlet"]
    assert [e.id for e in elems] == ["o1", "sw1", "o2"]


def test_id_generated_when_missing():
    elems = extract_electrical_points([{"kind": "outlet", "height_m": 0.3}])
    assert elems[0].id == "outlet-0"


def test_no_mutation_of_inputs():
    """构造新元素, 不 mutation 传入的点位 dict (红线)。"""
    p = {"kind": "outlet", "height_m": 0.3, "room_type": "living"}
    snapshot = dict(p)
    extract_electrical_points([p])
    assert p == snapshot, "入参 dict 被改"
