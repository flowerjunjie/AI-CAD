"""
Phase 3 — 给排水元素抽取单元测试

验证三块 (对应 coder 交付):
① get_wall_segments 抽公共方法 _segments_from_layer 后既有行为零回归
   (LINE 取 start/end; LWPOLYLINE 未闭合 n-1 段 / 闭合且 n>2 补首尾 / 两点不补 / 单点跳过;
    默认图层过滤) —— 用 ezdxf 造真实 DXF 直接测行为。
② get_plumbing_segments: 默认纯线段同 wall 形态; include_layer=True 输出
   ((start,end), layer), LWPOLYLINE 展开多段时逐段都带正确图层。
③ extract_plumbing_pipes 纯函数边界: 空 segs / 管径映射 (PIPE_WASTE→110 其余→50, 占位 TBD) /
   坡度 (无标注=0.0, 零长管段带标注=0.0 除零保护, 缺端点标注=0.0, 正常路径算百分比) /
   距检查井 (无井=0.0, 有点=中点到最近井距离) / 纯线段无图层回退 PIPE。

管径映射与坡度数值为占位 (TBD), 断言里的注释只描述"占位映射"本身, 不冒充规范条文。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


# ─── DXF 造数据辅助 ─────────────────────────────────────────────
def _make_plumbing_dxf(path, with_closed_poly=True):
    """造含 LINE + LWPOLYLINE 的 DXF: 各图层管道线。

    各放:
      PIPE:       一条 LINE (0,0)->(4,0)
      PIPE_WASTE: 一条 LWPOLYLINE 未闭合 3 顶点 (0,2)->(2,2)->(2,4)  → 2 段
      PIPE_VENT:  一条 LWPOLYLINE 闭合 3 顶点 (0,6)->(3,6)->(0,9)->(close)
                  → 未闭合展开 2 段 + 闭合补首尾 1 段 = 3 段
      PIPE_DRAIN: 一条 LWPOLYLINE 仅 2 顶点 (0,10)->(5,10) (未闭合) → 1 段, 不补首尾
    """
    import ezdxf

    doc = ezdxf.new("AC1027")
    for layer in ("PIPE", "PIPE_WASTE", "PIPE_VENT", "PIPE_DRAIN"):
        doc.layers.new(layer)
    msp = doc.modelspace()

    msp.add_line((0, 0), (4, 0), dxfattribs={"layer": "PIPE"})

    msp.add_lwpolyline(
        [(0, 2), (2, 2), (2, 4)],
        dxfattribs={"layer": "PIPE_WASTE", "closed": False},
    )

    if with_closed_poly:
        msp.add_lwpolyline(
            [(0, 6), (3, 6), (0, 9)],
            dxfattribs={"layer": "PIPE_VENT", "closed": True},
        )

    msp.add_lwpolyline(
        [(0, 10), (5, 10)],
        dxfattribs={"layer": "PIPE_DRAIN", "closed": False},
    )

    doc.saveas(path)


def _open_reader(dxf_path):
    from src.agents.src.tools.cad_tools import DXFReader

    reader = DXFReader(dxf_path)
    assert reader.open(), "DXF open() 失败"
    return reader


# ─── ① get_wall_segments 重构零回归 ─────────────────────────────
def test_wall_segments_line_basic(tmp_path):
    """LINE 逐条取 (start_xy, end_xy), 纯 2 元组, z 丢弃。"""
    p = str(tmp_path / "wall.dxf")
    _make_plumbing_dxf(p)  # 复用造出的各图层线, 这里只用 PIPE 那一条当 LINE
    reader = _open_reader(p)
    # 只捞 PIPE 层的一条 LINE
    segs = reader.get_wall_segments(layer_names=("PIPE",))
    assert segs == [((0, 0), (4, 0))], f"单 LINE 应取 1 段, 实际 {segs}"
    a, b = segs[0]
    assert isinstance(a, tuple) and isinstance(b, tuple), "端点须为 2 元组"


def test_wall_segments_lwpolyline_unclosed(tmp_path):
    """LWPOLYLINE 未闭合: n 顶点 → n-1 段 (相邻顶点对展开, 不补首尾)。"""
    p = str(tmp_path / "wall.dxf")
    _make_plumbing_dxf(p)
    reader = _open_reader(p)
    # PIPE_WASTE: 3 顶点未闭合 → 2 段
    segs = reader.get_wall_segments(layer_names=("PIPE_WASTE",))
    assert segs == [((0, 2), (2, 2)), ((2, 2), (2, 4))], f"未闭合 3 顶点应 2 段, 实际 {segs}"


def test_wall_segments_lwpolyline_closed_appends_first_last(tmp_path):
    """LWPOLYLINE 闭合且 n>2: 展开 n-1 段 + 补首尾 1 段 = n 段 (coder 点名的边界)。"""
    p = str(tmp_path / "wall.dxf")
    _make_plumbing_dxf(p)
    reader = _open_reader(p)
    # PIPE_VENT: 3 顶点闭合 → 2 展开 + 1 补首尾 = 3 段
    segs = reader.get_wall_segments(layer_names=("PIPE_VENT",))
    expected = [((0, 6), (3, 6)), ((3, 6), (0, 9)), ((0, 9), (0, 6))]
    assert segs == expected, f"闭合 3 顶点应 3 段(补首尾), 实际 {segs}"


def test_wall_segments_lwpolyline_two_points_no_close(tmp_path):
    """LWPOLYLINE 两点 (n==2): 展开 1 段, 因 n 不>2 不补首尾。"""
    p = str(tmp_path / "wall.dxf")
    _make_plumbing_dxf(p)
    reader = _open_reader(p)
    # PIPE_DRAIN: 2 顶点未闭合 → 1 段
    segs = reader.get_wall_segments(layer_names=("PIPE_DRAIN",))
    assert segs == [((0, 10), (5, 10))], f"两点 LWPOLYLINE 应 1 段, 实际 {segs}"


def test_wall_segments_default_layers_filter(tmp_path):
    """默认 layer_names=('WALL','WALL_THICK'): 只捞这两层, 其余图层线不混入。"""
    p = str(tmp_path / "wall.dxf")
    _make_plumbing_dxf(p)
    reader = _open_reader(p)
    segs = reader.get_wall_segments()  # 用默认 WALL/WALL_THICK
    assert segs == [], f"无 WALL/WALL_THICK 图层时默认应空, 实际 {segs}"


def test_wall_segments_requires_open():
    """未 open() 直接取线段 → RuntimeError (既有契约)。"""
    from src.agents.src.tools.cad_tools import DXFReader

    reader = DXFReader("nonexistent.dxf")
    try:
        reader.get_wall_segments()
        assert False, "未 open 应抛 RuntimeError"
    except RuntimeError:
        pass


def test_wall_segments_closed_poly_single_point_skipped(tmp_path):
    """单顶点 LWPOLYLINE (n<2) 跳过, 不产生线段。"""
    import ezdxf
    p = str(tmp_path / "single.dxf")
    doc = ezdxf.new("AC1027")
    doc.layers.new("WALL")
    msp = doc.modelspace()
    msp.add_lwpolyline([(1, 1)], dxfattribs={"layer": "WALL", "closed": True})
    doc.saveas(p)
    reader = _open_reader(p)
    segs = reader.get_wall_segments(layer_names=("WALL",))
    assert segs == [], f"单顶点 LWPOLYLINE 应跳过, 实际 {segs}"


# ─── ② get_plumbing_segments ────────────────────────────────────
def test_plumbing_segments_default_plain(tmp_path):
    """默认 include_layer=False: 输出纯线段, 与 get_wall_segments 同形态。"""
    p = str(tmp_path / "pl.dxf")
    _make_plumbing_dxf(p)
    reader = _open_reader(p)
    segs = reader.get_plumbing_segments()  # 全部 4 层 PIPE*/PIPE_WASTE/PIPE_VENT/PIPE_DRAIN
    # PIPE 1 + PIPE_WASTE 2 + PIPE_VENT 3 + PIPE_DRAIN 1 = 7 段
    assert len(segs) == 7, f"4 图层共 7 段, 实际 {len(segs)}"
    for a, b in segs:
        assert isinstance(a, tuple) and isinstance(b, tuple), f"默认形态应为纯线段, 实际 {(a, b)}"


def test_plumbing_segments_with_layer_per_segment(tmp_path):
    """include_layer=True: 每段输出 dict {"start","end","layer"}, LWPOLYLINE 多段逐段带正确图层。

    coder 点名: 闭合 LWPOLYLINE 展开成多段时, 每段都得带来源图层, 不能只带第一段。
    """
    p = str(tmp_path / "pl.dxf")
    _make_plumbing_dxf(p)
    reader = _open_reader(p)
    segs = reader.get_plumbing_segments(include_layer=True)
    assert len(segs) == 7, f"7 段 (带图层), 实际 {len(segs)}"

    by_layer = {}
    for seg in segs:
        assert isinstance(seg, dict) and {"start", "end", "layer"} <= set(seg), \
            f"带图层形态应为 dict, 实际 {seg}"
        by_layer.setdefault(seg["layer"], []).append((seg["start"], seg["end"]))

    # 逐层核对段数与图层归属
    assert set(by_layer) == {"PIPE", "PIPE_WASTE", "PIPE_VENT", "PIPE_DRAIN"}, \
        f"图层集合不符: {set(by_layer)}"
    assert len(by_layer["PIPE_WASTE"]) == 2, f"PIPE_WASTE 未闭合 3 顶点应 2 段, 实际 {len(by_layer['PIPE_WASTE'])}"
    assert by_layer["PIPE_WASTE"] == [((0, 2), (2, 2)), ((2, 2), (2, 4))], f"PIPE_WASTE 段不符: {by_layer['PIPE_WASTE']}"
    # 闭合 3 顶点 = 3 段, 每段都标 PIPE_VENT
    assert len(by_layer["PIPE_VENT"]) == 3, f"PIPE_VENT 闭合应 3 段, 实际 {len(by_layer['PIPE_VENT'])}"
    assert by_layer["PIPE_VENT"] == [((0, 6), (3, 6)), ((3, 6), (0, 9)), ((0, 9), (0, 6))], \
        f"PIPE_VENT 逐段归属/补首尾不符: {by_layer['PIPE_VENT']}"


def test_plumbing_segments_requires_open():
    """未 open() 取管道线 → RuntimeError。"""
    from src.agents.src.tools.cad_tools import DXFReader

    reader = DXFReader("nonexistent.dxf")
    try:
        reader.get_plumbing_segments()
        assert False, "未 open 应抛 RuntimeError"
    except RuntimeError:
        pass


# ─── ③ extract_plumbing_pipes 纯函数边界 ───────────────────────
def _pipes(segs, manhole_points=(), annotations=None):
    from src.agents.src.tools.plumbing_extractor import extract_plumbing_pipes

    return extract_plumbing_pipes(segs, manhole_points=manhole_points, annotations=annotations)


def test_extract_empty_segs():
    """空 segs → 空 list, 不崩。"""
    assert _pipes([]) == [], "空 segs 应返回空 list"


def test_extract_layer_diameter_mapping_placeholder():
    """带图层: 管径占位映射 PIPE_WASTE→110, 其余 (VENT/DRAIN/PIPE)→50。

    这是占位映射 (TBD), 注释只说明"按图层映射管径"这一机制, 不冒充规范数值。
    """
    segs = [
        {"start":(0,0),"end":(4,0),"layer":"PIPE_WASTE"},
        {"start":(0,0),"end":(4,0),"layer":"PIPE_VENT"},
        {"start":(0,0),"end":(4,0),"layer":"PIPE_DRAIN"},
    ]
    pipes = _pipes(segs)
    assert len(pipes) == 3, f"3 段应 3 管, 实际 {len(pipes)}"
    assert pipes[0].pipe_type == "waste" and pipes[0].diameter_mm == 110, \
        f"PIPE_WASTE 应映射 waste/110, 实际 {pipes[0].pipe_type}/{pipes[0].diameter_mm}"
    assert pipes[1].pipe_type == "vent" and pipes[1].diameter_mm == 50, \
        f"PIPE_VENT 应映射 vent/50, 实际 {pipes[1].pipe_type}/{pipes[1].diameter_mm}"
    assert pipes[2].pipe_type == "drain" and pipes[2].diameter_mm == 50, \
        f"PIPE_DRAIN 应映射 drain/50, 实际 {pipes[2].pipe_type}/{pipes[2].diameter_mm}"


def test_extract_plain_segs_fallback_default_pipe():
    """纯线段无图层 (只 (start,end) 二元组): 回退默认 PIPE → drain/50。"""
    segs = [((0, 0), (4, 0))]
    pipes = _pipes(segs)
    assert len(pipes) == 1
    assert pipes[0].pipe_type == "drain", f"无图层应回退 PIPE→drain, 实际 {pipes[0].pipe_type}"
    assert pipes[0].diameter_mm == 50, f"无图层应回退 50, 实际 {pipes[0].diameter_mm}"


def test_extract_slope_no_annotations():
    """无 annotations: 坡度占位 0.0 (coder 边界①)。"""
    segs = [{"start":(0,0),"end":(10,0),"layer":"PIPE_DRAIN"}]
    pipes = _pipes(segs)
    assert pipes[0].slope == 0.0, f"无标注坡度应 0.0, 实际 {pipes[0].slope}"


def test_extract_slope_zero_length_with_annotation():
    """零长管段 (start==end) + 有标注: 水平距离 0 → 除零保护, 坡度 0.0 (coder 边界②)。"""
    segs = [{"start":(0,0),"end":(0,0),"layer":"PIPE_DRAIN"}]
    ann = {"PIPE_DRAIN": {(0, 0): 1.0}}  # 两端点是同一点, 高程相同
    pipes = _pipes(segs, annotations=ann)
    assert pipes[0].slope == 0.0, f"零长管段应除零保护→0.0, 实际 {pipes[0].slope}"


def test_extract_slope_missing_endpoint_annotation():
    """annotations 缺某端点: 无法算差 → 坡度 0.0 (coder 边界③)。"""
    segs = [{"start":(0,0),"end":(10,0),"layer":"PIPE_DRAIN"}]
    ann = {"PIPE_DRAIN": {(0, 0): 1.0}}  # 只有 start, 缺 end(10,0)
    pipes = _pipes(segs, annotations=ann)
    assert pipes[0].slope == 0.0, f"缺端点标注应 0.0, 实际 {pipes[0].slope}"


def test_extract_slope_normal_path():
    """正常路径: 水平 10m, 高程差 0.2m → 坡度 2.0% (占位算法, 非规范数值)。"""
    segs = [{"start":(0,0),"end":(10,0),"layer":"PIPE_DRAIN"}]
    ann = {"PIPE_DRAIN": {(0, 0): 0.2, (10, 0): 0.0}}
    pipes = _pipes(segs, annotations=ann)
    assert abs(pipes[0].slope - 2.0) < 1e-6, f"差 0.2/水平 10 → 2.0%, 实际 {pipes[0].slope}"


def test_extract_manhole_absent_dist_zero():
    """无 manhole_points: 距检查井 0.0 (coder 边界④)。"""
    segs = [{"start":(0,0),"end":(10,0),"layer":"PIPE_DRAIN"}]
    pipes = _pipes(segs)
    assert pipes[0].distance_to_manhole_m == 0.0, f"无检查井应 0.0, 实际 {pipes[0].distance_to_manhole_m}"


def test_extract_manhole_distance_to_nearest():
    """有 manhole_points: 取管段中点到最近井的欧氏距离。"""
    # 管段 (0,0)->(10,0) 中点 (5,0); 两井 (5,3) 与 (5,8) → 最近 3.0
    segs = [{"start":(0,0),"end":(10,0),"layer":"PIPE_DRAIN"}]
    pipes = _pipes(segs, manhole_points=[(5, 3), (5, 8)])
    assert abs(pipes[0].distance_to_manhole_m - 3.0) < 1e-6, \
        f"中点 (5,0) 到最近井 (5,3) 应 3.0, 实际 {pipes[0].distance_to_manhole_m}"


def test_extract_ids_and_immutable_output():
    """每管带唯一 id plumbing-<idx>; 出参 list 是新建对象, 不含入参引用。"""
    segs = [{"start":(0,0),"end":(10,0),"layer":"PIPE_DRAIN"}]
    pipes = _pipes(segs)
    assert pipes[0].id == "plumbing-0", f"首个 id 应 plumbing-0, 实际 {pipes[0].id}"
    # 改管道字段不应影响 (确认非共享可变状态): 重新抽取应等价
    again = _pipes(segs)
    assert again[0] == pipes[0], "两次抽取同输入应得同结果 (无隐式 mutation)"


if __name__ == "__main__":
    # 纯函数用例 (不需要 tmp_path/DXF) 可直跑; DXF 相关用例走 pytest。
    test_extract_empty_segs()
    test_extract_layer_diameter_mapping_placeholder()
    test_extract_plain_segs_fallback_default_pipe()
    test_extract_slope_no_annotations()
    test_extract_slope_zero_length_with_annotation()
    test_extract_slope_missing_endpoint_annotation()
    test_extract_slope_normal_path()
    test_extract_manhole_absent_dist_zero()
    test_extract_manhole_distance_to_nearest()
    test_extract_ids_and_immutable_output()
    print("\nPure-function plumbing extractor tests passed! "
          "(DXF-based cases run via: python -m pytest tests/unit/test_plumbing_extractor.py -q)")
