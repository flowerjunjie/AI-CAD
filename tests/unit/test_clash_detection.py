"""
跨专业碰撞检测几何库单元测试 (M4)
仿 test_opening_numbering / test_layout 纯函数范式: seg_intersect /
point_to_seg_dist / detect_clashes 覆盖正交/平行/共线退化/点位/空输入。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _import():
    from src.agents.src.tools import clash_detection as cd
    return cd


def test_seg_intersect_orthogonal():
    """正交相交: 竖线 × 横线 在中间交叉 → True"""
    cd = _import()
    # 竖线 x=5 (0~10) 与 横线 y=5 (0~10) 在 (5,5) 相交
    assert cd.seg_intersect((5, 0), (5, 10), (0, 5), (10, 5)) is True
    assert cd.seg_intersect((0, 5), (10, 5), (5, 0), (5, 10)) is True  # 对称


def test_seg_intersect_parallel_no_touch():
    """平行且不相交: 两条平行横线错开 → False; 共线但区间不重叠 → False"""
    cd = _import()
    assert cd.seg_intersect((0, 0), (10, 0), (0, 1), (10, 1)) is False
    assert cd.seg_intersect((0, 0), (5, 0), (7, 0), (12, 0)) is False  # 共轴但区间不重叠
    # 共线重叠 (任意坐标轴) → True (含 y 轴水平线)
    assert cd.seg_intersect((0, 4), (5, 4), (2, 4), (4, 4)) is True


def test_seg_intersect_endpoint_touch():
    """端点接触语义: 严格相交才算碰撞; 端点贴到/共线相接 → 不报 (与
    detect_opening_collisions 的 overlap_m>0 范式对齐 — 共享端点不算重叠)。"""
    cd = _import()
    # T 形端点贴到横梁内部: 非严格交叉 → 不报 (管端顶到梁面, 非穿梁)
    assert cd.seg_intersect((5, 0), (5, 5), (0, 5), (10, 5)) is False
    assert cd.seg_intersect((0, 5), (10, 5), (5, 0), (5, 5)) is False
    # 共线端点相接 (区间仅共享端点) → 不报
    assert cd.seg_intersect((0, 0), (5, 0), (5, 0), (10, 0)) is False
    # 共线真正重叠 (端点深入对方内部) → 报
    assert cd.seg_intersect((0, 0), (5, 0), (3, 0), (8, 0)) is True
    # 端点落到延长线外 (不在线段本体) → 不报
    assert cd.seg_intersect((5, 0), (5, 50), (0, 100), (10, 100)) is False


def test_seg_intersect_not_intersect():
    """不相交: 两段错开 → False"""
    cd = _import()
    assert cd.seg_intersect((0, 0), (5, 0), (5, 3), (10, 3)) is False
    assert cd.seg_intersect((0, 0), (0, 5), (10, 10), (15, 10)) is False


def test_point_to_seg_dist_projection_inside():
    """投影落在线段内部 → 到线段的垂足距离"""
    cd = _import()
    # 点 (5, 3) 到水平线 y=0 上 [0,10] 的垂足 (5,0) 在段内 → 距离 3
    d = cd.point_to_seg_dist(5, 3, (0, 0), (10, 0))
    assert abs(d - 3.0) < 1e-9, f"应为 3.0, 实际 {d}"


def test_point_to_seg_dist_clamp_beyond_end():
    """投影落在线段端点外 → clamp 到最近端点"""
    cd = _import()
    # 点 (20, 0) 到 [0,10] 水平段: 垂足 (20,0) 超右端 → clamp 到 (10,0) → 距离 10
    d = cd.point_to_seg_dist(20, 0, (0, 0), (10, 0))
    assert abs(d - 10.0) < 1e-9, f"应为 10.0, 实际 {d}"
    # 点 (-5, 0) → clamp 到 (0,0) → 距离 5
    d2 = cd.point_to_seg_dist(-5, 0, (0, 0), (10, 0))
    assert abs(d2 - 5.0) < 1e-9, f"应为 5.0, 实际 {d2}"


def test_point_to_seg_dist_diagonal():
    """斜线段: 点 (1,1) 到 (0,0)-(10,10) 距离 = 0 (在线上)"""
    cd = _import()
    assert cd.point_to_seg_dist(1, 1, (0, 0), (10, 10)) < 1e-9
    # 点 (0,1) 到斜线 (0,0)-(10,10): 距离 = 1/sqrt(2)
    d = cd.point_to_seg_dist(0, 1, (0, 0), (10, 10))
    assert abs(d - 1.0 / 2 ** 0.5) < 1e-9, f"应为 1/sqrt2, 实际 {d}"


def test_point_to_seg_dist_degenerate_segment():
    """退化线段 (a==b) → 到该点欧氏距离"""
    cd = _import()
    d = cd.point_to_seg_dist(3, 4, (0, 0), (0, 0))
    assert abs(d - 5.0) < 1e-9, f"应为 5.0, 实际 {d}"


def test_detect_clashes_pipe_pierces_beam():
    """管段穿过梁段 → pipe-beam 碰撞"""
    cd = _import()
    raw = {
        "pipes": [{"id": "p1", "start": [0, 5], "end": [10, 5]}],
        "structural_beams": [{"id": "b1", "start": [5, 0], "end": [5, 10]}],
    }
    res = cd.detect_clashes(raw)
    kinds = {c["kind"] for c in res}
    assert "pipe-beam" in kinds, f"应检出 pipe-beam, 实际 {kinds}"
    c = next(x for x in res if x["kind"] == "pipe-beam")
    assert {c["a_id"], c["b_id"]} == {"p1", "b1"}


def test_detect_clashes_outlet_near_beam():
    """插座点位落在梁段容差带内 → outlet-beam"""
    cd = _import()
    raw = {
        "outlets": [{"id": "o1", "x": 5.0, "y": 0.05}],
        "structural_beams": [{"id": "b1", "start": [0, 0], "end": [10, 0]}],
    }
    res = cd.detect_clashes(raw, tolerance_m=0.15)
    kinds = {c["kind"] for c in res}
    assert "outlet-beam" in kinds, f"应检出 outlet-beam, 实际 {kinds}"


def test_detect_clashes_outlet_near_column():
    """插座点位贴近柱中心 → outlet-column"""
    cd = _import()
    raw = {
        "outlets": [{"id": "o1", "x": 2.0, "y": 2.0}],
        "structural_columns": [{"id": "c1", "x": 2.05, "y": 2.05}],
    }
    res = cd.detect_clashes(raw, tolerance_m=0.15)
    assert any(c["kind"] == "outlet-column" for c in res), f"应检出 outlet-column, 实际 {res}"


def test_detect_clashes_grille_and_duct_kinds():
    """风口 × 梁 / 风管 × 柱 等其余 kind 命中"""
    cd = _import()
    raw = {
        "hvac_grilles": [{"id": "g1", "x": 5.0, "y": 0.05}],
        "hvac_ducts": [{"id": "d1", "start": [5, 2], "end": [5, 8]}],
        "structural_beams": [{"id": "b1", "start": [0, 0], "end": [10, 0]}],
        "structural_columns": [{"id": "c1", "x": 5.0, "y": 2.05}],
    }
    res = cd.detect_clashes(raw, tolerance_m=0.15)
    kinds = {c["kind"] for c in res}
    assert "grille-beam" in kinds, f"应检出 grille-beam, 实际 {kinds}"
    assert "duct-column" in kinds, f"应检出 duct-column, 实际 {kinds}"


def test_detect_clashes_no_collision_returns_empty():
    """无碰撞 (所有元素错开) → 返回 []"""
    cd = _import()
    raw = {
        "pipes": [{"id": "p1", "start": [0, 5], "end": [2, 5]}],
        "structural_beams": [{"id": "b1", "start": [5, 0], "end": [5, 10]}],
        "outlets": [{"id": "o1", "x": 9.0, "y": 9.0}],
        "structural_columns": [{"id": "c1", "x": 0.5, "y": 0.5}],
        "hvac_ducts": [{"id": "d1", "start": [1, 1], "end": [2, 2]}],
        "hvac_grilles": [{"id": "g1", "x": 7.0, "y": 7.0}],
    }
    res = cd.detect_clashes(raw, tolerance_m=0.15)
    assert res == [], f"无碰撞应返回空, 实际 {res}"


def test_detect_clashes_empty_input():
    """空输入 / 键缺失 优雅返回 [] (不崩)"""
    cd = _import()
    assert cd.detect_clashes({}) == []
    assert cd.detect_clashes({"pipes": []}) == []
    # 部分键缺失
    assert cd.detect_clashes({"structural_beams": [{"id": "b"}]}) == []


def test_detect_clashes_skip_missing_keys():
    """线段元素缺 start/end 或点位缺 x/y → 优雅跳过, 不崩"""
    cd = _import()
    raw = {
        "pipes": [{"id": "p_bad"}],  # 缺 start/end
        "outlets": [{"id": "o_bad"}],  # 缺 x/y
        "structural_beams": [{"id": "b1", "start": [0, 0], "end": [10, 0]}],
    }
    res = cd.detect_clashes(raw, tolerance_m=0.15)
    assert res == []


# ── M4 容差取值通道 (resolve_clash_tolerance, default.json 回填范式) ──

class _FakeDslRule:
    """仿 ParametricRule: 带 .params 的 DSL 规则对象 (无 .clash_tolerance_m 属性,
    走 getattr → params dict 路径, 与真实 ParametricRule 行为一致)。"""
    def __init__(self, params: dict):
        self.params = params


def test_resolve_clash_tolerance_priority():
    """取值优先级: params 显式 > DSL 规则 params > 几何默认; 来源标注不虚标。"""
    cd = _import()
    # ① 全空 → 几何默认 0.15, source=default
    assert cd.resolve_clash_tolerance() == (0.15, "default")
    assert cd.resolve_clash_tolerance(default_m=0.2, dsl_rule=None, params=None) == (0.2, "default")
    # ② DSL 规则 params 覆盖 (专家回填 default.json 即生效, 零代码)
    rule = _FakeDslRule({"clash_tolerance_m": 0.3})
    assert cd.resolve_clash_tolerance(dsl_rule=rule) == (0.3, "dsl")
    # ③ 会话级 params 压过 DSL (桥端点 query tolerance_m / 引擎 state 透传)
    assert cd.resolve_clash_tolerance(dsl_rule=rule,
                                      params={"clash_tolerance_m": 0.5}) == (0.5, "param")
    # ④ 非法值 (0/负/非数) 不采信, 逐级降级
    assert cd.resolve_clash_tolerance(params={"clash_tolerance_m": 0}) == (0.15, "default")
    assert cd.resolve_clash_tolerance(dsl_rule=_FakeDslRule({"clash_tolerance_m": -1}),
                                      params={"clash_tolerance_m": "abc"}) == (0.15, "default")
    # ⑤ 真实 ParametricRule 兼容性: 从 default.json 加载的 clash-tolerance-range 规则
    from src.rules.src.dsl import DslRuleProvider
    provider = DslRuleProvider(os.path.join(project_root, "src", "rules", "rules", "default.json"))
    rules = provider.load()
    clash_rule = next((r for r in rules if r.rule_id == "clash-tolerance-range"), None)
    assert clash_rule is not None, "default.json 应含 clash-tolerance-range 规则"
    tol, src = cd.resolve_clash_tolerance(dsl_rule=clash_rule)
    assert src == "dsl" and abs(tol - 0.15) < 1e-9, "现状值 = 几何默认 (改 JSON 即变, 行为不变)"
    # ⑥ confirmed 标志: M4 机制已落地 (取值通道已接主链路+桥端点), default.json
    # 回填 confirmed=true 即点亮 M4 占位卡 (与 M1 「专家填值即点亮」同叙事);
    # 不虚标: 真·多专业容差终值仍需专家背书 (confidence 维持 medium 不升级 high)。
    assert clash_rule._spec.dsl_only is True, "clash-tolerance-range 应 dsl_only (纯 DSL 新增)"
    assert clash_rule._spec.confidence == "medium", "几何容差非 GB 条文, confidence 不虚标 high"
    assert clash_rule._spec.confirmed is True, "机制已落地, confirmed=true (点亮 M4 卡)"


if __name__ == "__main__":
    test_seg_intersect_orthogonal()
    test_seg_intersect_parallel_no_touch()
    test_seg_intersect_endpoint_touch()
    test_seg_intersect_not_intersect()
    test_point_to_seg_dist_projection_inside()
    test_point_to_seg_dist_clamp_beyond_end()
    test_point_to_seg_dist_diagonal()
    test_point_to_seg_dist_degenerate_segment()
    test_detect_clashes_pipe_pierces_beam()
    test_detect_clashes_outlet_near_beam()
    test_detect_clashes_outlet_near_column()
    test_detect_clashes_grille_and_duct_kinds()
    test_detect_clashes_no_collision_returns_empty()
    test_detect_clashes_empty_input()
    test_detect_clashes_skip_missing_keys()
    test_resolve_clash_tolerance_priority()
    print("OK: all clash detection tests passed")


# ── M4 Wave 3: 出图侧碰撞标记 (add_clash_marker + task 接线) ──────
def test_add_clash_marker_creates_clash_entities():
    """DXFWriter.add_clash_marker: CLASH 层 CIRCLE + CLASH_LABEL 层 TEXT。"""
    from src.agents.src.tools.cad_tools import DXFWriter

    w = DXFWriter()
    w.new("AC1027")
    w.add_clash_marker(2.0, 2.5, "pipe-beam", label="PIPE-BEAM")
    msp = w.doc.modelspace()
    assert len(msp.query('CIRCLE[layer=="CLASH"]')) == 1, "应有 1 条 CLASH 圈"
    texts = [t.dxf.text for t in msp.query('TEXT[layer=="CLASH_LABEL"]')]
    assert "PIPE-BEAM" in texts, f"应有 PIPE-BEAM 标注, 实际 {texts}"


def test_cad_execute_clash_task_marks_clashes():
    """cad_execute_node task_type=clash: 有碰撞样本画 CLASH 圈, 无碰撞样本 0 圈。"""
    from src.agents.src.nodes.cad_rule_export import cad_execute_node

    state = {"raw_data": {
        "zones": [], "doors": [], "windows": [],
        # 管段横穿梁段 (y=2.5 横, 梁 x=2 竖穿过) → pipe-beam 碰撞
        "pipes": [{"id": "p", "start": [0.0, 2.5], "end": [4.0, 2.5]}],
        "structural_beams": [{"id": "b", "start": [2.0, 0.0], "end": [2.0, 5.0]}],
    }, "task_list": [{"id": "clash-all", "type": "clash"}],
        "output_path": "/tmp/aicad_clash_task.dwg", "auto_mode": True}
    res = cad_execute_node(state)
    clash = [r for r in res["cad_results"] if r["task_id"] == "clash-all"][0]
    assert clash["clashes"] == 1, f"应 1 处碰撞, 实际 {clash.get('clashes')}"

    import ezdxf
    doc = ezdxf.readfile(res["final_dwg_path"])
    assert len(doc.modelspace().query('CIRCLE[layer=="CLASH"]')) == 1, "出图应含 1 碰撞圈"

    # 无碰撞样本 → 0 圈
    state2 = {"raw_data": {
        "zones": [], "doors": [], "windows": [],
        "pipes": [{"id": "p", "start": [0.0, 9.0], "end": [4.0, 9.0]}],
        "structural_beams": [{"id": "b", "start": [2.0, 0.0], "end": [2.0, 5.0]}],
    }, "task_list": [{"id": "clash-all", "type": "clash"}],
        "output_path": "/tmp/aicad_clash_none.dwg", "auto_mode": True}
    res2 = cad_execute_node(state2)
    clash2 = [r for r in res2["cad_results"] if r["task_id"] == "clash-all"][0]
    assert clash2["clashes"] == 0, "无碰撞应 0 处"
    doc2 = ezdxf.readfile(res2["final_dwg_path"])
    assert len(doc2.modelspace().query('CIRCLE[layer=="CLASH"]')) == 0, "无碰撞不出圈"
