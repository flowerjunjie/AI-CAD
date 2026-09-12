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


if __name__ == "__main__":
    test_agent_graph_builds()
    test_agent_graph_compiles()
    test_state_schema()
    print("\n🎉 All integration tests passed!")
