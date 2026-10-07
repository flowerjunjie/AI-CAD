"""
AI-CAD Agent 图定义 — LangGraph
人在回路的可中断执行流
集成 LLM + RAG + CAD + 规则引擎

外部依赖标注（诚实边界，不虚标）:
- 本模块图编排逻辑本身纯 Python 可测（纯定义 + routing 函数）。
- 但完整跑图需真 langgraph 栈 + LLM API key + ChromaDB 向量库:
  * `tests/integration/test_agent_graph.py` 的 4 条框架用例默认 skip，
    设 `AI_CAD_RUN_FRAMEWORK=1` 才真构建/编译 Agent 图。
  * LLM 主导路径需 `AGNES_API_KEY`（或对应 provider key）。
  覆盖率 ~27% 属正常——未盖部分全落在「需真框架/真 key 才能跑」的编排分支，
  非「没测试的 bug 热点」，故不硬 mock 凑覆盖（红线二：不造假绿）。
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
    raw_data: dict  # input_parser 产出的原始户型数据（zones/doors/windows 几何）

    # CAD execution
    cad_queue: list[dict]
    cad_results: list[dict]
    human_confirmations: dict[str, bool]

    # Rule checking
    rule_violations: list[dict]
    rule_check_passed: bool
    opening_collisions_check: dict  # 门窗碰撞自洽诊断 (rule_check_node 产出; 声明进 schema 才随 state 持久化, 仿 export_status 范式)

    # Output
    final_dwg_path: str | None
    export_format: str
    material_tables: list[dict]
    export_status: str | None  # export_node 产出；声明进 schema 才随 state 持久化


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


def pending_confirmation_ids(state: DesignState) -> list[str]:
    """待确认 task_id 列表（human_confirmations 中值为 False 的键）"""
    return [tid for tid, ok in state.get("human_confirmations", {}).items() if not ok]


# ─── Confirmation Node ──────────────────────────────────────────

def awaiting_confirmation_node(state: DesignState) -> dict:
    """人在回路暂停点：仍有未确认 task 时调用 interrupt() 挂起，
    把待确认 task_id 列表作为 interrupt 值暴露给调用方。

    恢复 (resume) 语义：
      - 首次 invoke 在本节点挂起；resume 时 LangGraph 从本节点起点重跑，
        interrupt() 返回调用方 Command(resume=...) 传入的值（= 已更新的全量
        human_confirmations，确认项已置 True）。
      - 节点把该值写回 state["human_confirmations"]；随后条件边
        should_continue_confirmation 读到「全部确认」→ 路由到 rule_check。
      - 若 resume 值仍有 pending → 条件边路由回 awaiting_confirmation（可逐批确认）。
    挂起/恢复依赖 checkpointer（compile 时传入）。"""
    pending = pending_confirmation_ids(state)
    if not pending:
        return {}
    from langgraph.types import interrupt
    # 挂起并暴露待确认 task_id；resume 时返回传入的确认映射（或首次为 None）。
    resumed = interrupt({"pending_task_ids": pending, "message": "请确认 CAD 执行结果后放行"})
    if not resumed:
        # 首次挂起尚未 resume：什么都不改，等调用方传值回来
        return {}
    # resumed 是调用方更新后的 human_confirmations（确认项已 True）
    return {"human_confirmations": resumed}


# ─── Graph Construction ─────────────────────────────────────────

def build_agent_graph(checkpointer=None) -> "StateGraph":
    """构建 Agent 执行图

    checkpointer: 传入 MemorySaver（或持久 checkpointer）启用人在回路暂停/resume。
                  默认 None — auto_mode=True 的直跑路径保持不变（run.py 依赖此路径）。
    """
    from langgraph.graph import StateGraph, END

    graph = StateGraph(DesignState)

    # 添加节点
    graph.add_node("intent", intent_understanding_node)
    graph.add_node("structure", structure_design_node)
    graph.add_node("cad_execute", cad_execute_node)
    graph.add_node("awaiting_confirmation", awaiting_confirmation_node)
    graph.add_node("rule_check", rule_check_node)
    graph.add_node("export", export_node)

    # 入口
    graph.set_entry_point("intent")

    # 主线流程
    graph.add_edge("intent", "structure")
    graph.add_edge("structure", "cad_execute")

    # 人机协作分支：cad_execute 后按 auto_mode + 确认状态路由
    graph.add_conditional_edges(
        "cad_execute",
        should_request_confirmation,
        {"awaiting_confirmation": "awaiting_confirmation", "rule_check": "rule_check"},
    )
    # 暂停点：确认完 → 放行 rule_check；仍有 pending → 重回暂停点（可逐批确认）
    graph.add_conditional_edges(
        "awaiting_confirmation",
        should_continue_confirmation,
        {"rule_check": "rule_check", "awaiting_confirmation": "awaiting_confirmation"},
    )

    graph.add_edge("rule_check", "export")
    graph.add_edge("export", END)

    # 保留 checkpointer 引用：compile 时透传（见 run_agent_with_confirmation）
    graph._checkpointer = checkpointer  # type: ignore[attr-defined]
    return graph


def run_agent_demo(
    sample_path: str | None = None,
    auto_mode: bool = True,
    inject_sample_structure: bool = True,
) -> dict:
    """运行 Agent 演示流程
    sample_path: 可选，传入户型 JSON 路径 → 解析注入 raw_data + task_list
                 让 CAD/规则节点按真实样本数据出图、校验（Phase 1 数据接线）
    inject_sample_structure: True (默认) = 注入 sample 的 project_structure/task_list，
                 本地快验、LLM 意图被样本数据覆盖（结果确定、秒级）。
                 False = 只注入 raw_data 几何，project_structure/task_list 交给
                 LLM 的 intent + structure 节点生成（真 LLM 主导出图）。
    """
    graph = build_agent_graph()
    app = graph.compile()

    initial_state: DesignState = {
        "project_input": "三室一厅住宅，建筑面积约100平米，需要生成施工图",
        "output_path": "/tmp/ai_cad_demo_result.dwg",
        "auto_mode": auto_mode,
    }

    if sample_path:
        from src.agents.src.nodes.input_parser import parse_json_input
        parsed = parse_json_input(sample_path)
        # raw_data 是出图几何原料 (zones/doors/windows 坐标), 两种模式都注入
        initial_state["raw_data"] = parsed.get("raw_data", {})
        # project_structure/task_list 只在「本地快验」模式注入; LLM 主导模式
        # 交给 intent + structure 节点生成, 不被样本覆盖
        if inject_sample_structure:
            initial_state["task_list"] = parsed.get("task_list", [])
            initial_state["project_structure"] = parsed.get("project_structure", {})
            initial_state["project_type"] = parsed.get("project_type", "住宅")

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


# ─── 人在回路：暂停 → 确认 → 恢复 ───────────────────────────────

def run_agent_with_confirmation(
    sample_path: str | None = None,
    auto_mode: bool = False,
    confirm_all: bool = True,
    thread_id: str | None = None,
    output_path: str | None = None,
    inject_sample_structure: bool = True,
    confirm_fn=None,
) -> dict:
    """演示「跑到 cad_execute 后暂停 → 模拟人工确认 → 继续到 export」。

    依赖 langgraph checkpointer（MemorySaver 起步）+ interrupt() 暂停点：
      1. 首次 invoke（auto_mode=False, 有 pending 确认）→ 在 awaiting_confirmation
         挂起，返回的是「挂起前的 state 快照」，此时 CAD 已出图但规则/export 未跑。
      2. 读取挂起值里的 pending_task_ids，按 confirm_fn(confirm_ids) 决定放行哪些
         （默认 confirm_all=True 全放行）。
      3. 用相同 thread_id resume：把 human_confirmations 对应项置 True，
         再 invoke(None, config) 让图从暂停点重跑 → 条件边路由到 rule_check → export。

    返回最终完整 state（含 rule_violations / final_dwg_path）。
    """
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command

    saver = MemorySaver()
    graph = build_agent_graph(checkpointer=saver)
    # 暂停/resume 依赖 checkpointer 落盘线程状态 → compile 时必须传同一实例
    app = graph.compile(checkpointer=saver)
    config = {"configurable": {"thread_id": thread_id or "ai-cad-hil-demo"}}

    initial_state: DesignState = {
        "project_input": "三室一厅住宅，建筑面积约100平米，需要生成施工图",
        "output_path": output_path or "/tmp/ai_cad_demo_result.dwg",
        "auto_mode": auto_mode,
    }
    if sample_path:
        from src.agents.src.nodes.input_parser import parse_json_input
        parsed = parse_json_input(sample_path)
        initial_state["raw_data"] = parsed.get("raw_data", {})
        if inject_sample_structure:
            initial_state["task_list"] = parsed.get("task_list", [])
            initial_state["project_structure"] = parsed.get("project_structure", {})
            initial_state["project_type"] = parsed.get("project_type", "住宅")

    # 首跑：在确认点挂起。挂起时 invoke 返回「当前 state 快照」（非最终态）。
    result = app.invoke(initial_state, config)

    # 若仍有待确认（未挂起=auto_mode 或无 pending → 已跑到底），直接返回
    pending = pending_confirmation_ids(result)
    if not pending:
        return result

    # 决定放行哪些 task：confirm_fn(pending)→bool（自定义）；默认全放行
    release_all = confirm_fn(pending) if confirm_fn else confirm_all
    return _resume_with_confirmations(result, pending, release_all, app, config)


def _resume_with_confirmations(
    snapshot: dict, pending: list[str], release_all: bool, app, config: dict,
) -> dict:
    """resume 辅助：把 human_confirmations 对应项置 True 后 invoke 续跑。

    release_all=True 放行全部 pending；False 不新增放行（图会再次停在确认点，
    等待下一轮 resume 时调用方自行挑选 task 确认 — 逐批确认语义）。"""
    from langgraph.types import Command
    new_confirms = dict(snapshot.get("human_confirmations", {}))
    if release_all:
        for tid in pending:
            new_confirms[tid] = True
    # Command(resume=...) 传入全量确认映射；awaiting_confirmation_node 写回 state，
    # 条件边据此路由到 rule_check（全部确认）或回到确认点（仍有 pending）。
    return app.invoke(Command(resume=new_confirms), config)


# ─── Session 级人在回路: 外部持有 checkpointer + thread, 分「起图挂起 / 续跑」两步 ───
# 与上面 run_agent_with_confirmation (一次跑到底, saver 闭在函数内) 互补:
# 这里把 saver/app/config 交给调用方 (bridge) 持有, 设计师可「起真实图 → 拿到挂起
# 快照 → 逐 task 确认 → 续跑同一 thread」, 即真正的 session 级人在回路 (非演示)。

def start_agent_run_suspended(
    sample_path: str | None = None,
    thread_id: str | None = None,
    output_path: str | None = None,
    inject_sample_structure: bool = True,
) -> dict:
    """起一次 auto_mode=False 的图, 跑到 awaiting_confirmation 挂起。

    返回 {saver, app, thread_id, pending_task_ids, snapshot}:
      - saver/app: MemorySaver + 编译图, 供后续 resume_agent_run 用 (同一实例!)
      - thread_id: 本次 run 的 thread (外部不传则自动生成)
      - pending_task_ids: 挂起时的待确认 task 列表 (设计师要逐个确认的对象)
      - snapshot: 挂起前 state 快照 (此时 CAD 已出图, 规则/export 未跑)
    若 auto_mode 下无 pending (已跑到底), pending_task_ids 为空。
    """
    from langgraph.checkpoint.memory import MemorySaver
    from uuid import uuid4

    saver = MemorySaver()
    graph = build_agent_graph(checkpointer=saver)
    app = graph.compile(checkpointer=saver)
    tid = thread_id or f"ai-cad-hil-{uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": tid}}

    initial_state: DesignState = {
        "project_input": "三室一厅住宅，建筑面积约100平米，需要生成施工图",
        "output_path": output_path or f"/tmp/ai_cad_hil_{tid}.dwg",
        "auto_mode": False,  # 人在回路必须关 auto_mode, 否则确认点被绕过
    }
    if sample_path:
        from src.agents.src.nodes.input_parser import parse_json_input
        parsed = parse_json_input(sample_path)
        initial_state["raw_data"] = parsed.get("raw_data", {})
        if inject_sample_structure:
            initial_state["task_list"] = parsed.get("task_list", [])
            initial_state["project_structure"] = parsed.get("project_structure", {})
            initial_state["project_type"] = parsed.get("project_type", "住宅")

    result = app.invoke(initial_state, config)  # 在确认点挂起, 返回挂起前快照
    pending = pending_confirmation_ids(result)
    return {
        "saver": saver,
        "app": app,
        "thread_id": tid,
        "config": config,
        "pending_task_ids": pending,
        "snapshot": result,
        "sample_path": sample_path,
    }


def resume_agent_run(
    session: dict,
    release_task_ids: list[str] | None = None,
    release_all: bool = True,
) -> dict:
    """续跑一次挂起的 run (用 start_agent_run_suspended 返回的 session)。

    release_all=True 放行全部 pending; release_task_ids 给定时只放行这些 task
    (逐 task 确认语义, 其余仍挂起, 图会再次停在确认点等下一批)。
    返回最终 state (含 rule_violations / final_dwg_path)。"""
    from langgraph.types import Command

    app = session["app"]
    config = session["config"]
    pending = session.get("pending_task_ids", [])
    new_confirms = dict(session["snapshot"].get("human_confirmations", {}))
    if release_task_ids is not None:
        for tid in release_task_ids:
            new_confirms[tid] = True
    elif release_all:
        for tid in pending:
            new_confirms[tid] = True
    # 逐批确认: 未放行的 task 保持 False, 图会重回确认点 (可再调本函数放行下一批)
    return app.invoke(Command(resume=new_confirms), config)
