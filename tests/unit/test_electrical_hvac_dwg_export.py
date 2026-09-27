"""
单元测试 — 电气/暖通出图 (Electrical Outlet/Switch + HVAC Duct/Unit/Grille DWG Export)
验证: DXFWriter 新增的电气/暖通出图方法在各自图层画点位/线段 + 标注层 TEXT,
      cad_execute_node 的 outlet/switch/hvac task_type 分支消费 raw_data 对应键。
仿 test_pipe_dwg_export.py / test_structural_dwg_export.py 范式。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

# 与样本 outlets 键坐标一致 (2 个插座)
_OUTLETS = [
    {"id": "o1", "layer": "ELEC_OUTLET", "x": 1.0, "y": 1.0, "height_m": 0.3},
    {"id": "o2", "layer": "ELEC_OUTLET", "x": 2.0, "y": 3.0, "height_m": 1.3},
]
# 与样本 switches 键坐标一致 (1 个开关)
_SWITCHES = [
    {"id": "s1", "layer": "ELEC_SWITCH", "x": 0.5, "y": 2.0, "height_m": 1.3},
]
# 与样本 hvac_* 键坐标一致 (风管1 + 机组1 + 风口1)
_HVAC_DUCTS = [
    {"id": "hd1", "layer": "HVAC_DUCT", "start": [1.0, 1.5], "end": [4.0, 1.5], "diameter_mm": 100},
]
_HVAC_UNITS = [
    {"id": "hu1", "layer": "HVAC_UNIT", "x": 0.5, "y": 0.5, "cooling_kw": 3.5},
]
_HVAC_GRILLES = [
    {"id": "hg1", "layer": "HVAC_GRILLE", "x": 3.0, "y": 3.0, "height_m": 2.5},
]


def test_add_outlet_creates_square_on_elec_layer():
    """add_outlet: ELEC_OUTLET 闭合正方形 LWPOLYLINE + ELEC_LABEL "H0.3" 标注。"""
    from src.agents.src.tools.cad_tools import DXFWriter, Outlet, Point

    writer = DXFWriter()
    writer.new("AC1027")
    n = writer.add_outlet(Outlet(position=Point(1.0, 1.0), height_m=0.3))
    assert n == 1, f"add_outlet 应返回 1 条标注, 实际 {n}"

    doc = writer.doc
    msp = doc.modelspace()
    squares = list(msp.query('LWPOLYLINE[layer=="ELEC_OUTLET"]'))
    assert len(squares) == 1, f"ELEC_OUTLET 图层应 1 条闭合 LWPOLYLINE, 实际 {len(squares)}"
    with squares[0].points(format="xy") as pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
    side = 100 / 1000.0
    assert abs((max(xs) - min(xs)) - side) < 1e-6, "插座正方形 x 边长应=0.1"
    assert min(xs) == 0.95 and min(ys) == 0.95, "正方形左下顶角应 = (x-half, y-half)"

    texts = [t.dxf.text for t in msp.query('TEXT[layer=="ELEC_LABEL"]')]
    assert "H0.3" in texts, f"插座高度标注 'H0.3' 未画, 实际 {texts}"


def test_add_switch_creates_square_on_switch_layer():
    """add_switch: ELEC_SWITCH 正方形 + ELEC_LABEL "H1.3" 标注。"""
    from src.agents.src.tools.cad_tools import DXFWriter, Switch, Point

    writer = DXFWriter()
    writer.new("AC1027")
    n = writer.add_switch(Switch(position=Point(0.5, 2.0), height_m=1.3))
    assert n == 1, f"add_switch 应返回 1 条标注, 实际 {n}"

    doc = writer.doc
    msp = doc.modelspace()
    squares = list(msp.query('LWPOLYLINE[layer=="ELEC_SWITCH"]'))
    assert len(squares) == 1, f"ELEC_SWITCH 图层应 1 条闭合 LWPOLYLINE, 实际 {len(squares)}"
    texts = [t.dxf.text for t in msp.query('TEXT[layer=="ELEC_LABEL"]')]
    assert "H1.3" in texts, f"开关高度标注 'H1.3' 未画, 实际 {texts}"


def test_add_hvac_duct_creates_lwpolyline_on_hvac_layer():
    """add_hvac_duct: HVAC_DUCT 层 LWPOLYLINE (两点) + HVAC_LABEL "DN100" 标注。"""
    from src.agents.src.tools.cad_tools import DXFWriter, HvacDuct, Point

    writer = DXFWriter()
    writer.new("AC1027")
    n = writer.add_hvac_duct(HvacDuct(start=Point(1.0, 1.5), end=Point(4.0, 1.5),
                                       diameter_mm=100))
    assert n == 1, f"add_hvac_duct 应返回 1 条标注, 实际 {n}"

    doc = writer.doc
    msp = doc.modelspace()
    lwps = list(msp.query('LWPOLYLINE[layer=="HVAC_DUCT"]'))
    assert len(lwps) == 1, f"HVAC_DUCT 图层应 1 条 LWPOLYLINE, 实际 {len(lwps)}"
    with lwps[0].points(format="xy") as pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
    assert abs(max(xs) - min(xs) - 3.0) < 1e-6, "水平风管 x 跨度应=3.0"
    assert max(ys) == min(ys) == 1.5, "水平风管 y 应恒=1.5"

    texts = [t.dxf.text for t in msp.query('TEXT[layer=="HVAC_LABEL"]')]
    assert "DN100" in texts, f"风管管径标注 'DN100' 未画, 实际 {texts}"


def test_add_hvac_unit_grille_create_squares():
    """add_hvac_unit/add_hvac_grille: HVAC_UNIT/HVAC_GRILLE 正方形 + HVAC_LABEL 标注。"""
    from src.agents.src.tools.cad_tools import (
        DXFWriter, HvacUnit, HvacGrille, Point,
    )

    writer = DXFWriter()
    writer.new("AC1027")
    writer.add_hvac_unit(HvacUnit(position=Point(0.5, 0.5), cooling_kw=3.5))
    writer.add_hvac_grille(HvacGrille(position=Point(3.0, 3.0), height_m=2.5))

    doc = writer.doc
    msp = doc.modelspace()
    assert len(msp.query('LWPOLYLINE[layer=="HVAC_UNIT"]')) == 1, \
        "HVAC_UNIT 图层应 1 条 LWPOLYLINE"
    assert len(msp.query('LWPOLYLINE[layer=="HVAC_GRILLE"]')) == 1, \
        "HVAC_GRILLE 图层应 1 条 LWPOLYLINE"
    texts = [t.dxf.text for t in msp.query('TEXT[layer=="HVAC_LABEL"]')]
    assert "K3.5" in texts, f"机组制冷量标注 'K3.5' 未画, 实际 {texts}"
    assert "H2.5" in texts, f"风口高度标注 'H2.5' 未画, 实际 {texts}"


def test_cad_execute_elec_hvac_tasks_write_entities():
    """cad_execute_node outlet/switch/hvac task_type: 消费 raw_data 对应键 →
    DWG 有 ELEC_OUTLET/ELEC_SWITCH/HVAC_* 图层实体 + 标注层 TEXT。
    ezdxf 读回查 (仿 pipe/structural 范式)。"""
    import ezdxf
    from src.agents.src.nodes.cad_rule_export import cad_execute_node
    from src.agents.src.nodes.input_parser import parse_json_input

    sample = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    parsed = parse_json_input(sample)
    state = {
        "raw_data": parsed["raw_data"],
        "project_structure": parsed["project_structure"],
        "task_list": parsed["task_list"],
        "output_path": "/tmp/aicad_elec_hvac_test.dwg",
        "auto_mode": True,
    }
    result = cad_execute_node(state)
    assert result.get("final_dwg_path"), "DWG 应生成"

    outlet_tasks = [r for r in result["cad_results"] if r["task_id"] == "outlet-elec"]
    switch_tasks = [r for r in result["cad_results"] if r["task_id"] == "switch-elec"]
    hvac_tasks = [r for r in result["cad_results"] if r["task_id"] == "hvac-system"]
    assert outlet_tasks, "task_list 应含 outlet-elec 任务"
    assert switch_tasks, "task_list 应含 switch-elec 任务"
    assert hvac_tasks, "task_list 应含 hvac-system 任务"
    assert outlet_tasks[0]["status"] == "completed", f"outlet 任务应 completed, 实际 {outlet_tasks[0]}"
    assert switch_tasks[0]["status"] == "completed", f"switch 任务应 completed, 实际 {switch_tasks[0]}"
    assert hvac_tasks[0]["status"] == "completed", f"hvac 任务应 completed, 实际 {hvac_tasks[0]}"
    assert outlet_tasks[0].get("count") == 2, f"样本 2 个插座应画 2 个, 实际 {outlet_tasks[0].get('count')}"
    assert switch_tasks[0].get("count") == 1, f"样本 1 个开关应画 1 个, 实际 {switch_tasks[0].get('count')}"
    assert hvac_tasks[0].get("count") == 3, f"样本 3 个暖通元素应画 3 个, 实际 {hvac_tasks[0].get('count')}"

    doc = ezdxf.readfile(result["final_dwg_path"])
    msp = doc.modelspace()
    assert len(msp.query('LWPOLYLINE[layer=="ELEC_OUTLET"]')) == 2, "ELEC_OUTLET 应 2 条 LWPOLYLINE"
    assert len(msp.query('LWPOLYLINE[layer=="ELEC_SWITCH"]')) == 1, "ELEC_SWITCH 应 1 条 LWPOLYLINE"
    assert len(msp.query('LWPOLYLINE[layer=="HVAC_DUCT"]')) == 1, "HVAC_DUCT 应 1 条 LWPOLYLINE"
    assert len(msp.query('LWPOLYLINE[layer=="HVAC_UNIT"]')) == 1, "HVAC_UNIT 应 1 条 LWPOLYLINE"
    assert len(msp.query('LWPOLYLINE[layer=="HVAC_GRILLE"]')) == 1, "HVAC_GRILLE 应 1 条 LWPOLYLINE"

    elec_texts = [t.dxf.text for t in msp.query('TEXT[layer=="ELEC_LABEL"]')]
    hvac_texts = [t.dxf.text for t in msp.query('TEXT[layer=="HVAC_LABEL"]')]
    assert elec_texts.count("H0.3") == 1 and elec_texts.count("H1.3") == 2, \
        f"ELEC_LABEL 应为 H0.3 x1 + H1.3 x2 (插座+开关), 实际 {elec_texts}"
    assert "DN100" in hvac_texts and "K3.5" in hvac_texts and "H2.5" in hvac_texts, \
        f"HVAC_LABEL 应含 DN100/K3.5/H2.5, 实际 {hvac_texts}"


def test_input_parser_emits_elec_hvac_tasks():
    """parse_json_input: 样本带 outlets/switches/hvac_* 键即生成 task;
    缺 keys 时零改动回归安全 (仿 pipe/structural 分支)。"""
    import json
    import tempfile
    from src.agents.src.nodes.input_parser import parse_json_input

    sample = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    parsed = parse_json_input(sample)
    outlet_tasks = [t for t in parsed["task_list"] if t["type"] == "outlet"]
    switch_tasks = [t for t in parsed["task_list"] if t["type"] == "switch"]
    hvac_tasks = [t for t in parsed["task_list"] if t["type"] == "hvac"]
    assert len(outlet_tasks) == 1, f"outlets 应生成 1 个 outlet task, 实际 {len(outlet_tasks)}"
    assert len(switch_tasks) == 1, f"switches 应生成 1 个 switch task, 实际 {len(switch_tasks)}"
    assert len(hvac_tasks) == 1, f"hvac_* 应生成 1 个 hvac task, 实际 {len(hvac_tasks)}"
    assert outlet_tasks[0]["id"] == "outlet-elec", "outlet task id 应为 outlet-elec"
    assert switch_tasks[0]["id"] == "switch-elec", "switch task id 应为 switch-elec"
    assert hvac_tasks[0]["id"] == "hvac-system", "hvac task id 应为 hvac-system"

    # 缺电气/暖通键的样本 (回归安全): 不生成 outlet/switch/hvac task
    with open(sample, "r", encoding="utf-8") as f:
        data = json.load(f)
    for k in ("outlets", "switches", "hvac_ducts", "hvac_units", "hvac_grilles"):
        data.pop(k, None)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                     encoding="utf-8") as tf:
        json.dump(data, tf, ensure_ascii=False)
        tmp_path = tf.name
    parsed2 = parse_json_input(tmp_path)
    assert not [t for t in parsed2["task_list"] if t["type"] in ("outlet", "switch", "hvac")], \
        "缺电气/暖通键不应生成对应 task (回归安全)"
    os.unlink(tmp_path)


def test_structure_design_passes_elec_hvac_counts():
    """structure_design_node 重建 task_list 时透传电气/暖通计数 (已知坑, 照 pipe 修法):
    LLM 主导路径 (不注入 sample task_list) 也会出 outlet/switch/hvac task。"""
    from src.agents.src.nodes.intent_structure import structure_design_node

    sample = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    state = {
        "project_type": "住宅",
        "disciplines": ["建筑", "电气", "暖通"],
        "raw_data": {
            "outlets": _OUTLETS,
            "switches": _SWITCHES,
            "hvac_ducts": _HVAC_DUCTS,
            "hvac_units": _HVAC_UNITS,
            "hvac_grilles": _HVAC_GRILLES,
        },
        "project_structure": {"zones": [], "floors": 1},
    }
    result = structure_design_node(state)
    structure = result["project_structure"]
    assert structure.get("outlet_count") == 2, \
        f"outlet_count 应透传 2, 实际 {structure.get('outlet_count')}"
    assert structure.get("switch_count") == 1, \
        f"switch_count 应透传 1, 实际 {structure.get('switch_count')}"
    assert structure.get("hvac_duct_count") == 1, \
        f"hvac_duct_count 应透传 1, 实际 {structure.get('hvac_duct_count')}"
    assert structure.get("hvac_unit_count") == 1, \
        f"hvac_unit_count 应透传 1, 实际 {structure.get('hvac_unit_count')}"
    assert structure.get("hvac_grille_count") == 1, \
        f"hvac_grille_count 应透传 1, 实际 {structure.get('hvac_grille_count')}"
    # 重建出的 task_list 必须含 outlet/switch/hvac task (否则被 structure_design_node 抹掉)
    types = [t["type"] for t in result["task_list"]]
    assert "outlet" in types, f"重建 task_list 缺 outlet task: {types}"
    assert "switch" in types, f"重建 task_list 缺 switch task: {types}"
    assert "hvac" in types, f"重建 task_list 缺 hvac task: {types}"


if __name__ == "__main__":
    test_add_outlet_creates_square_on_elec_layer()
    test_add_switch_creates_square_on_switch_layer()
    test_add_hvac_duct_creates_lwpolyline_on_hvac_layer()
    test_add_hvac_unit_grille_create_squares()
    test_cad_execute_elec_hvac_tasks_write_entities()
    test_input_parser_emits_elec_hvac_tasks()
    test_structure_design_passes_elec_hvac_counts()
    print("OK: all electrical/hvac DWG export tests passed")
