"""
AI-CAD Agent 图定义 — LangGraph
人在回路的可中断执行流
集成 LLM + RAG + CAD + 规则引擎
"""
from typing import TypedDict

# Note: langgraph is imported lazily inside build_agent_graph() to avoid
# pulling the heavy langgraph/langchain stack (~100s cold) during module
# collection (pytest import-time). The pure definitions below (DesignState,
# routing functions, node imports) do not depend on langgraph.

# Import node implementations
from src.agents.src.nodes.intent_structure import (
    intent_understanding_node,
    structure_design_node,
)
from src.agents.src.nodes.cad_rule_export import (
    cad_execute_node,
    rule_check_node,
    export_node,
)


# ─── State Definition ───────────────────────────────────────────

class DesignState(TypedDict, total=False):
    """Agent 共享状态"""

    # Input
    project_input: str
    design_file: str | None
    output_path: str  # 输出DWG路径
    auto_mode: bool  # 自动模式（跳过人工确认）

    # Intent & Structure
    project_type: str
    disciplines: list[str]
    project_structure: dict
    task_list: list[dict]

    # CAD execution
    cad_queue: list[dict]
    cad_results: list[dict]
    human_confirmations: dict[str, bool]

    # Rule checking
    rule_violations: list[dict]
    rule_check_passed: bool

    # Output
    final_dwg_path: str | None
    export_format: str
    material_tables: list[dict]


# ─── Edge Functions ─────────────────────────────────────────────

def should_request_confirmation(state: DesignState) -> str:
    """判断是否需要人工确认"""
    if state.get("auto_mode", False):
        return "rule_check"
    confirmations = state.get("human_confirmations", {})
    pending = [v for v in confirmations.values() if not v]
    return "awaiting_confirmation" if pending else "rule_check"


def should_continue_confirmation(state: DesignState) -> str:
    """人工确认后的分支"""
    all_confirmed = all(state.get("human_confirmations", {}).values())
    return "rule_check" if all_confirmed else "awaiting_confirmation"


# ─── Graph Construction ─────────────────────────────────────────

def build_agent_graph() -> "StateGraph":
    """构建 Agent 执行图"""
    from langgraph.graph import StateGraph, END

    graph = StateGraph(DesignState)

    # 添加节点
    graph.add_node("intent", intent_understanding_node)
    graph.add_node("structure", structure_design_node)
    graph.add_node("cad_execute", cad_execute_node)
    graph.add_node("rule_check", rule_check_node)
    graph.add_node("export", export_node)

    # 入口
    graph.set_entry_point("intent")

    # 主线流程
    graph.add_edge("intent", "structure")
    graph.add_edge("structure", "cad_execute")

    # 人机协作分支（直接到规则检查）
    graph.add_edge("cad_execute", "rule_check")
    graph.add_edge("rule_check", "export")
    graph.add_edge("export", END)

    return graph


def run_agent_demo() -> dict:
    """运行 Agent 演示流程"""
    graph = build_agent_graph()
    app = graph.compile()

    # 初始状态
    initial_state: DesignState = {
        "project_input": "三室一厅住宅，建筑面积约100平米，需要生成施工图",
        "output_path": "/tmp/ai_cad_demo_result.dwg",
        "auto_mode": True,  # 演示模式跳过人工确认
    }

    # 执行
    result = app.invoke(initial_state)

    return result


if __name__ == "__main__":
    print("=== AI-CAD Agent Demo ===")
    result = run_agent_demo()

    print(f"\n项目类型: {result.get('project_type')}")
    print(f"专业列表: {result.get('disciplines')}")
    print(f"任务数: {len(result.get('task_list', []))}")
    print(f"CAD结果: {len(result.get('cad_results', []))} 个任务")
    print(f"规范违规: {len(result.get('rule_violations', []))} 条")
    print(f"DWG路径: {result.get('final_dwg_path')}")
    print("\nAgent 演示完成!")
