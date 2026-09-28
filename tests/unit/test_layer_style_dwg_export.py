"""
单元测试 — 图层着色/线宽深化 (M3 出图深化: 元素→精细图元的制图标准维度)
验证: DXFWriter._ensure_layer_styles 给各专业图层套 ACI 色号 color + 线宽
      lineweight, 幂等重调不炸, 既有实体数量不变 (回归红线 BEAM=2/COLUMN=3/
      ELEC_OUTLET=2)。仿 test_cad_refinement_dwg_export.py 的 ezdxf 读回范式。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _style(doc, layer_name):
    """读回某图层的 (color, lineweight)。"""
    l = doc.layers.get(layer_name)
    return l.dxf.color, l.dxf.lineweight


def test_ensure_layer_styles_applies_standard_colors():
    """_ensure_layer_styles: 各专业图层 着色/线宽 按标准表落地。"""
    from src.agents.src.tools.cad_tools import DXFWriter

    writer = DXFWriter()
    writer.new("AC1027")
    writer._ensure_layer_styles()

    doc = writer.doc
    # 墙体承重主轮廓: 白(7) 粗(50)
    assert _style(doc, "WALL") == (7, 50), f"WALL 应 (7,50), 实际 {_style(doc,'WALL')}"
    assert _style(doc, "CENTERLINE") == (7, 50)
    # 水系统: 红(1) 细(13)
    assert _style(doc, "PIPE") == (1, 13)
    assert _style(doc, "PIPE_LABEL") == (1, 13)
    assert _style(doc, "PIPE_WASTE") == (1, 13)
    # 风系统: 蓝(5) 细(13)
    assert _style(doc, "HVAC_DUCT") == (5, 13)
    assert _style(doc, "HVAC_LABEL") == (5, 13)
    # 结构: 绿(3), 梁柱截面中粗(30) 标注细(13)
    assert _style(doc, "BEAM") == (3, 30)
    assert _style(doc, "BEAM_LABEL") == (3, 13)
    assert _style(doc, "COLUMN") == (3, 30)
    assert _style(doc, "FOUNDATION") == (3, 30)
    # 电气: 黄(2) 细(13)
    assert _style(doc, "ELEC_OUTLET") == (2, 13)
    assert _style(doc, "ELEC_SWITCH") == (2, 13)
    # 轴网/标注/编号: 白(7) 细(13)
    assert _style(doc, "AXIS") == (7, 13)
    assert _style(doc, "DIMENSION") == (7, 13)
    assert _style(doc, "OPENING_TAG") == (7, 13)


def test_ensure_layer_styles_idempotent():
    """_ensure_layer_styles 重复调用不炸, 样式幂等收敛 (不重复 new)。"""
    from src.agents.src.tools.cad_tools import DXFWriter

    writer = DXFWriter()
    writer.new("AC1027")
    writer._ensure_layer_styles()
    count_after_first = len(list(writer.doc.layers))
    writer._ensure_layer_styles()  # 第二次应全走 setter, no-op
    writer._ensure_layer_styles()  # 第三次仍安全

    assert len(list(writer.doc.layers)) == count_after_first, \
        "重复调用不得新增图层 (幂等)"
    # 收敛后样式不变
    assert _style(writer.doc, "BEAM") == (3, 30)
    assert _style(writer.doc, "PIPE") == (1, 13)


def test_ensure_layer_styles_overrides_bare_layers():
    """add_* 内裸建图层 (无色) 后, _ensure_layer_styles 补上样式 (同名字段增量)。

    主链路时序: add_pipe 先 layers.new('PIPE') 裸建 → save 入口 _ensure 走
    setter 分支覆盖。本测试复现「先裸建再 ensure」路径, 验证 setter 分支生效。
    """
    from src.agents.src.tools.cad_tools import DXFWriter, Pipe, Point

    writer = DXFWriter()
    writer.new("AC1027")
    # 模拟 add_pipe 内裸建 (无样式): 直接 new 一个图层但不套色
    writer.doc.layers.new("HVAC_GRILLE")
    # ezdxf 裸建图层默认 色7(白)/线宽 ByLayer(-3): 未显式套样式即此态
    assert _style(writer.doc, "HVAC_GRILLE") == (7, -3), \
        f"裸建图层默认应为 (7,-3), 实际 {_style(writer.doc,'HVAC_GRILLE')}"
    writer._ensure_layer_styles()
    assert _style(writer.doc, "HVAC_GRILLE") == (5, 13), \
        f"ensure 后裸建图层应被补上 (5,13), 实际 {_style(writer.doc,'HVAC_GRILLE')}"


def test_cad_execute_applies_layer_styles_roundtrip():
    """cad_execute_node 出图 (save 入口自动 _ensure): DWG 读回各图层带样式。
    ezdxf 读回范式 + 回归红线 (BEAM=2/COLUMN=3/ELEC_OUTLET=2 数量不变)。"""
    import ezdxf
    from src.agents.src.nodes.cad_rule_export import cad_execute_node
    from src.agents.src.nodes.input_parser import parse_json_input

    sample = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    parsed = parse_json_input(sample)
    state = {
        "raw_data": parsed["raw_data"],
        "project_structure": parsed["project_structure"],
        "task_list": parsed["task_list"],
        "output_path": "/tmp/aicad_layer_style_test.dwg",
        "auto_mode": True,
    }
    result = cad_execute_node(state)
    assert result.get("final_dwg_path"), "DWG 应生成"

    doc = ezdxf.readfile(result["final_dwg_path"])
    msp = doc.modelspace()

    # 出图后各图层已套样式 (save 入口 _ensure_layer_styles)
    assert _style(doc, "WALL") == (7, 50), f"WALL 层应 (7,50), 实际 {_style(doc,'WALL')}"
    assert _style(doc, "PIPE") == (1, 13), f"PIPE 层应 (1,13), 实际 {_style(doc,'PIPE')}"
    assert _style(doc, "BEAM") == (3, 30), f"BEAM 层应 (3,30), 实际 {_style(doc,'BEAM')}"
    assert _style(doc, "ELEC_OUTLET") == (2, 13)
    assert _style(doc, "AXIS") == (7, 13)

    # 回归红线: 实体数量不因样式深化而变
    assert len(msp.query('LWPOLYLINE[layer=="BEAM"]')) == 2, "BEAM 实体数不能变"
    assert len(msp.query('LWPOLYLINE[layer=="COLUMN"]')) == 3, "COLUMN 实体数不能变"
    assert len(msp.query('LWPOLYLINE[layer=="ELEC_OUTLET"]')) == 2, "ELEC_OUTLET 不能变"


if __name__ == "__main__":
    test_ensure_layer_styles_applies_standard_colors()
    test_ensure_layer_styles_idempotent()
    test_ensure_layer_styles_overrides_bare_layers()
    test_cad_execute_applies_layer_styles_roundtrip()
    print("OK: all layer-style (color/lineweight) DWG export tests passed")
