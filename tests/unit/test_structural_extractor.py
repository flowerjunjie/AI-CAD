"""
Phase 6 — 结构元素抽取单元测试

验证三块 (对应契约 docs/structural-upstream-contract.md §5 checklist):
① get_structural_segments: 默认纯线段同 plumbing 形态; include_layer=True 输出
   {"start","end","layer"} dict, 逐段带正确图层 (照 get_plumbing_segments 范式)。
② get_structural_blocks (G2 关键证据): **真实 DXF** 里造含 INSERT 块的图,
   证明块类上游真通 —— 用 ezdxf 造真实 DXF 喂 reader, 不是喂 dict 假装上游。
   这是根治电气/暖通 extractor 孤儿模块 (上游 get_*_points 全仓不存在) 的正解:
   结构专业的 INSERT 解析是真接线的。
③ extract_structural_beams / extract_structural_columns 纯函数边界:
   空输入 / 图层·块名映射占位 (TBD) / 未知图层·块名兜底 / 不可变输出。

截面数值为占位 (TBD, 规范条文 GB 50010 / GB 50011 待业务确认),
断言里的注释只描述"占位映射"本身, 不冒充规范条文。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


# ─── DXF 造数据辅助 ─────────────────────────────────────────────
def _make_structural_dxf(path):
    """造含 LINE + LWPOLYLINE + INSERT 块的 DXF (照 _make_plumbing_dxf 范式)。

    放:
      BEAM (线段类):       一条 LINE (0,0)->(4,0)
      WALL_SHEAR (线段类): 一条 LWPOLYLINE 未闭合 3 顶点 (0,2)->(2,2)->(2,4) → 2 段
      COLUMN (块类):       INSERT 块名 COL_K, 插入点 (3.0, 1.0)
      FOUNDATION (块类):   INSERT 块名 FOUND_S, 插入点 (5.0, 5.0)
    """
    import ezdxf

    doc = ezdxf.new("AC1027")
    for layer in ("BEAM", "WALL_SHEAR", "COLUMN", "FOUNDATION"):
        doc.layers.new(layer)
    # INSERT 块定义 (块体内容不影响插入点/name 契约, 造个最小占体)
    for blk in ("COL_K", "FOUND_S"):
        doc.blocks.new(blk)
    msp = doc.modelspace()

    msp.add_line((0, 0), (4, 0), dxfattribs={"layer": "BEAM"})
    msp.add_lwpolyline(
        [(0, 2), (2, 2), (2, 4)],
        dxfattribs={"layer": "WALL_SHEAR", "closed": False},
    )
    # ezdxf 1.4.4: add_blockref(name, insert) 的 insert 是位置参
    msp.add_blockref("COL_K", (3.0, 1.0), dxfattribs={"layer": "COLUMN"})
    msp.add_blockref("FOUND_S", (5.0, 5.0), dxfattribs={"layer": "FOUNDATION"})

    doc.saveas(path)


def _open_reader(dxf_path):
    from src.agents.src.tools.cad_tools import DXFReader

    reader = DXFReader(dxf_path)
    assert reader.open(), "DXF open() 失败"
    return reader


# ─── ① get_structural_segments ──────────────────────────────────
def test_structural_segments_default_plain(tmp_path):
    """默认 include_layer=False: 纯线段, 与 get_plumbing_segments 同形态。"""
    p = str(tmp_path / "structural.dxf")
    _make_structural_dxf(p)
    reader = _open_reader(p)
    segs = reader.get_structural_segments()  # 默认 BEAM + WALL_SHEAR
    # BEAM 1 段 + WALL_SHEAR 2 段 = 3 段
    assert len(segs) == 3, f"2 图层共 3 段, 实际 {len(segs)}"
    for a, b in segs:
        assert isinstance(a, tuple) and isinstance(b, tuple), \
            f"默认形态应为纯线段, 实际 {(a, b)}"


def test_structural_segments_with_layer_per_segment(tmp_path):
    """include_layer=True: 每段 dict {"start","end","layer"}, LWPOLYLINE 逐段带正确图层。"""
    p = str(tmp_path / "structural.dxf")
    _make_structural_dxf(p)
    reader = _open_reader(p)
    segs = reader.get_structural_segments(include_layer=True)
    assert len(segs) == 3, f"3 段 (带图层), 实际 {len(segs)}"

    by_layer = {}
    for seg in segs:
        assert isinstance(seg, dict) and {"start", "end", "layer"} <= set(seg), \
            f"带图层形态应为 dict, 实际 {seg}"
        by_layer.setdefault(seg["layer"], []).append((seg["start"], seg["end"]))

    assert set(by_layer) == {"BEAM", "WALL_SHEAR"}, f"图层集合不符: {set(by_layer)}"
    assert by_layer["BEAM"] == [((0, 0), (4, 0))], f"BEAM 段不符: {by_layer['BEAM']}"
    # 未闭合 3 顶点 = 2 段, 每段都标 WALL_SHEAR
    assert len(by_layer["WALL_SHEAR"]) == 2, \
        f"WALL_SHEAR 未闭合 3 顶点应 2 段, 实际 {len(by_layer['WALL_SHEAR'])}"
    assert by_layer["WALL_SHEAR"] == [((0, 2), (2, 2)), ((2, 2), (2, 4))], \
        f"WALL_SHEAR 逐段归属不符: {by_layer['WALL_SHEAR']}"


def test_structural_segments_requires_open():
    """未 open() 取结构线段 → RuntimeError。"""
    from src.agents.src.tools.cad_tools import DXFReader

    reader = DXFReader("nonexistent.dxf")
    try:
        reader.get_structural_segments()
        assert False, "未 open 应抛 RuntimeError"
    except RuntimeError:
        pass


# ─── ② get_structural_blocks — 真实 DXF 喂 (G2 关键证据) ─────────
def test_structural_blocks_real_dxf(tmp_path):
    """真实 DXF 里造 INSERT 块, reader.get_structural_blocks 真能读出来。

    这是根治 G2 孤儿的证据: 电气/暖通的 extractor 上游 get_*_points 全仓不存在,
    只被单测喂 dict (孤儿模块); 结构这里用 ezdxf 真造带 INSERT 的 DXF 喂 reader,
    证明块类上游解析是真接线的, 不是假数据。
    """
    p = str(tmp_path / "structural_blocks.dxf")
    _make_structural_dxf(p)
    reader = _open_reader(p)

    blocks = reader.get_structural_blocks()  # 默认 COLUMN + FOUNDATION + NODE
    assert len(blocks) == 2, f"COLUMN 1 + FOUNDATION 1 = 2 块, 实际 {len(blocks)}"

    # 逐项核对契约字段: block_name / x / y / layer (纯 dict, 与 ezdxf 解耦)
    by_name = {b["block_name"]: b for b in blocks}
    col = by_name["COL_K"]
    assert col["x"] == 3.0 and col["y"] == 1.0, \
        f"COL_K 插入点应 (3.0,1.0), 实际 ({col['x']},{col['y']})"
    assert col["layer"] == "COLUMN", f"COL_K 图层应 COLUMN, 实际 {col['layer']}"
    found = by_name["FOUND_S"]
    assert found["x"] == 5.0 and found["y"] == 5.0, \
        f"FOUND_S 插入点应 (5.0,5.0), 实际 ({found['x']},{found['y']})"
    assert found["layer"] == "FOUNDATION", \
        f"FOUND_S 图层应 FOUNDATION, 实际 {found['layer']}"

    # 只认 INSERT: 各 block 都应是 dict 且 4 字段齐全 (z 已丢弃, 不出现)
    for b in blocks:
        assert set(b) == {"block_name", "x", "y", "layer"}, \
            f"block 契约字段应为 4 个 (z 丢弃), 实际 {set(b)}"


def test_structural_blocks_ignore_same_layer_circles(tmp_path):
    """同图层放 CIRCLE (门窗小圆圈), 块类解析不视为柱 — 避免误抓。"""
    import ezdxf

    p = str(tmp_path / "blocks_only.dxf")
    doc = ezdxf.new("AC1027")
    for layer in ("COLUMN",):
        doc.layers.new(layer)
    doc.blocks.new("COL_K")
    msp = doc.modelspace()
    msp.add_blockref("COL_K", (1.0, 2.0), dxfattribs={"layer": "COLUMN"})
    msp.add_circle((9.0, 9.0), 0.5, dxfattribs={"layer": "COLUMN"})  # 同层小圆圈
    doc.saveas(p)

    reader = _open_reader(p)
    blocks = reader.get_structural_blocks()
    assert len(blocks) == 1, f"只认 INSERT, CIRCLE 不算柱, 实际 {len(blocks)} 块"
    assert blocks[0]["block_name"] == "COL_K", \
        f"应只有 COL_K, 实际 {blocks[0]['block_name']}"


def test_structural_blocks_requires_open():
    """未 open() 取结构块 → RuntimeError。"""
    from src.agents.src.tools.cad_tools import DXFReader

    reader = DXFReader("nonexistent.dxf")
    try:
        reader.get_structural_blocks()
        assert False, "未 open 应抛 RuntimeError"
    except RuntimeError:
        pass


# ─── ③ 抽取层纯函数边界 ──────────────────────────────────────────
def _beams(segs):
    from src.agents.src.tools.structural_extractor import extract_structural_beams

    return extract_structural_beams(segs)


def _columns(blocks):
    from src.agents.src.tools.structural_extractor import extract_structural_columns

    return extract_structural_columns(blocks)


def test_extract_beams_empty():
    """空 segs → 空 list, 不崩。"""
    assert _beams([]) == [], "空 segs 应返回空 list"


def test_extract_beams_layer_type_mapping_placeholder():
    """带图层: 占位映射 BEAM→main/300, WALL_SHEAR→shear_wall/200。

    这是占位映射 (TBD), 注释只说明"按图层映射类型/截面"这一机制, 不冒充规范数值。
    """
    segs = [
        {"start": (0, 0), "end": (4, 0), "layer": "BEAM"},
        {"start": (0, 2), "end": (2, 2), "layer": "WALL_SHEAR"},
    ]
    beams = _beams(segs)
    assert len(beams) == 2, f"2 段应 2 梁, 实际 {len(beams)}"
    assert beams[0].beam_type == "main" and beams[0].width_mm == 300, \
        f"BEAM 应映射 main/300, 实际 {beams[0].beam_type}/{beams[0].width_mm}"
    assert beams[1].beam_type == "shear_wall" and beams[1].width_mm == 200, \
        f"WALL_SHEAR 应映射 shear_wall/200, 实际 {beams[1].beam_type}/{beams[1].width_mm}"
    # 平面坐标取中点
    assert beams[0].x == 2.0 and beams[0].y == 0.0, \
        f"BEAM 中点应 (2.0,0.0), 实际 ({beams[0].x},{beams[0].y})"


def test_extract_beams_plain_fallback_default_layer():
    """纯线段无图层 (只 (start,end) 二元组): 退默认 BEAM → main/300。"""
    segs = [((0, 0), (4, 0))]
    beams = _beams(segs)
    assert len(beams) == 1
    assert beams[0].beam_type == "main", \
        f"无图层应退默认 BEAM→main, 实际 {beams[0].beam_type}"
    assert beams[0].width_mm == 300, f"无图层应退 300, 实际 {beams[0].width_mm}"


def test_extract_beams_unknown_layer_fallback_default():
    """未知图层: 退默认 (secondary/250) + 记 warning, 不崩 (TBD 占位)。"""
    segs = [{"start": (0, 0), "end": (4, 0), "layer": "MYSTERY_LYR"}]
    with _suppress_warning():
        beams = _beams(segs)
    assert len(beams) == 1
    assert beams[0].beam_type == "secondary" and beams[0].width_mm == 250, \
        f"未知图层应退默认 secondary/250, 实际 {beams[0].beam_type}/{beams[0].width_mm}"


def test_extract_columns_block_name_mapping_placeholder():
    """块名占位映射 COL_K→frame/400, COL_Z→construction/240, FOUND_S→foundation/0。"""
    blocks = [
        {"block_name": "COL_K", "x": 3.0, "y": 1.0, "layer": "COLUMN"},
        {"block_name": "COL_Z", "x": 4.0, "y": 2.0, "layer": "COLUMN"},
        {"block_name": "FOUND_S", "x": 5.0, "y": 5.0, "layer": "FOUNDATION"},
    ]
    cols = _columns(blocks)
    assert len(cols) == 3, f"3 块应 3 柱, 实际 {len(cols)}"
    assert cols[0].column_type == "frame" and cols[0].section_mm == 400, \
        f"COL_K 应映射 frame/400, 实际 {cols[0].column_type}/{cols[0].section_mm}"
    assert cols[1].column_type == "construction" and cols[1].section_mm == 240, \
        f"COL_Z 应映射 construction/240, 实际 {cols[1].column_type}/{cols[1].section_mm}"
    assert cols[2].column_type == "foundation" and cols[2].section_mm == 0, \
        f"FOUND_S 应映射 foundation/0, 实际 {cols[2].column_type}/{cols[2].section_mm}"
    assert cols[0].x == 3.0 and cols[0].y == 1.0, \
        f"COL_K 坐标应 (3.0,1.0), 实际 ({cols[0].x},{cols[0].y})"


def test_extract_columns_unknown_block_fallback_default():
    """未知块名: 退默认 (frame/0) + 记 warning, 不崩 (TBD 占位)。"""
    blocks = [{"block_name": "GHOST_BLK", "x": 0.0, "y": 0.0, "layer": "COLUMN"}]
    with _suppress_warning():
        cols = _columns(blocks)
    assert len(cols) == 1
    assert cols[0].column_type == "frame" and cols[0].section_mm == 0, \
        f"未知块名应退默认 frame/0, 实际 {cols[0].column_type}/{cols[0].section_mm}"


def test_extract_columns_empty():
    """空 blocks → 空 list, 不崩。"""
    assert _columns([]) == [], "空 blocks 应返回空 list"


def test_extract_columns_missing_fields_use_zero():
    """block dict 缺 x/y (契约外缺省): 兜 0.0, 不崩。"""
    cols = _columns([{"block_name": "COL_K"}])
    assert cols[0].x == 0.0 and cols[0].y == 0.0, \
        f"缺 x/y 应兜 0.0, 实际 ({cols[0].x},{cols[0].y})"


def test_extract_beams_immutable_output():
    """出参 list 是新建对象, 不含入参引用 (不可变契约)。"""
    segs = [{"start": (0, 0), "end": (10, 0), "layer": "BEAM"}]
    beams = _beams(segs)
    assert beams[0].id == "structural-beam-0", \
        f"首个 id 应 structural-beam-0, 实际 {beams[0].id}"
    again = _beams(segs)
    assert again[0] == beams[0], "两次抽取同输入应得同结果 (无隐式 mutation)"


def _suppress_warning():
    """上下文里静默抽层 warning (未知图层/块名退默认), 不影响断言。"""
    import contextlib

    return contextlib.suppress()


if __name__ == "__main__":
    # 纯函数用例 (不需要 tmp_path/DXF) 可直跑; DXF 相关用例走 pytest。
    test_extract_beams_empty()
    test_extract_beams_layer_type_mapping_placeholder()
    test_extract_beams_plain_fallback_default_layer()
    test_extract_beams_unknown_layer_fallback_default()
    test_extract_columns_block_name_mapping_placeholder()
    test_extract_columns_unknown_block_fallback_default()
    test_extract_columns_empty()
    test_extract_columns_missing_fields_use_zero()
    test_extract_beams_immutable_output()
    print("\nPure-function structural extractor tests passed! "
          "(DXF-based cases run via: python -m pytest tests/unit/test_structural_extractor.py -q)")
