"""
单元测试 — 结构梁/柱出图 (Structural Beam/Column DWG Export)
验证: DXFWriter.add_beam / add_column 在 BEAM/COLUMN 图层画实体 + 截面标注,
      cad_execute_node 的 beam/column task_type 分支消费 raw_data 的 structural 元素。
仿 test_pipe_dwg_export.py (出图实体断言 + ezdxf 读回查) + test_wall_thickness.py。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

# 与样本 structural_beams 键坐标一致 (2 根梁: 水平2 根)
_BEAMS = [
    {"id": "sb1", "layer": "BEAM", "start": [0.0, 0.0], "end": [4.0, 0.0],
     "width_mm": 300, "depth_mm": 600},
    {"id": "sb2", "layer": "BEAM", "start": [0.0, 4.0], "end": [4.0, 4.0],
     "width_mm": 250, "depth_mm": 500},
]
# 与样本 structural_columns 键坐标一致 (3 根柱: 2 框架 + 1 构造)
_COLUMNS = [
    {"id": "sc1", "layer": "COLUMN", "x": 0.0, "y": 4.0, "section_mm": 400},
    {"id": "sc2", "layer": "COLUMN", "x": 4.0, "y": 4.0, "section_mm": 400},
    {"id": "sc3", "layer": "COLUMN", "x": 0.0, "y": 0.0, "section_mm": 200},
]


def test_add_beam_creates_lwpolyline_on_beam_layer():
    """add_beam: BEAM 图层 LWPOLYLINE (两点) + BEAM_LABEL 层 "300x600" 截面标注。"""
    from src.agents.src.tools.cad_tools import DXFWriter, Beam, Point

    writer = DXFWriter()
    writer.new("AC1027")
    n = writer.add_beam(Beam(start=Point(0.0, 0.0), end=Point(4.0, 0.0),
                             width_mm=300, depth_mm=600))
    assert n == 1, f"add_beam 应返回 1 条标注, 实际 {n}"

    doc = writer.doc
    msp = doc.modelspace()
    lwps = list(msp.query('LWPOLYLINE[layer=="BEAM"]'))
    assert len(lwps) == 1, f"BEAM 图层应有 1 条 LWPOLYLINE, 实际 {len(lwps)}"
    with lwps[0].points(format="xy") as pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
    assert abs(max(xs) - min(xs) - 4.0) < 1e-6, "水平梁 x 跨度应=4.0"
    assert max(ys) == min(ys) == 0.0, "水平梁 y 应恒=0.0"

    texts = [t.dxf.text for t in msp.query('TEXT[layer=="BEAM_LABEL"]')]
    assert "300x600" in texts, f"梁截面标注 '300x600' 未画, 实际 {texts}"


def test_add_column_creates_square_on_column_layer():
    """add_column: COLUMN 图层闭合正方形 LWPOLYLINE + COLUMN_LABEL 层 "400x400"。"""
    from src.agents.src.tools.cad_tools import DXFWriter, Column, Point

    writer = DXFWriter()
    writer.new("AC1027")
    n = writer.add_column(Column(position=Point(0.0, 4.0), section_mm=400))
    assert n == 1, f"add_column 应返回 1 条标注, 实际 {n}"

    doc = writer.doc
    msp = doc.modelspace()
    # 闭合正方形: 4 顶点 + 首尾闭合 (closed LWPOLYLINE 展开后第 4 段补齐)
    closed = list(msp.query('LWPOLYLINE[layer=="COLUMN"]'))
    assert len(closed) == 1, f"COLUMN 图层应有 1 条闭合 LWPOLYLINE, 实际 {len(closed)}"
    with closed[0].points(format="xy") as pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
    side = 400 / 1000.0
    assert abs((max(xs) - min(xs)) - side) < 1e-6, "柱正方形 x 边长应=0.4"
    assert abs((max(ys) - min(ys)) - side) < 1e-6, "柱正方形 y 边长应=0.4"
    # 柱心 (0.0, 4.0): 左下顶角 = (-0.2, 3.8)
    assert min(xs) == -0.2 and min(ys) == 3.8, "正方形左下顶角应 = (x-half, y-half)"

    texts = [t.dxf.text for t in msp.query('TEXT[layer=="COLUMN_LABEL"]')]
    assert "400x400" in texts, f"柱截面标注 '400x400' 未画, 实际 {texts}"


def test_cad_execute_beam_column_tasks_write_entities():
    """cad_execute_node beam/column task_type: 消费 raw_data structural 元素 →
    DWG 有 BEAM/COLUMN 图层实体 + 截面标注。ezdxf 读回查 (仿 pipe 范式)。"""
    import ezdxf
    from src.agents.src.nodes.cad_rule_export import cad_execute_node
    from src.agents.src.nodes.input_parser import parse_json_input

    sample = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    parsed = parse_json_input(sample)
    state = {
        "raw_data": parsed["raw_data"],
        "project_structure": parsed["project_structure"],
        "task_list": parsed["task_list"],
        "output_path": "/tmp/aicad_structural_test.dwg",
        "auto_mode": True,
    }
    result = cad_execute_node(state)
    assert result.get("final_dwg_path"), "DWG 应生成"

    beam_tasks = [r for r in result["cad_results"] if r["task_id"] == "beam-structural"]
    col_tasks = [r for r in result["cad_results"] if r["task_id"] == "column-structural"]
    assert beam_tasks, "task_list 应含 beam-structural 任务"
    assert col_tasks, "task_list 应含 column-structural 任务"
    assert beam_tasks[0]["status"] == "completed", f"beam 任务应 completed, 实际 {beam_tasks[0]}"
    assert col_tasks[0]["status"] == "completed", f"column 任务应 completed, 实际 {col_tasks[0]}"
    assert beam_tasks[0].get("count") == 2, f"样本 2 根梁应画 2 条, 实际 {beam_tasks[0].get('count')}"
    assert col_tasks[0].get("count") == 3, f"样本 3 根柱应画 3 条, 实际 {col_tasks[0].get('count')}"

    doc = ezdxf.readfile(result["final_dwg_path"])
    msp = doc.modelspace()
    beam_lwps = list(msp.query('LWPOLYLINE[layer=="BEAM"]'))
    col_lwps = list(msp.query('LWPOLYLINE[layer=="COLUMN"]'))
    assert len(beam_lwps) == 2, f"BEAM 图层应 2 条 LWPOLYLINE, 实际 {len(beam_lwps)}"
    assert len(col_lwps) == 3, f"COLUMN 图层应 3 条 LWPOLYLINE, 实际 {len(col_lwps)}"

    beam_texts = [t.dxf.text for t in msp.query('TEXT[layer=="BEAM_LABEL"]')]
    col_texts = [t.dxf.text for t in msp.query('TEXT[layer=="COLUMN_LABEL"]')]
    assert "300x600" in beam_texts and "250x500" in beam_texts, \
        f"梁截面标注缺失, 实际 {beam_texts}"
    assert col_texts.count("400x400") == 2, f"400x400 柱标注应 2 条, 实际 {col_texts}"
    assert col_texts.count("200x200") == 1, f"200x200 柱标注应 1 条, 实际 {col_texts}"


def test_input_parser_emits_beam_column_tasks():
    """parse_json_input: 样本带 structural_beams/columns 键即生成 task;
    缺 keys 时零改动回归安全 (仿 pipe 分支)。"""
    import json
    import tempfile
    from src.agents.src.nodes.input_parser import parse_json_input

    sample = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    parsed = parse_json_input(sample)
    beam_tasks = [t for t in parsed["task_list"] if t["type"] == "beam"]
    col_tasks = [t for t in parsed["task_list"] if t["type"] == "column"]
    assert len(beam_tasks) == 1, f"样本 structural_beams 应生成 1 个 beam task, 实际 {len(beam_tasks)}"
    assert len(col_tasks) == 1, f"样本 structural_columns 应生成 1 个 column task, 实际 {len(col_tasks)}"
    assert beam_tasks[0]["id"] == "beam-structural", "beam task id 应为 beam-structural"
    assert col_tasks[0]["id"] == "column-structural", "column task id 应为 column-structural"

    # 缺 structural 键的样本 (回归安全): 不生成 beam/column task
    with open(sample, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.pop("structural_beams", None)
    data.pop("structural_columns", None)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                     encoding="utf-8") as tf:
        json.dump(data, tf, ensure_ascii=False)
        tmp_path = tf.name
    parsed2 = parse_json_input(tmp_path)
    assert not [t for t in parsed2["task_list"] if t["type"] in ("beam", "column")], \
        "缺 structural 键不应生成 beam/column task (回归安全)"
    os.unlink(tmp_path)


def test_structure_design_passes_beam_column_counts():
    """structure_design_node 重建 task_list 时透传 structural 计数 (已知坑, 照 pipe 修法):
    LLM 主导路径 (不注入 sample task_list) 也会出 beam/column task。"""
    from src.agents.src.nodes.intent_structure import structure_design_node

    sample = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    state = {
        "project_type": "住宅",
        "disciplines": ["建筑", "结构"],
        "raw_data": {"structural_beams": _BEAMS, "structural_columns": _COLUMNS},
        "project_structure": {"zones": [], "floors": 1},
    }
    result = structure_design_node(state)
    structure = result["project_structure"]
    assert structure.get("beam_count") == 2, \
        f"beam_count 应透传 2, 实际 {structure.get('beam_count')}"
    assert structure.get("column_count") == 3, \
        f"column_count 应透传 3, 实际 {structure.get('column_count')}"
    # 重建出的 task_list 必须含 beam/column task (否则被 structure_design_node 抹掉)
    types = [t["type"] for t in result["task_list"]]
    assert "beam" in types, f"重建 task_list 缺 beam task: {types}"
    assert "column" in types, f"重建 task_list 缺 column task: {types}"


def test_add_column_hatch_creates_column_fill():
    """add_column(hatch=True): COLUMN_FILL 图层出 1 条实填充 HATCH (4 顶点=柱本体 4 角),
    且不破坏既有柱本体 LWPOLYLINE / COLUMN_LABEL (回归红线: hatch 是纯增量)。"""
    from src.agents.src.tools.cad_tools import DXFWriter, Column, Point

    writer = DXFWriter()
    writer.new("AC1027")
    n = writer.add_column(Column(position=Point(0.0, 4.0), section_mm=400), hatch=True)
    assert n == 1, f"add_column(hatch=True) 仍返回 1 条标注, 实际 {n}"

    msp = writer.doc.modelspace()
    # 柱本体不受影响: COLUMN 层仍 1 条 LWPOLYLINE
    assert len(list(msp.query('LWPOLYLINE[layer=="COLUMN"]'))) == 1
    # COLUMN_FILL 层出 1 条 HATCH (新增的填充, 与 add_beam hatch 同口径)
    hatches = list(msp.query('HATCH[layer=="COLUMN_FILL"]'))
    assert len(hatches) == 1, f"COLUMN_FILL 层应有 1 条 HATCH, 实际 {len(hatches)}"
    # HATCH 有 1 条闭合 path (填充区域 = 柱截面)
    h = hatches[0]
    assert len(h.paths) == 1, "柱填充应有 1 条 path"


def test_add_column_hatch_default_off_and_idempotent():
    """hatch 默认 False 不出填充 (既有行为不变); 多次 hatch=True 幂等不炸 (纯增量)。"""
    from src.agents.src.tools.cad_tools import DXFWriter, Column, Point

    writer = DXFWriter()
    writer.new("AC1027")
    # 默认 hatch=False: 无 COLUMN_FILL 实体 (既有行为不变)
    writer.add_column(Column(position=Point(0.0, 4.0), section_mm=400))
    assert len(list(writer.doc.modelspace().query('HATCH[layer=="COLUMN_FILL"]'))) == 0, \
        "默认 hatch=False 不应出 COLUMN_FILL 填充 (既有行为不变)"
    # hatch=True: 出填充; 再调一次同位置不炸 (幂等纯增量)
    writer.add_column(Column(position=Point(0.0, 4.0), section_mm=400), hatch=True)
    assert len(list(writer.doc.modelspace().query('HATCH[layer=="COLUMN_FILL"]'))) == 1


if __name__ == "__main__":
    test_add_beam_creates_lwpolyline_on_beam_layer()
    test_add_column_creates_square_on_column_layer()
    test_cad_execute_beam_column_tasks_write_entities()
    test_input_parser_emits_beam_column_tasks()
    test_structure_design_passes_beam_column_counts()
    test_add_column_hatch_creates_column_fill()
    test_add_column_hatch_default_off_and_idempotent()
    # ASCII print — Windows GBK 终端不能 print emoji (直跑护栏见 test_direct_run.py)
    print("OK: all structural DWG export tests passed")
