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


# ─── DXF 造数据辅助 (照 test_structural_extractor._make_structural_dxf 范式) ───
def _make_hvac_dxf(path):
    """造含暖通 INSERT 块的 DXF。

    放:
      HVAC_DUCT (块类): INSERT 块名 DUCT_STD, 插入点 (0.0, 0.0)
      HVAC_UNIT (块类): INSERT 块名 UNIT_STD, 插入点 (4.0, 6.0)
      HVAC_GRILLE (块类): INSERT 块名 GRILLE_STD, 插入点 (2.0, 3.0)
    """
    import ezdxf

    doc = ezdxf.new("AC1027")
    for layer in ("HVAC_DUCT", "HVAC_UNIT", "HVAC_GRILLE"):
        doc.layers.new(layer)
    for blk in ("DUCT_STD", "UNIT_STD", "GRILLE_STD"):
        doc.blocks.new(blk)
    msp = doc.modelspace()

    # ezdxf 1.4.4: add_blockref(name, insert) 的 insert 是位置参
    msp.add_blockref("DUCT_STD", (0.0, 0.0), dxfattribs={"layer": "HVAC_DUCT"})
    msp.add_blockref("UNIT_STD", (4.0, 6.0), dxfattribs={"layer": "HVAC_UNIT"})
    msp.add_blockref("GRILLE_STD", (2.0, 3.0), dxfattribs={"layer": "HVAC_GRILLE"})

    doc.saveas(path)


def _open_reader(dxf_path):
    from src.agents.src.tools.cad_tools import DXFReader

    reader = DXFReader(dxf_path)
    assert reader.open(), "DXF open() 失败"
    return reader


# ─── DXF-based cases: 真实 DXF 喂 get_hvac_points (G2 根治证据) ───
def test_hvac_points_real_dxf_full_chain(tmp_path):
    """真实 DXF 里造暖通 INSERT 块 → reader.get_hvac_points() dict 契约
    → 喂 extract_hvac_points 全链路通。"""
    p = str(tmp_path / "hvac.dxf")
    _make_hvac_dxf(p)
    reader = _open_reader(p)

    pts = reader.get_hvac_points()  # 默认 HVAC_DUCT + HVAC_UNIT + HVAC_GRILLE
    assert len(pts) == 3, f"3 块 = 3 点位, 实际 {len(pts)}"

    by_id = {q["id"]: q for q in pts}
    assert set(by_id) == {"DUCT_STD", "UNIT_STD", "GRILLE_STD"}, \
        f"点位 id 应为块名, 实际 {set(by_id)}"
    duct, unit, grille = by_id["DUCT_STD"], by_id["UNIT_STD"], by_id["GRILLE_STD"]
    # 占位映射: 块名 DUCT_STD→duct / UNIT_STD→unit / GRILLE_STD→grille
    assert (duct["kind"], unit["kind"], grille["kind"]) == ("duct", "unit", "grille"), \
        f"kind 映射不符, 实际 {(duct['kind'], unit['kind'], grille['kind'])}"
    assert unit["x"] == 4.0 and unit["y"] == 6.0, \
        f"UNIT_STD 插入点应 (4.0,6.0), 实际 ({unit['x']},{unit['y']})"
    # 每个点位只带当前 kind 相关的缺省键 (value None), extractor 按 kind 兜底占位
    assert "cooling_kw" in unit and "duct_type" not in unit, \
        f"unit 点位应只带 unit 相关键, 实际 {list(unit)}"
    assert "duct_type" in duct and "unit_type" not in duct, \
        f"duct 点位应只带 duct 相关键, 实际 {list(duct)}"

    # 全链路: 真实 dict → 抽层 → 元素 (缺省字段走占位 + warning, 不崩)
    elems = extract_hvac_points(pts)
    assert [type(e).__name__ for e in elems] == ["HvacDuct", "HvacUnit", "HvacGrille"], \
        f"全链路应 duct/unit/grille → HvacDuct/HvacUnit/HvacGrille, 实际 " \
        f"{[type(e).__name__ for e in elems]}"
    assert elems[0].diameter_mm == 100, "duct 缺省 → 占位 100mm"
    assert elems[1].unit_type == "room" and elems[1].x == 4.0, \
        "unit 缺省 → 占位 room, x 保持真实值 4.0"


def test_hvac_points_requires_open():
    """未 open() 取暖通点位 → RuntimeError。"""
    from src.agents.src.tools.cad_tools import DXFReader

    reader = DXFReader("nonexistent.dxf")
    try:
        reader.get_hvac_points()
        assert False, "未 open 应抛 RuntimeError"
    except RuntimeError:
        pass


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
