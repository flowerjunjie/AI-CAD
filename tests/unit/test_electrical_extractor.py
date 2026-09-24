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


# ─── DXF 造数据辅助 (照 test_structural_extractor._make_structural_dxf 范式) ───
def _make_electrical_dxf(path):
    """造含电气 INSERT 块的 DXF。

    放:
      ELEC_OUTLET (块类): INSERT 块名 OUTLET_STD, 插入点 (1.0, 2.0)
      ELEC_SWITCH (块类): INSERT 块名 SWITCH_STD, 插入点 (0.5, 0.5)
      ELEC_OUTLET 同层加一个 CIRCLE 小圆圈 — 只认 INSERT, 不算点位。
    """
    import ezdxf

    doc = ezdxf.new("AC1027")
    for layer in ("ELEC_OUTLET", "ELEC_SWITCH"):
        doc.layers.new(layer)
    for blk in ("OUTLET_STD", "SWITCH_STD"):
        doc.blocks.new(blk)
    msp = doc.modelspace()

    # ezdxf 1.4.4: add_blockref(name, insert) 的 insert 是位置参
    msp.add_blockref("OUTLET_STD", (1.0, 2.0), dxfattribs={"layer": "ELEC_OUTLET"})
    msp.add_blockref("SWITCH_STD", (0.5, 0.5), dxfattribs={"layer": "ELEC_SWITCH"})
    msp.add_circle((9.0, 9.0), 0.1, dxfattribs={"layer": "ELEC_OUTLET"})

    doc.saveas(path)


def _open_reader(dxf_path):
    from src.agents.src.tools.cad_tools import DXFReader

    reader = DXFReader(dxf_path)
    assert reader.open(), "DXF open() 失败"
    return reader


# ─── DXF-based cases: 真实 DXF 喂 get_electrical_points (G2 根治证据) ───
def test_electrical_points_real_dxf_full_chain(tmp_path):
    """真实 DXF 里造电气 INSERT 块 → reader.get_electrical_points() dict 契约
    → 喂 extract_electrical_points 全链路通。"""
    p = str(tmp_path / "electrical.dxf")
    _make_electrical_dxf(p)
    reader = _open_reader(p)

    pts = reader.get_electrical_points()  # 默认 ELEC_OUTLET + ELEC_SWITCH
    assert len(pts) == 2, f"OUTLET 1 + SWITCH 1 = 2 点位, 实际 {len(pts)}"

    # 契约字段: kind/id/x/y/height_m/room_type/has_earthing (纯 dict, 与 ezdxf 解耦)
    by_id = {q["id"]: q for q in pts}
    assert set(by_id) == {"OUTLET_STD", "SWITCH_STD"}, \
        f"只认 INSERT, CIRCLE 不算点位, 实际 {set(by_id)}"
    outlet, switch = by_id["OUTLET_STD"], by_id["SWITCH_STD"]
    assert outlet["kind"] == "outlet" and switch["kind"] == "switch", \
        f"占位映射: 块名 OUTLET_STD→outlet / SWITCH_STD→switch, 实际 " \
        f"{outlet['kind']}/{switch['kind']}"
    assert outlet["x"] == 1.0 and outlet["y"] == 2.0, \
        f"OUTLET_STD 插入点应 (1.0,2.0), 实际 ({outlet['x']},{outlet['y']})"
    assert switch["x"] == 0.5 and switch["y"] == 0.5, \
        f"SWITCH_STD 插入点应 (0.5,0.5), 实际 ({switch['x']},{switch['y']})"
    for q in pts:  # height_m/room_type/has_earthing 全 None 占位, 由 extractor 兜底
        assert q["height_m"] is None and q["room_type"] is None, \
            f"缺省字段应 None 占位, 实际 {q}"

    # 全链路: 真实 dict → 抽层 → 元素
    elems = extract_electrical_points(pts)
    assert [type(e).__name__ for e in elems] == ["ElectricalOutlet", "ElectricalSwitch"], \
        f"全链路应 outlet→ElectricalOutlet / switch→ElectricalSwitch, 实际 " \
        f"{[type(e).__name__ for e in elems]}"
    assert elems[0].x == 1.0 and elems[0].y == 2.0
    assert elems[0].height_m == 0.3, "height_m 缺省 → 占位 0.3 (outlet)"
    assert elems[1].height_m == 1.3, "height_m 缺省 → 占位 1.3 (switch)"


def test_electrical_points_requires_open():
    """未 open() 取电气点位 → RuntimeError。"""
    from src.agents.src.tools.cad_tools import DXFReader

    reader = DXFReader("nonexistent.dxf")
    try:
        reader.get_electrical_points()
        assert False, "未 open 应抛 RuntimeError"
    except RuntimeError:
        pass


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
