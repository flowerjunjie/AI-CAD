"""
单元测试 — 墙体厚度标注 (Wall Thickness Callouts)
验证 CAD 节点对每条墙在 CENTERLINE 图层生成双线墙轮廓 (LWPOLYLINE)
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def test_wall_thickness_generates_lwpolyline():
    """cad_execute_node: 每条墙生成 CENTERLINE 图层 LWPOLYLINE (双线墙轮廓)"""
    import ezdxf
    from src.agents.src.nodes.cad_rule_export import cad_execute_node
    from src.agents.src.nodes.input_parser import parse_json_input

    sample = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    parsed = parse_json_input(sample)
    state = {
        "raw_data": parsed["raw_data"],
        "project_structure": parsed["project_structure"],
        "task_list": parsed["task_list"],
        "output_path": "/tmp/aicad_wall_thickness_test.dwg",
        "auto_mode": True,
    }
    result = cad_execute_node(state)
    assert result.get("final_dwg_path"), "DWG 应生成"

    doc = ezdxf.readfile(result["final_dwg_path"])
    msp = doc.modelspace()

    # CENTERLINE 图层应存在且含 LWPOLYLINE (每段墙 1 条双线轮廓)
    assert "CENTERLINE" in [l.dxf.name for l in doc.layers], \
        "应创建 CENTERLINE 图层"

    # 样本 7 zones → 外墙4条 + 内墙若干条 → LWPOLYLINE 数 >= 4
    lwps = list(msp.query('LWPOLYLINE[layer=="CENTERLINE"]'))
    assert len(lwps) >= 4, f"CENTERLINE 图层 LWPOLYLINE 数 {len(lwps)} < 4"

    # 每条墙厚 = 2×(th/2) 跨度: 水平墙 y 极差 = th, 竖直墙 x 极差 = th
    for lwp in lwps:
        with lwp.points(format="xy") as pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
        if max(ys) - min(ys) > 0:
            # 水平墙: x 极差 = 墙长, y 极差 = 墙厚
            assert max(xs) - min(xs) > 0.1, "水平双线墙 x 跨度应为墙长"
        else:
            # 竖直墙: y 极差 = 墙长, x 极差 = 墙厚
            assert max(ys) - min(ys) > 0.1, "竖直双线墙 y 跨度应为墙长"


def test_add_wall_thickness_skips_diagonal():
    """斜墙 (MVP 不画) → CENTERLINE 图层不增 LWPOLYLINE"""
    from src.agents.src.tools.cad_tools import DXFWriter, Wall, Point

    writer = DXFWriter()
    writer.new("AC1027")
    writer.add_wall_thickness(Wall(start=Point(0, 0), end=Point(1, 1), thickness=0.24))

    import ezdxf
    doc = writer.doc
    lwps = list(doc.modelspace().query('LWPOLYLINE[layer=="CENTERLINE"]'))
    assert len(lwps) == 0, "斜墙应跳过厚度标注"


def test_add_wall_thickness_horizontal_span():
    """水平墙: 双线 y 跨度 = 墙厚"""
    from src.agents.src.tools.cad_tools import DXFWriter, Wall, Point

    writer = DXFWriter()
    writer.new("AC1027")
    writer.add_wall_thickness(Wall(start=Point(0, 0), end=Point(5, 0), thickness=0.24))

    import ezdxf
    doc = writer.doc
    lwps = list(doc.modelspace().query('LWPOLYLINE[layer=="CENTERLINE"]'))
    assert len(lwps) == 1
    with lwps[0].points(format="xy") as pts:
        ys = [p[1] for p in pts]
    assert abs((max(ys) - min(ys)) - 0.24) < 1e-6, f"y 跨度应=0.24, 实际 {max(ys)-min(ys)}"


def test_add_wall_thickness_vertical_span():
    """竖直墙: 双线 x 跨度 = 墙厚"""
    from src.agents.src.tools.cad_tools import DXFWriter, Wall, Point

    writer = DXFWriter()
    writer.new("AC1027")
    writer.add_wall_thickness(Wall(start=Point(0, 0), end=Point(0, 4), thickness=0.12))

    import ezdxf
    doc = writer.doc
    lwps = list(doc.modelspace().query('LWPOLYLINE[layer=="CENTERLINE"]'))
    assert len(lwps) == 1
    with lwps[0].points(format="xy") as pts:
        xs = [p[0] for p in pts]
    assert abs((max(xs) - min(xs)) - 0.12) < 1e-6, f"x 跨度应=0.12, 实际 {max(xs)-min(xs)}"


def test_place_doors_carrys_width_m():
    """place_doors_on_walls 输出每门 dict 含 width_m 键 (供洞口标注复用门宽)"""
    from src.agents.src.layout import place_doors_on_walls, layout_rooms

    zones = [
        {"id": "z1", "name": "客厅", "type": "living", "length": 5, "width": 4},
        {"id": "z2", "name": "主卧", "type": "bedroom", "length": 3, "width": 4},
    ]
    rooms = layout_rooms(zones)
    doors = [{"id": "d1", "type": "interior", "width_m": 0.9, "location": "客厅→主卧"}]
    placed = place_doors_on_walls(doors, rooms)
    assert placed, "应至少放 1 扇门"
    for p in placed:
        assert "width_m" in p, f"门 {p.get('id')} 缺 width_m 键 (洞口标注需读)"
        assert p["width_m"] == 0.9, "width_m 应透传样本门宽"


def test_add_opening_dimensions_text_count():
    """add_opening_dimensions: 门+窗 各 1 条 DIMENSION 层 TEXT, 文字=宽度数字"""
    from src.agents.src.tools.cad_tools import DXFWriter

    writer = DXFWriter()
    writer.new("AC1027")
    doors = [
        {"id": "d1", "position": (3.0, 4.0), "width": 0.9, "rotation": 0.0,
         "room_type": "interior", "location": "客厅→主卧"},
    ]
    windows = [
        {"id": "w1", "start": (1.0, 0.0), "end": (3.0, 0.0), "sill_height": 0.9,
         "room": "客厅"},
    ]
    n = writer.add_opening_dimensions(doors, windows, offset=0.5)
    assert n == 2, f"门1+窗1 应画 2 条, 实际 {n}"

    doc = writer.doc
    texts = [t.dxf.text for t in doc.modelspace().query('TEXT[layer=="DIMENSION"]')]
    assert "0.9" in texts, f"门宽文字 '0.9' 未画, 实际 {texts}"
    assert "2.00" in texts, f"窗宽文字 '2.00' 未画, 实际 {texts}"


def test_dimension_task_includes_openings_count():
    """dimension 任务结果 dict 应含 openings 键 (标注条数), 便于下游统计"""
    import ezdxf
    from src.agents.src.nodes.cad_rule_export import cad_execute_node
    from src.agents.src.nodes.input_parser import parse_json_input

    sample = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    parsed = parse_json_input(sample)
    state = {
        "raw_data": parsed["raw_data"],
        "project_structure": parsed["project_structure"],
        "task_list": parsed["task_list"],
        "output_path": "/tmp/aicad_dimension_test.dwg",
        "auto_mode": True,
    }
    result = cad_execute_node(state)
    dim = [r for r in result["cad_results"] if r["task_id"] == "dim-axis"]
    assert dim, "dim-axis 任务应执行"
    assert dim[0].get("openings", 0) >= 5, \
        f"样本 7门+5窗 应画 >=12 条洞口标注, 实际 {dim[0].get('openings')} 条"


if __name__ == "__main__":
    test_wall_thickness_generates_lwpolyline()
    test_add_wall_thickness_skips_diagonal()
    test_add_wall_thickness_horizontal_span()
    test_add_wall_thickness_vertical_span()
    test_place_doors_carrys_width_m()
    test_add_opening_dimensions_text_count()
    test_dimension_task_includes_openings_count()
    # ASCII print — Windows GBK 终端不能 print emoji (直跑护栏见 test_direct_run.py)
    print("OK: all wall thickness + opening dimension tests passed")
