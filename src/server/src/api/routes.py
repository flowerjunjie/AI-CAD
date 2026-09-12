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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
