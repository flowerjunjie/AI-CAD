"""
两稿改动冲突检测库单元测试 (M5 团队协作可自主子集)
仿 test_clash_detection 纯函数范式: diff_elements / detect_conflicts /
summarize_conflicts 覆盖 值冲突/新增/删除/嵌套 list 深比较/缺字段/空输入。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _import():
    from src.agents.src.tools import conflict_detection as cf
    return cf


def test_diff_elements_value_conflict():
    """同 id 同字段值不同 → kind='value' (门 width 0.9 → 1.0)"""
    cf = _import()
    a = [{"id": "d1", "width_m": 0.9, "type": "interior"}]
    b = [{"id": "d1", "width_m": 1.0, "type": "interior"}]
    res = cf.diff_elements(a, b, "doors")
    assert res == [
        {"id": "d1", "field": "width_m", "a_value": 0.9, "b_value": 1.0,
         "kind": "value"},
    ], f"应只 1 条 width_m 值冲突, 实际 {res}"


def test_diff_elements_identical_returns_empty():
    """同 id 值完全相同 → []"""
    cf = _import()
    a = [{"id": "w1", "sill_height_m": 0.9, "room": "客厅"}]
    b = [{"id": "w1", "sill_height_m": 0.9, "room": "客厅"}]
    assert cf.diff_elements(a, b, "windows") == []


def test_diff_elements_added():
    """id 只在 b → kind='added', b_value 为整块"""
    cf = _import()
    a = []
    b = [{"id": "p2", "layer": "PIPE", "diameter_mm": 50}]
    res = cf.diff_elements(a, b, "pipes")
    assert res == [
        {"id": "p2", "field": None, "a_value": None,
         "b_value": {"id": "p2", "layer": "PIPE", "diameter_mm": 50},
         "kind": "added"},
    ], f"应检出 added, 实际 {res}"


def test_diff_elements_removed():
    """id 只在 a → kind='removed', a_value 为整块"""
    cf = _import()
    a = [{"id": "o1", "x": 1.0, "y": 1.0}]
    b = []
    res = cf.diff_elements(a, b, "outlets")
    assert res == [
        {"id": "o1", "field": None,
         "a_value": {"id": "o1", "x": 1.0, "y": 1.0}, "b_value": None,
         "kind": "removed"},
    ], f"应检出 removed, 实际 {res}"


def test_diff_elements_nested_list_deep_compare():
    """嵌套 list (start/end) 深比较: 坐标不同 → value; 相同 → []"""
    cf = _import()
    a = [{"id": "p1", "start": [2.5, 2.5], "end": [6.0, 2.5]}]
    b = [{"id": "p1", "start": [2.5, 3.0], "end": [6.0, 2.5]}]
    res = cf.diff_elements(a, b, "pipes")
    assert res == [
        {"id": "p1", "field": "start", "a_value": [2.5, 2.5],
         "b_value": [2.5, 3.0], "kind": "value"},
    ], f"start 列表不同应值冲突, 实际 {res}"
    # end 相同不报; 整体同 → 只剩 1 条
    assert len(res) == 1

    # 完全相同 (含嵌套 list) → []
    a2 = [{"id": "p1", "start": [2.5, 2.5], "end": [6.0, 2.5]}]
    b2 = [{"id": "p1", "start": [2.5, 2.5], "end": [6.0, 2.5]}]
    assert cf.diff_elements(a2, b2, "pipes") == []


def test_diff_elements_missing_field_is_value():
    """缺字段: 稿A 门有 width_m, 稿B 同 id 无 → value, b_value=None"""
    cf = _import()
    a = [{"id": "d1", "width_m": 0.9, "type": "interior"}]
    b = [{"id": "d1", "type": "interior"}]  # 无 width_m
    res = cf.diff_elements(a, b, "doors")
    assert res == [
        {"id": "d1", "field": "width_m", "a_value": 0.9, "b_value": None,
         "kind": "value"},
    ], f"缺字段应值冲突 (b_value=None), 实际 {res}"


def test_diff_elements_empty_inputs():
    """空/None 输入 → [] (不崩)"""
    cf = _import()
    assert cf.diff_elements([], [], "doors") == []
    assert cf.diff_elements(None, None, "doors") == []
    assert cf.diff_elements([], None, "pipes") == []


def test_detect_conflicts_two_drafts():
    """两份 raw 全量比对: 门值冲突 + 管新增 + 插座删除"""
    cf = _import()
    raw_a = {
        "doors": [{"id": "d1", "width_m": 0.9, "type": "interior"}],
        "outlets": [{"id": "o1", "x": 1.0, "y": 1.0}],
    }
    raw_b = {
        "doors": [{"id": "d1", "width_m": 1.0, "type": "interior"}],
        "pipes": [{"id": "p2", "layer": "PIPE", "diameter_mm": 50}],
        # o1 被稿B删 → removed
    }
    res = cf.detect_conflicts(raw_a, raw_b)
    by = {(c["id"], c["kind"]): c for c in res}
    assert ("d1", "value") in by, f"应检出 d1 值冲突, 实际 {res}"
    assert by[("d1", "value")]["field"] == "width_m"
    assert by[("d1", "value")]["category"] == "doors"
    assert ("p2", "added") in by, f"应检出 p2 新增, 实际 {res}"
    assert by[("p2", "added")]["category"] == "pipes"
    assert ("o1", "removed") in by, f"应检出 o1 删除, 实际 {res}"
    assert by[("o1", "removed")]["category"] == "outlets"
    assert len(res) == 3, f"应恰好 3 条冲突, 实际 {len(res)}"


def test_detect_conflicts_empty_input():
    """detect_conflicts({}, {}) → [] (不崩)"""
    cf = _import()
    assert cf.detect_conflicts({}, {}) == []
    assert cf.detect_conflicts(None, None) == []


def test_summarize_counts():
    """summarize: 计数正确 (value/added/removed + by_category + total)"""
    cf = _import()
    conflicts = [
        {"id": "d1", "field": "width_m", "a_value": 0.9, "b_value": 1.0,
         "kind": "value", "category": "doors"},
        {"id": "p2", "field": None, "a_value": None, "b_value": {},
         "kind": "added", "category": "pipes"},
        {"id": "o1", "field": None, "a_value": {}, "b_value": None,
         "kind": "removed", "category": "outlets"},
    ]
    s = cf.summarize_conflicts(conflicts)
    assert s == {
        "total": 3,
        "by_category": {"doors": 1, "pipes": 1, "outlets": 1},
        "value_conflicts": 1,
        "added": 1,
        "removed": 1,
    }, f"汇总计数应正确, 实际 {s}"


def test_summarize_empty():
    """summarize 空输入 → 全 0, by_category={}"""
    cf = _import()
    s = cf.summarize_conflicts([])
    assert s == {"total": 0, "by_category": {}, "value_conflicts": 0,
                 "added": 0, "removed": 0}, f"空输入应全 0, 实际 {s}"
    assert cf.summarize_conflicts(None) == s


# ── 主链路接入 (M5): 默认无第二稿 → 0 冲突 no-op, 不破既有出图 ──
def test_cad_execute_conflict_task_noop_without_second_draft():
    """cad_execute_node task_type=conflict 无 conflict_raw_b → 0 冲突, 不画实体。"""
    from src.agents.src.nodes.cad_rule_export import cad_execute_node

    state = {"raw_data": {"doors": [{"id": "d1", "width_m": 0.9}]},
             "task_list": [{"id": "conflict-all", "type": "conflict"}],
             "output_path": "/tmp/aicad_conflict_noop.dwg", "auto_mode": True}
    res = cad_execute_node(state)
    r = [x for x in res["cad_results"] if x["task_id"] == "conflict-all"][0]
    assert r["status"] == "completed" and r["conflicts"] == 0, \
        f"无第二稿应 0 冲突, 实际 {r}"


def test_cad_execute_conflict_task_counts_second_draft():
    """带 conflict_raw_b (稿B 门 width 改) → 1 处值冲突, 仍不新增出图实体。"""
    from src.agents.src.nodes.cad_rule_export import cad_execute_node

    state = {"raw_data": {"doors": [{"id": "d1", "width_m": 0.9, "type": "interior"}]},
             "conflict_raw_b": {"doors": [{"id": "d1", "width_m": 1.0,
                                             "type": "interior"}]},
             "task_list": [{"id": "conflict-all", "type": "conflict"}],
             "output_path": "/tmp/aicad_conflict_hit.dwg", "auto_mode": True}
    res = cad_execute_node(state)
    r = [x for x in res["cad_results"] if x["task_id"] == "conflict-all"][0]
    assert r["conflicts"] == 1, f"应 1 处值冲突, 实际 {r}"



if __name__ == "__main__":
    test_diff_elements_value_conflict()
    test_diff_elements_identical_returns_empty()
    test_diff_elements_added()
    test_diff_elements_removed()
    test_diff_elements_nested_list_deep_compare()
    test_diff_elements_missing_field_is_value()
    test_diff_elements_empty_inputs()
    test_detect_conflicts_two_drafts()
    test_detect_conflicts_empty_input()
    test_summarize_counts()
    test_summarize_empty()
    test_cad_execute_conflict_task_noop_without_second_draft()
    test_cad_execute_conflict_task_counts_second_draft()
    print("OK: all conflict detection tests passed")
