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
    """summarize: 计数正确 (value/added/removed/duplicate + by_category + total)"""
    cf = _import()
    conflicts = [
        {"id": "d1", "field": "width_m", "a_value": 0.9, "b_value": 1.0,
         "kind": "value", "category": "doors"},
        {"id": "p2", "field": None, "a_value": None, "b_value": {},
         "kind": "added", "category": "pipes"},
        {"id": "o1", "field": None, "a_value": {}, "b_value": None,
         "kind": "removed", "category": "outlets"},
        {"id": "o3", "field": None, "a_value": None, "b_value": None,
         "kind": "duplicate", "category": "outlets"},
    ]
    s = cf.summarize_conflicts(conflicts)
    assert s == {
        "total": 4,
        "by_category": {"doors": 1, "pipes": 1, "outlets": 2},
        "value_conflicts": 1,
        "added": 1,
        "removed": 1,
        "duplicates": 1,
    }, f"汇总计数应正确, 实际 {s}"


def test_summarize_empty():
    """summarize 空输入 → 全 0, by_category={}; 含 duplicates 键"""
    cf = _import()
    s = cf.summarize_conflicts([])
    assert s == {"total": 0, "by_category": {}, "value_conflicts": 0,
                 "added": 0, "removed": 0, "duplicates": 0}, \
        f"空输入应全 0 (含 duplicates=0), 实际 {s}"
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
    assert r["duplicates_marked"] == 0, "无第二稿应 0 重复标记 (no-op)"


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
    assert r["duplicates_marked"] == 0, "门改宽无坐标重复, 应 0 标记"



# ── M5 几何等价类维度 (同坐标不同 id = 疑似重复元素, 纯函数扩展) ──

def test_detect_duplicate_elements_same_coord_different_id():
    """同坐标不同 id → 疑似重复元素 (kind='duplicate'), 跨两稿全量扫。"""
    cf = _import()
    raw_a = {"outlets": [
        {"id": "o1", "x": 1.0, "y": 1.0},
        {"id": "o2", "x": 1.0, "y": 1.0},  # 与 o1 同坐标不同 id → 重复
    ]}
    raw_b = {"outlets": [{"id": "o1", "x": 1.0, "y": 1.0}]}
    dupes = cf.detect_duplicate_elements(raw_a, raw_b)
    assert len(dupes) == 1, f"应 1 处重复, 实际 {dupes}"
    d = dupes[0]
    assert d["kind"] == "duplicate" and d["category"] == "outlets"
    assert d["id_a"] == "o1" and d["id_b"] == "o2"
    assert d["coord"] == [1.0, 1.0]


def test_detect_duplicate_elements_no_false_positive():
    """同坐标同 id (稿 A/B 对齐) → 不算重复 (removed 已记过, 不再报 duplicate)。"""
    cf = _import()
    raw_a = {"outlets": [{"id": "o1", "x": 2.0, "y": 2.0}]}
    raw_b = {"outlets": [{"id": "o1", "x": 2.0, "y": 2.0}]}
    dupes = cf.detect_duplicate_elements(raw_a, raw_b)
    assert dupes == [], f"同 id 同坐标不应报重复, 实际 {dupes}"


def test_detect_duplicate_elements_pipeline_endpoints():
    """管线 start/end 按端点排序 (方向不敏感): 同几何不同方向的管段不算重复。"""
    cf = _import()
    raw_a = {"pipes": [
        {"id": "p1", "start": [0.0, 0.0], "end": [5.0, 0.0]},
        {"id": "p2", "start": [5.0, 0.0], "end": [0.0, 0.0]},  # 与 p1 同几何反向
    ]}
    dupes = cf.detect_duplicate_elements(raw_a, {})
    assert len(dupes) == 1, f"同几何反向管段应 1 处重复, 实际 {dupes}"
    assert dupes[0]["id_a"] == "p1" and dupes[0]["id_b"] == "p2"


def test_detect_conflicts_includes_duplicates_by_default():
    """detect_conflicts 默认 check_duplicates=True: 重复元素进冲突清单。"""
    cf = _import()
    raw_a = {"outlets": [
        {"id": "o1", "x": 3.0, "y": 3.0},
        {"id": "o2", "x": 3.0, "y": 3.0},
    ]}
    res = cf.detect_conflicts(raw_a, {})
    kinds = {c["kind"] for c in res}
    assert "duplicate" in kinds, f"应含 duplicate 冲突, 实际 kinds={kinds}"
    dup = next(c for c in res if c["kind"] == "duplicate")
    assert dup["id_a"] == "o1" and dup["id_b"] == "o2"


def test_detect_conflicts_no_duplicates_when_disabled():
    """check_duplicates=False → 不报重复 (老调用方零改动, 向后兼容)。"""
    cf = _import()
    raw_a = {"outlets": [
        {"id": "o1", "x": 4.0, "y": 4.0},
        {"id": "o2", "x": 4.0, "y": 4.0},
    ]}
    res = cf.detect_conflicts(raw_a, {}, check_duplicates=False)
    assert all(c["kind"] != "duplicate" for c in res), \
        f"禁用重复检测应无 duplicate, 实际 {res}"


