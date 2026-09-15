"""
集成测试 — 数据接线：raw_data 真正驱动 CAD/规则节点
验证：生成的 DWG 实体数随样本规模变化（不再是写死的 7）
"""
import os
import sys
import json

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _load_sample_raw():
    sample = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    with open(sample, encoding="utf-8") as f:
        return json.load(f)


def _make_state():
    raw = _load_sample_raw()
    from src.agents.src.nodes.input_parser import parse_json_input
    parsed = parse_json_input(os.path.join(project_root, "data", "sample", "residential_100sqm.json"))
    return {
        "raw_data": parsed.get("raw_data", {}),
        "task_list": parsed.get("task_list", []),
        "project_structure": parsed.get("project_structure", {}),
        "project_type": parsed.get("project_type", "住宅"),
        "output_path": "/tmp/aicad_data_wiring_test.dwg",
        "auto_mode": True,
    }


def test_cad_node_consumes_raw_data():
    """CAD 节点按真实 zones/doors/windows 出图，实体数随样本规模"""
    from src.agents.src.nodes.cad_rule_export import cad_execute_node

    state = _make_state()
    result = cad_execute_node(state)

    assert result.get("final_dwg_path"), "DWG 应生成"
    # 样本有 7 zones / 7 doors / 5 windows — 实体总数应明显多于旧版写死的 7
    import ezdxf
    doc = ezdxf.readfile(result["final_dwg_path"])
    msp = doc.modelspace()
    total = sum(len(list(msp.query(q))) for q in ["LINE", "ARC", "TEXT"])
    # 外墙4 + 内墙>=1 + 门7(arc) + 窗5x2(line) + 标注若干 + 门确认
    assert total >= 20, f"实体数 {total} 过低，未消费 raw_data 几何"


def test_rule_check_uses_raw_elements():
    """规则校验按 raw_data 元素：样本含 1 条真违规（d5 厨房门 0.8m < 0.9m）"""
    from src.agents.src.nodes.cad_rule_export import rule_check_node

    state = _make_state()
    result = rule_check_node(state)
    # 样本：d5 厨房门 0.8m < 户内门 0.9m（门宽违规）+ d5 门 × w5 窗 同墙碰撞
    # 卫生间门 0.8m 合规、面积达标 → 应检出 2 条（1 门宽 + 1 碰撞）
    assert len(result["rule_violations"]) == 2, \
        f"应检出 2 条(d5门宽 + d5xw5碰撞)，实际 {len(result['rule_violations'])} 条"
    rule_ids = [v["rule_id"] for v in result["rule_violations"]]
    assert "residential-door-interior-width" in rule_ids, "应含 d5 门宽违规"
    assert "layout-opening-collision" in rule_ids, "应含 d5×w5 门窗碰撞"


def test_rule_check_detects_violation():
    """故意把次卫面积改小 → 规则引擎检出卫生间面积违规（叠加 d5 共 2 条）"""
    from src.agents.src.nodes.cad_rule_export import rule_check_node

    state = _make_state()
    # 破坏样本：次卫 1.5x2 = 3㎡ -> 改成 1.0x1.0 = 1㎡（< 2㎡ 违规）
    for z in state["raw_data"].get("zones", []):
        if z.get("name") == "次卫":
            z["length"], z["width"] = 1.0, 1.0
    result = rule_check_node(state)
    assert result["rule_check_passed"] is False
    assert any("bathroom" in v["rule_id"] for v in result["rule_violations"]), \
        f"应检出卫生间面积违规: {result['rule_violations']}"


def test_rule_check_hits_electrical_outlet_violation():
    """带 raw_data['outlets'] 的 state → 命中 electrical-* 违规 (Phase 4 电气走分发表验证)"""
    from src.agents.src.nodes.cad_rule_export import rule_check_node

    state = _make_state()
    # 加一个高插座 2.5m (超占位上限 2.0m) → 应命中 electrical-outlet-height-range
    state["raw_data"]["outlets"] = [
        {"id": "o1", "height_m": 2.5, "room_type": "living"},
    ]
    result = rule_check_node(state)
    rule_ids = [v["rule_id"] for v in result["rule_violations"]]
    assert "electrical-outlet-height-range" in rule_ids, \
        f"应检出电气插座高度违规, 实际: {rule_ids}"
    assert result["rule_check_passed"] is False
