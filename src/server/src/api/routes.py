"""
服务器 API 路由 — 设计方案、Agent 任务、规则管理
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import json

app = FastAPI(title="AI-CAD API", version="0.1.0")


# ─── Data Models ──────────────────────────────────────────────

class DesignInput(BaseModel):
    project_type: str = "住宅"
    disciplines: list[str] = ["建筑"]
    description: str
    file_path: Optional[str] = None


class DesignTask(BaseModel):
    task_id: str
    status: str  # pending / running / completed / failed
    current_step: str
    result: Optional[dict] = None


class RuleCheckResult(BaseModel):
    passed: bool
    violations: list[dict]


# ─── In-memory Storage (Phase 0) ──────────────────────────────

designs: dict[str, dict] = {}
tasks: dict[str, DesignTask] = {}


# ─── Health Check ─────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "version": "0.1.0",
        "phase": "Phase 0",
        "modules": {
            "server": "running",
            "agents": "initialized",
            "rules": "loaded",
            "rag": "initialized",
        },
    }


# ─── Design API ───────────────────────────────────────────────

@app.post("/api/designs")
async def create_design(data: DesignInput):
    """创建设计任务"""
    import uuid
    task_id = str(uuid.uuid4())[:8]

    designs[task_id] = {
        "id": task_id,
        "project_type": data.project_type,
        "disciplines": data.disciplines,
        "description": data.description,
        "status": "pending",
        "created_at": "now",
    }

    tasks[task_id] = DesignTask(
        task_id=task_id,
        status="pending",
        current_step="idle",
    )

    return {"taskId": task_id, "status": "created"}


@app.get("/api/designs/{task_id}")
async def get_design(task_id: str):
    """获取设计任务状态"""
    if task_id not in designs:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks.get(task_id, DesignTask(task_id=task_id, status="unknown", current_step="idle"))
    design = designs[task_id]

    return {
        **design,
        "agent_status": {
            "current_step": task.current_step,
            "status": task.status,
        },
    }


# ─── Rules API ────────────────────────────────────────────────

@app.get("/api/rules")
async def list_rules():
    """列出所有已注册的规则"""
    from src.rules.src.engine import get_engine
    from src.rules.src.residential import doors, windows, corridors, rooms

    engine = get_engine()
    rules = []
    for rule in engine.list_rules():
        rules.append({
            "id": rule.rule_id,
            "name": rule.name,
            "code_ref": rule.code_ref,
            "severity": rule.severity.value,
        })
    return rules


@app.post("/api/rules/check")
async def check_rules(data: dict):
    """执行规则检查"""
    from src.rules.src.engine import get_engine
    from src.rules.src.residential.doors import Door
    from src.rules.src.residential.windows import Window
    from src.rules.src.residential.rooms import Room
    from src.rules.src.residential.corridors import Corridor

    engine = get_engine()
    elements = data.get("elements", [])
    rule_ids = data.get("rule_ids")

    violations = engine.check(elements, rule_ids=rule_ids)

    return {
        "passed": len(violations) == 0,
        "violation_count": len(violations),
        "violations": [
            {
                "rule_id": v.rule_id,
                "rule_name": v.rule_name,
                "severity": v.severity.value,
                "description": v.description,
                "element_id": v.element_id,
                "code_ref": v.code_ref,
            }
            for v in violations
        ],
    }


# ─── Knowledge Base API ───────────────────────────────────────

@app.get("/api/knowledge/search")
async def search_knowledge(query: str, top_k: int = 5):
    """搜索知识库"""
    from src.agents.src.tools.rag_tools import RAGKnowledgeBase

    rag = RAGKnowledgeBase()
    if not rag.initialize():
        raise HTTPException(status_code=500, detail="RAG not initialized")

    results = rag.search(query, top_k=top_k)
    return {"query": query, "results": results, "count": len(results)}


# ─── Agent API ────────────────────────────────────────────────

@app.get("/api/agents/status")
async def get_agent_status():
    """获取 Agent 执行状态"""
    return {
        "current_step": "idle",
        "is_running": False,
        "pending_confirmations": [],
        "supported_providers": ["minimax", "kimi", "glm"],
    }


@app.post("/api/agents/run")
async def run_agent(data: dict):
    """启动 Agent 执行流程"""
    # Phase 0: Return demo response
    return {
        "taskId": "demo-task-001",
        "status": "running",
        "steps": [
            {"name": "intent_understanding", "status": "completed"},
            {"name": "structure_design", "status": "running"},
            {"name": "decompose_tasks", "status": "pending"},
            {"name": "cad_execute", "status": "pending"},
            {"name": "rule_check", "status": "pending"},
            {"name": "export", "status": "pending"},
        ],
    }


# ─── Agent 人工确认（人在回路）─────────────────────────────────
# 配合 Agent 图专家在 graph.py 上做的暂停机制（interrupt + checkpointer +
# awaiting_confirmation_node）。本段只负责 FastAPI 端：登记人工决定 + 触发 resume。
# 图侧真实的「写 human_confirmations 并 resume」尚未定死，故 _resume_agent_graph()
# 目前是预留对接点（见其 docstring 的 TODO）。


class AgentConfirmRequest(BaseModel):
    """POST /agent/confirm 入参。

    confirmed=False → 记录该 task 为待确认（登记后仍暂停）；
    confirmed=True  → 标记放行并触发 resume（携 modifications 回写图状态）。
    """
    task_id: str
    confirmed: bool
    modifications: Optional[dict] = None


# 内存态（Phase 0）：挂起的 Agent 图 run + 每个待确认 task 的人工决定。
# run 键为 graph 的 thread_id，task 键为 cad 执行产生的 task_id（门/窗等）。
_pending_agent_runs: dict[str, dict] = {}
_agent_task_confirms: dict[str, dict] = {}


def _register_agent_task(run_id: str, task_id: str, node: str) -> None:
    """登记一个挂起在某 node、待人工确认的 task。内存态，供 status/confirm 用。"""
    _agent_task_confirms[task_id] = {"run_id": run_id, "node": node, "confirmed": False}


def _resume_agent_graph(run_id: str, confirmed: bool, modifications: Optional[dict]) -> dict:
    """TODO(图层专家对接点)：graph.py 的 run_agent_with_confirmation 还没定死。
    预期语义：按 thread_id=run_id 读 checkpointer 里的 state，把待确认 task 的
    human_confirmations 置 confirmed、并入 modifications，再 app.invoke(resume=...)
    把图从 interrupt 处恢复。届时把下面这段占位换成真实调用即可，端点签名不变。"""
    return {
        "resumed": False,
        "reason": "agent_graph_not_wired",
        "todo": "graph.py run_agent_with_confirmation",
    }


@app.post("/agent/confirm")
async def agent_confirm(data: AgentConfirmRequest):
    """登记人工确认，若 confirmed 则触发图侧 resume。"""
    record = _agent_task_confirms.get(data.task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # 内存态记录人工决定（immutable 风格：重建 dict，不改原对象）
    _agent_task_confirms[data.task_id] = {
        **record,
        "confirmed": data.confirmed,
        "modifications": data.modifications,
    }

    result = {
        "task_id": data.task_id,
        "confirmed": data.confirmed,
        "modifications": data.modifications,
        "status": "confirmed" if data.confirmed else "pending_confirm",
    }

    # confirmed=True 才放行 resume；False 只是登记「仍未确认」，图继续暂停
    if data.confirmed:
        result["resume"] = _resume_agent_graph(
            record["run_id"], data.confirmed, data.modifications)

    return result


@app.get("/agent/status")
async def agent_status():
    """当前停在哪个节点 + 待确认 task 列表（人在回路视图）。"""
    awaiting = [
        {
            "task_id": tid,
            "run_id": rec["run_id"],
            "node": rec["node"],
            "pending": not rec["confirmed"],
        }
        for tid, rec in _agent_task_confirms.items()
        if not rec["confirmed"]
    ]
    current_run = next(iter(_pending_agent_runs.values()), None)
    return {
        "current_node": current_run["node"] if current_run else "idle",
        "is_running": current_run is not None,
        "awaiting_confirmation": awaiting,
        "pending_task_count": len(awaiting),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