def test_summarize_counts_duplicate_kind():
    """summarize_conflicts 含 kind='duplicate' → 计入 total, 不污染 value/added/removed。"""
    cf = _import()
    conflicts = [
        {"id": "o1", "field": None, "a_value": None, "b_value": None,
         "kind": "duplicate", "category": "outlets"},
    ]
    s = cf.summarize_conflicts(conflicts)
    assert s["total"] == 1
    assert s["value_conflicts"] == 0 and s["added"] == 0 and s["removed"] == 0
    assert s["by_category"] == {"outlets": 1}


# ── M5 几何等价类出图侧 (DXFWriter.add_duplicate_marker + conflict task 接线) ──

def test_add_duplicate_marker_creates_dup_entities():
    """DXFWriter.add_duplicate_marker: DUP 层 CIRCLE (琥珀色) + DUP_LABEL 层 TEXT。"""
    from src.agents.src.tools.cad_tools import DXFWriter

    w = DXFWriter()
    w.new("AC1027")
    w.add_duplicate_marker(1.0, 1.0, label="DUP")
    msp = w.doc.modelspace()
    assert len(msp.query('CIRCLE[layer=="DUP"]')) == 1, "应有 1 条 DUP 圈"
    assert len(msp.query('TEXT[layer=="DUP_LABEL"]')) == 1, "应有 1 条 DUP 标注"
    # 琥珀色 ACI 32 (区别于 CLASH 品红 6), 与 M4 碰撞圈视觉区分
    circle = next(iter(msp.query('CIRCLE[layer=="DUP"]')))
    assert circle.dxf.color == 32, f"DUP 圈应琥珀色 32, 实际 {circle.dxf.color}"


def test_cad_execute_conflict_task_marks_duplicates():
    """cad_execute_node task_type=conflict: 有重复元素画 DUP 圈, 无重复 0 圈。"""
    from src.agents.src.nodes.cad_rule_export import cad_execute_node
    import ezdxf

    # 含重复元素 (o1/o2 同坐标 (1,1)) → 1 处 DUP
    state = {"raw_data": {
        "zones": [], "doors": [], "windows": [],
        "outlets": [{"id": "o1", "x": 1.0, "y": 1.0},
                    {"id": "o2", "x": 1.0, "y": 1.0}],
    }, "conflict_raw_b": {"outlets": [{"id": "o1", "x": 1.0, "y": 1.0}]},
       "task_list": [{"id": "conflict-all", "type": "conflict"}],
       "output_path": "/tmp/aicad_conflict_dup.dwg", "auto_mode": True}
    res = cad_execute_node(state)
    r = [x for x in res["cad_results"] if x["task_id"] == "conflict-all"][0]
    assert r["duplicates_marked"] == 1, f"应 1 处重复标记, 实际 {r.get('duplicates_marked')}"
    doc = ezdxf.readfile(res["final_dwg_path"])
    assert len(doc.modelspace().query('CIRCLE[layer=="DUP"]')) == 1, "出图应含 1 DUP 圈"

    # 无重复 (o1/o2 坐标不同) → 0 DUP 圈 (回归安全, 既有出图不变)
    state2 = {"raw_data": {
        "zones": [], "doors": [], "windows": [],
        "outlets": [{"id": "o1", "x": 1.0, "y": 1.0},
                    {"id": "o2", "x": 2.0, "y": 2.0}],
    }, "conflict_raw_b": {"outlets": [{"id": "o1", "x": 1.0, "y": 1.5},
                                       {"id": "o2", "x": 2.0, "y": 2.0}]},
       "task_list": [{"id": "conflict-all", "type": "conflict"}],
       "output_path": "/tmp/aicad_conflict_nodup.dwg", "auto_mode": True}
    res2 = cad_execute_node(state2)
    r2 = [x for x in res2["cad_results"] if x["task_id"] == "conflict-all"][0]
    assert r2["duplicates_marked"] == 0, "无重复应 0 标记"
    doc2 = ezdxf.readfile(res2["final_dwg_path"])
    assert len(doc2.modelspace().query('CIRCLE[layer=="DUP"]')) == 0, "无重复不出 DUP 圈"


def test_cad_execute_conflict_task_noop_no_duplicate_marker():
    """无第二稿 → 0 冲突 0 重复标记 (no-op, 不破既有出图)。"""
    from src.agents.src.nodes.cad_rule_export import cad_execute_node

    state = {"raw_data": {"outlets": [{"id": "o1", "x": 1.0, "y": 1.0}]},
             "task_list": [{"id": "conflict-all", "type": "conflict"}],
             "output_path": "/tmp/aicad_conflict_noop2.dwg", "auto_mode": True}
    res = cad_execute_node(state)
    r = [x for x in res["cad_results"] if x["task_id"] == "conflict-all"][0]
    assert r["status"] == "completed" and r["conflicts"] == 0
    assert r["duplicates_marked"] == 0, f"无第二稿应 0 重复标记, 实际 {r}"


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
    test_detect_duplicate_elements_same_coord_different_id()
    test_detect_duplicate_elements_no_false_positive()
    test_detect_duplicate_elements_pipeline_endpoints()
    test_detect_conflicts_includes_duplicates_by_default()
    test_detect_conflicts_no_duplicates_when_disabled()
    test_summarize_counts_duplicate_kind()
    test_add_duplicate_marker_creates_dup_entities()
    test_cad_execute_conflict_task_marks_duplicates()
    test_cad_execute_conflict_task_noop_no_duplicate_marker()
    print("OK: all conflict detection tests passed")
