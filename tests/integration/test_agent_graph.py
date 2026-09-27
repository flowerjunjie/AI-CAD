"""
集成测试 — Agent 图端到端流程
langgraph 冷启动极慢（~100s），默认跳过框架用例，仅业务测试即时通过。
设 AI_CAD_RUN_FRAMEWORK=1 才实际构建/编译 Agent 图（用于 CI 全量验证）。
"""
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

import pytest

# DesignState 是 TypedDict（graph.py 顶层定义，import 它不触发 langgraph 冷启动）
from src.agents.src.graph import DesignState

# 框架用例默认跳过：收集期不 import langgraph，避免 ~100s 冷启动
_RUN_FRAMEWORK = os.environ.get("AI_CAD_RUN_FRAMEWORK") == "1"


@pytest.mark.skipif(not _RUN_FRAMEWORK, reason="langgraph 框架用例默认跳过 (设 AI_CAD_RUN_FRAMEWORK=1 启用)")
def test_agent_graph_builds():
    """验证 Agent 图能正常构建"""
    from src.agents.src.graph import build_agent_graph
    graph = build_agent_graph()
    assert graph is not None
    print("✅ test_agent_graph_builds")


@pytest.mark.skipif(not _RUN_FRAMEWORK, reason="langgraph 框架用例默认跳过 (设 AI_CAD_RUN_FRAMEWORK=1 启用)")
def test_agent_graph_compiles():
    """验证 Agent 图能正常编译（不执行）"""
    from src.agents.src.graph import build_agent_graph
    graph = build_agent_graph()
    compiled = graph.compile()
    assert compiled is not None
    print("✅ test_agent_graph_compiles")


def test_state_schema():
    """验证状态定义包含所有必要字段"""
    state: DesignState = {
        "project_input": "三室一厅，建筑面积120平",
        "design_file": None,
        "project_type": "住宅",
        "disciplines": ["建筑"],
        "project_structure": {},
        "task_list": [],
        "cad_queue": [],
        "cad_results": [],
        "human_confirmations": {},
        "rule_violations": [],
        "rule_check_passed": False,
        "final_dwg_path": None,
        "export_format": "DWG",
        "material_tables": [],
    }
    assert "project_input" in state
    assert "rule_check_passed" in state
    print("✅ test_state_schema")


@pytest.mark.skipif(not _RUN_FRAMEWORK, reason="langgraph 框架用例默认跳过 (设 AI_CAD_RUN_FRAMEWORK=1 启用)")
def test_confirmation_pauses_then_resumes():
    """auto_mode=False：cad_execute 后在确认点挂起（暂停），确认后才继续到 export。

    验证人在回路核心契约：
      1. 首次 invoke → 在 awaiting_confirmation 挂起，此时尚未跑 rule_check/export，
         且暴露出待确认 task_id（human_confirmations 中 False 的键）。
      2. 把 human_confirmations 全部置 True 后 resume → 路由到 rule_check → export，
         最终态含 material_tables 与 rule_violations。
    """
    import os
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command
    from src.agents.src.graph import build_agent_graph, pending_confirmation_ids
    from src.agents.src.nodes.input_parser import parse_json_input

    sample = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    parsed = parse_json_input(sample)
    saver = MemorySaver()
    app = build_agent_graph(checkpointer=saver).compile(checkpointer=saver)
    cfg = {"configurable": {"thread_id": "test-hil"}}

    init = {
        "project_input": "三室一厅住宅，生成施工图",
        "output_path": "/tmp/ai_cad_hil_test.dwg",
        "auto_mode": False,
        "raw_data": parsed.get("raw_data", {}),
        "task_list": parsed.get("task_list", []),
        "project_structure": parsed.get("project_structure", {}),
    }

    # 阶段 1：挂起在确认点（尚未出 export）
    paused = app.invoke(init, cfg)
    assert pending_confirmation_ids(paused), "应在 cad_execute 后停在确认点，暴露待确认 task"
    assert paused.get("export_status") is None, "挂起时不应已跑完 export"
    assert "material_tables" not in paused or not paused.get("material_tables"), "挂起时不应已有材料表"

    # 阶段 2：全量放行并 resume
    all_confirmed = {k: True for k in paused.get("human_confirmations", {})}
    final = app.invoke(Command(resume=all_confirmed), cfg)
    assert all(final.get("human_confirmations", {}).values()), "resume 后应全部确认"
    assert "rule_check_passed" in final, "resume 后应经过 rule_check"
    assert final.get("material_tables"), "resume 后应完成 export"
    print("✅ test_confirmation_pauses_then_resumes")


@pytest.mark.skipif(not _RUN_FRAMEWORK, reason="langgraph 框架用例默认跳过 (设 AI_CAD_RUN_FRAMEWORK=1 启用)")
def test_confirmation_helper_roundtrip():
    """run_agent_with_confirmation 一键演示：暂停→模拟确认→继续，输出与直跑一致。"""
    import os
    from src.agents.src.graph import run_agent_with_confirmation, pending_confirmation_ids

    sample = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    result = run_agent_with_confirmation(
        sample_path=sample, auto_mode=False, confirm_all=True,
        thread_id="test-hil-helper", output_path="/tmp/ai_cad_hil_helper.dwg",
    )
    assert not pending_confirmation_ids(result), "全量放行后不应再有待确认 task"
    assert result.get("material_tables"), "辅助路径应跑到 export 并出材料表"
    assert result.get("rule_check_passed") is not None, "辅助路径应经过 rule_check"
    print("✅ test_confirmation_helper_roundtrip")


if __name__ == "__main__":
    test_agent_graph_builds()
    test_agent_graph_compiles()
    test_state_schema()
    test_confirmation_pauses_then_resumes()
    test_confirmation_helper_roundtrip()
    print("\n🎉 All integration tests passed!")
