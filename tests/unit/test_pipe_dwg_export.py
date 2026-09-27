"""
单元测试 — 给排水管出图 (Pipe DWG Export)
验证: DXFWriter.add_pipe 在 PIPE 图层画 LWPOLYLINE 双线 + 管径标注,
      cad_execute_node 的 pipe task_type 分支消费 raw_data 的 pipes 线段。
仿 test_wall_thickness.py (出图实体断言) + test_plumbing_e2e.py (ezdxf 读回查)。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

# 与样本 pipes 键坐标一致 (3 段: 水平2 + 竖直1)
_PIPES = [
    {"id": "p1", "layer": "PIPE", "start": [2.5, 2.5], "end": [6.0, 2.5], "diameter_mm": 50},
    {"id": "p2", "layer": "PIPE", "start": [0.8, 1.0], "end": [0.8, 3.0], "diameter_mm": 50},
    {"id": "p3", "layer": "PIPE_WASTE", "start": [3.0, 2.5], "end": [3.0, 4.0], "diameter_mm": 110},
]


def test_add_pipe_creates_lwpolyline_on_pipe_layer():
    """add_pipe: PIPE 图层 LWPOLYLINE (两点) + PIPE_LABEL 层管径标注 TEXT。"""
    from src.agents.src.tools.cad_tools import DXFWriter, Pipe, Point

    writer = DXFWriter()
    writer.new("AC1027")
    n = writer.add_pipe(Pipe(start=Point(2.5, 2.5), end=Point(6.0, 2.5), diameter_mm=50))
    assert n == 1, f"add_pipe 应返回 1 条标注, 实际 {n}"

    doc = writer.doc
    msp = doc.modelspace()
    # PIPE 图层 LWPOLYLINE: 两点不闭合
    lwps = list(msp.query('LWPOLYLINE[layer=="PIPE"]'))
    assert len(lwps) == 1, f"PIPE 图层应有 1 条 LWPOLYLINE, 实际 {len(lwps)}"
    with lwps[0].points(format="xy") as pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
    assert abs(max(xs) - min(xs) - 3.5) < 1e-6, "水平管段 x 跨度应=3.5"
    assert max(ys) == min(ys) == 2.5, "水平管段 y 应恒=2.5"

    # 管径标注: PIPE_LABEL 层 TEXT "DN50"
    texts = [t.dxf.text for t in msp.query('TEXT[layer=="PIPE_LABEL"]')]
    assert "DN50" in texts, f"管径标注 'DN50' 未画, 实际 {texts}"


def test_add_pipe_waste_layer_diagonal_label():
    """竖直管 + PIPE_WASTE 图层: LWPOLYLINE 画在指定层, 标注 DN110。"""
    from src.agents.src.tools.cad_tools import DXFWriter, Pipe, Point

    writer = DXFWriter()
    writer.new("AC1027")
    writer.add_pipe(Pipe(start=Point(3.0, 2.5), end=Point(3.0, 4.0),
                         diameter_mm=110, layer="PIPE_WASTE"))
    doc = writer.doc
    msp = doc.modelspace()
    lwps = list(msp.query('LWPOLYLINE[layer=="PIPE_WASTE"]'))
    assert len(lwps) == 1, f"PIPE_WASTE 图层应有 1 条 LWPOLYLINE, 实际 {len(lwps)}"
    with lwps[0].points(format="xy") as pts:
        ys = [p[1] for p in pts]
    assert abs(max(ys) - min(ys) - 1.5) < 1e-6, "竖直管段 y 跨度应=1.5"
    texts = [t.dxf.text for t in msp.query('TEXT[layer=="PIPE_LABEL"]')]
    assert "DN110" in texts, f"管径标注 'DN110' 未画, 实际 {texts}"


def test_cad_execute_pipe_task_writes_pipe_entities():
    """cad_execute_node pipe task_type: 消费 raw_data.pipes → DWG 有 PIPE 图层管线 + 管径标注。
    ezdxf 读回查 (仿 test_plumbing_e2e 读回范式)。"""
    import ezdxf
    from src.agents.src.nodes.cad_rule_export import cad_execute_node
    from src.agents.src.nodes.input_parser import parse_json_input

    sample = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    parsed = parse_json_input(sample)
    state = {
        "raw_data": parsed["raw_data"],
        "project_structure": parsed["project_structure"],
        "task_list": parsed["task_list"],
        "output_path": "/tmp/aicad_pipe_test.dwg",
        "auto_mode": True,
    }
    result = cad_execute_node(state)
    assert result.get("final_dwg_path"), "DWG 应生成"

    # pipe task 结果: 3 段全出图
    pipe_tasks = [r for r in result["cad_results"] if r["task_id"] == "pipe-plumbing"]
    assert pipe_tasks, "task_list 应含 pipe-plumbing 任务"
    assert pipe_tasks[0]["status"] == "completed", f"pipe 任务应 completed, 实际 {pipe_tasks[0]}"
    assert pipe_tasks[0].get("count") == 3, f"样本 3 段管应画 3 条, 实际 {pipe_tasks[0].get('count')}"

    # ezdxf 读回查: PIPE 图层 LWPOLYLINE = 2 段 + PIPE_WASTE = 1 段, 管径标注 3 条
    doc = ezdxf.readfile(result["final_dwg_path"])
    msp = doc.modelspace()
    pipe_lwps = list(msp.query('LWPOLYLINE[layer=="PIPE"]'))
    waste_lwps = list(msp.query('LWPOLYLINE[layer=="PIPE_WASTE"]'))
    assert len(pipe_lwps) == 2, f"PIPE 图层应 2 条 LWPOLYLINE, 实际 {len(pipe_lwps)}"
    assert len(waste_lwps) == 1, f"PIPE_WASTE 图层应 1 条 LWPOLYLINE, 实际 {len(waste_lwps)}"

    texts = [t.dxf.text for t in msp.query('TEXT[layer=="PIPE_LABEL"]')]
    assert texts.count("DN50") == 2, f"DN50 标注应 2 条, 实际 {texts}"
    assert texts.count("DN110") == 1, f"DN110 标注应 1 条, 实际 {texts}"


def test_input_parser_emits_pipe_task():
    """parse_json_input: 样本带 pipes 键即生成 pipe task; 缺 keys 零改动回归安全。"""
    import json
    import tempfile
    from src.agents.src.nodes.input_parser import parse_json_input

    sample = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    parsed = parse_json_input(sample)
    pipe_tasks = [t for t in parsed["task_list"] if t["type"] == "pipe"]
    assert len(pipe_tasks) == 1, f"样本 pipes 应生成 1 个 pipe task, 实际 {len(pipe_tasks)}"
    assert pipe_tasks[0]["id"] == "pipe-plumbing", "pipe task id 应为 pipe-plumbing"

    # 缺 pipes 键的样本 (回归安全): 不生成 pipe task
    with open(sample, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.pop("pipes", None)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                     encoding="utf-8") as tf:
        json.dump(data, tf, ensure_ascii=False)
        tmp_path = tf.name
    parsed2 = parse_json_input(tmp_path)
    assert not [t for t in parsed2["task_list"] if t["type"] == "pipe"], \
        "缺 pipes 键不应生成 pipe task (回归安全)"
    os.unlink(tmp_path)


if __name__ == "__main__":
    test_add_pipe_creates_lwpolyline_on_pipe_layer()
    test_add_pipe_waste_layer_diagonal_label()
    test_cad_execute_pipe_task_writes_pipe_entities()
    test_input_parser_emits_pipe_task()
    print("OK: all pipe DWG export tests passed")
