"""
单元测试 — 门窗编号生成 + 编号文字渲染 (Phase 1 P0 闭环)
- numbering: M1..Mn / C1..Cn 按出现序编号, 输出 dict 带 number/mark
- cad_tools: add_opening_marker 在 OPENING_TAG 层画编号 TEXT
- cad_execute_node: 出图分支把编号传进去 (ezdxf 读回查 OPENING_TAG TEXT)
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def test_assign_door_numbers_by_order():
    """门按出现序 M1..Mn, 每门 dict 带 number/mark 键"""
    from src.agents.src.numbering import assign_door_numbers

    doors = [
        {"id": "d1", "type": "entrance", "width_m": 1.0},
        {"id": "d2", "type": "interior", "width_m": 0.9},
        {"id": "d3", "type": "bathroom", "width_m": 0.8},
    ]
    numbered = assign_door_numbers(doors)
    assert [d["number"] for d in numbered] == ["M1", "M2", "M3"]
    for d in numbered:
        assert "mark" in d and "number" in d, "每门须带 number/mark 键"
        assert d["mark"] == d["number"], "P0: mark 直接取 number"
    # 原 dict 不改 (纯函数)
    assert "number" not in doors[0], "不应改原 dict"


def test_assign_window_numbers_by_order():
    """窗按出现序 C1..Cn"""
    from src.agents.src.numbering import assign_window_numbers

    windows = [{"id": "w1"}, {"id": "w2"}, {"id": "w3"}]
    numbered = assign_window_numbers(windows)
    assert [w["number"] for w in numbered] == ["C1", "C2", "C3"]


def test_opening_numbers_full():
    """opening_numbers 一次出全量编号"""
    from src.agents.src.numbering import opening_numbers

    res = opening_numbers([{"id": "d1"}, {"id": "d2"}], [{"id": "w1"}])
    assert [d["number"] for d in res["doors"]] == ["M1", "M2"]
    assert [w["number"] for w in res["windows"]] == ["C1"]


def test_add_opening_marker_text():
    """add_opening_marker: OPENING_TAG 层 1 条 TEXT, 文字=编号, 落在指定坐标"""
    from src.agents.src.tools.cad_tools import DXFWriter

    writer = DXFWriter()
    writer.new("AC1027")
    writer.add_opening_marker("M1", (3.0, 4.0))
    writer.add_opening_marker("C2", (1.0, 2.0))

    doc = writer.doc
    assert "OPENING_TAG" in [l.dxf.name for l in doc.layers]
    texts = list(doc.modelspace().query('TEXT[layer=="OPENING_TAG"]'))
    assert len(texts) == 2
    got = {t.dxf.text: (round(t.dxf.insert[0], 6), round(t.dxf.insert[1], 6)) for t in texts}
    assert got.get("M1") == (3.0, 4.0), f"M1 文字坐标错, 实际 {got.get('M1')}"
    assert got.get("C2") == (1.0, 2.0), f"C2 文字坐标错, 实际 {got.get('C2')}"


def test_cad_execute_node_draws_numbered_markers():
    """cad_execute_node: 样本 7门+5窗 → OPENING_TAG 层 12 条编号 TEXT"""
    import ezdxf
    from src.agents.src.nodes.cad_rule_export import cad_execute_node
    from src.agents.src.nodes.input_parser import parse_json_input

    sample = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    parsed = parse_json_input(sample)
    state = {
        "raw_data": parsed["raw_data"],
        "project_structure": parsed["project_structure"],
        "task_list": parsed["task_list"],
        "output_path": "/tmp/aicad_opening_number_test.dwg",
        "auto_mode": True,
    }
    result = cad_execute_node(state)
    assert result.get("final_dwg_path"), "DWG 应生成"

    doc = ezdxf.readfile(result["final_dwg_path"])
    texts = list(doc.modelspace().query('TEXT[layer=="OPENING_TAG"]'))
    marks = sorted(t.dxf.text for t in texts)
    # 7门 M1..M7 + 5窗 C1..C5 = 12 条
    assert len(texts) == 12, f"应 12 条编号文字, 实际 {len(texts)}: {marks}"
    assert "M1" in marks and "M7" in marks, f"门编号 M1..M7 不全: {marks}"
    assert "C1" in marks and "C5" in marks, f"窗编号 C1..C5 不全: {marks}"
    expected = sorted(["M1", "M2", "M3", "M4", "M5", "M6", "M7",
                      "C1", "C2", "C3", "C4", "C5"])
    assert marks == expected, f"编号集合错: {marks}"


def test_door_numbering_space_matches_id():
    """编号空间与 id 对齐: 门 d1(entrance)→M1, 后续户内/卫门依序 M2..M7"""
    from src.agents.src.numbering import assign_door_numbers

    doors = [
        {"id": "d1", "type": "entrance"},
        {"id": "d2", "type": "interior"},
        {"id": "d3", "type": "interior"},
        {"id": "d4", "type": "interior"},
        {"id": "d5", "type": "interior"},
        {"id": "d6", "type": "bathroom"},
        {"id": "d7", "type": "bathroom"},
    ]
    by_id = {d["id"]: d["number"] for d in assign_door_numbers(doors)}
    assert by_id["d1"] == "M1", "户门 d1 应排 M1"
    assert by_id["d7"] == "M7", "末位 d7 应排 M7"
    assert set(by_id.values()) == {f"M{i}" for i in range(1, 8)}


if __name__ == "__main__":
    test_assign_door_numbers_by_order()
    test_assign_window_numbers_by_order()
    test_opening_numbers_full()
    test_add_opening_marker_text()
    test_cad_execute_node_draws_numbered_markers()
    test_door_numbering_space_matches_id()
    # ASCII print — Windows GBK 终端不能 print emoji (直跑护栏见 test_direct_run.py)
    print("OK: all opening numbering tests passed")
