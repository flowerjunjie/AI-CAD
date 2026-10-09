"""
AI-CAD GUI FastAPI 桥 — 把真实 Python 引擎暴露成 HTTP, 供 Electron/浏览器专业面板消费。

分工 (见 docs/gui-contract.md §3):
  - B 规则域  : /api/rules, /api/rule-violations
  - C Agent 域: /api/pipeline, /api/preview
  - D RAG 域  : /api/rag/search, /api/health 的 rag 布尔   ← 本文件已实现段
  - E 入口    : start_gui.bat / start_gui.py
约束:
  - langgraph/chromadb 一律懒加载 (放函数体), 模块收集时不触发 ~100s 冷启动。
  - 未实现能力只出占位, 绝不造假数据 (红线二: 区分「没数据」和「错了」)。
"""
from __future__ import annotations

import json
import os
import sys
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ─── 项目根定位 (桥可被 uvicorn / 直接 import 两种方式拉起) ───
def _project_root() -> str:
    # 本文件在 <root>/src/gui/bridge.py → 上溯两级
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

ROOT = _project_root()
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

CHROMA_DB = os.path.join(ROOT, "data", "chroma_db")

app = FastAPI(title="AI-CAD GUI Bridge", version="0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:*", "http://127.0.0.1:*", "null"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── D RAG/知识域段 ──────────────────────────────────────────────
# 懒加载 + 单例: 只在真正检索/探活时连 chromadb, 不碰模块收集期。
_rag_kb: Optional[object] = None
_rag_ready: Optional[bool] = None  # None=未探, True/False=已探


def _get_rag():
    """惰性拿 RAGKnowledgeBase 单例; chromadb 未装/初始化失败返回 None。"""
    global _rag_kb, _rag_ready
    if _rag_kb is not None:
        return _rag_kb
    from src.agents.src.tools.rag_tools import RAGKnowledgeBase  # 懒 import

    if not os.path.exists(CHROMA_DB):
        _rag_ready = False
        return None
    kb = RAGKnowledgeBase(persist_path=CHROMA_DB)
    ok = kb.initialize()
    _rag_ready = bool(ok)
    if ok:
        _rag_kb = kb
    return _rag_kb


class RAGSearchReq(BaseModel):
    query: str
    top_k: int = 5


@app.post("/api/rag/search")
def rag_search(req: RAGSearchReq) -> dict:
    """本地 ChromaDB 向量检索。

    返回结构固定 {query, results, note?, count}; 三种诚实状态:
      - 有命中: results 非空, 无 note
      - 库可连但 0 命中: results 空 + note 说明「本地库未命中」, 不崩
      - chromadb 未装/库缺失: results 空 + note 说明「本地库不可用」, 不崩
    """
    kb = _get_rag()
    if kb is None or getattr(kb, "_collection", None) is None:
        reason = "本地库不可用" if _rag_ready else "本地库不可用 (chromadb 未安装或库缺失)"
        return {"query": req.query, "results": [], "count": 0, "note": reason}

    raw = kb.search(req.query, top_k=max(1, req.top_k))
    results = []
    for r in raw:
        meta = r.get("metadata") or {}
        dist = r.get("distance")
        # cosine distance ∈ [0,2] → score ∈ [0,1], 越高越相关
        score = round(max(0.0, 1.0 - (dist if dist is not None else 0.0)), 4)
        results.append({
            "text": r.get("content", ""),
            "score": score,
            "category": meta.get("category", "unknown"),
            "code": meta.get("code"),
        })
    if not results:
        return {"query": req.query, "results": [], "count": 0,
                "note": "本地库未命中 (库当前为空或无相关条文)"}
    return {"query": req.query, "results": results, "count": len(results)}


# /api/health 的 rag 布尔由本段补 (文件存在 + 可 initialize)
def rag_health() -> bool:
    """供 /api/health 调用: rag 库是否可用 (不影响其他模块探活)。"""
    return bool(_get_rag() is not None)


# ─── B 规则域段: 拆到 bridge_rules.py, include_router 挂载 ─────────────
# 从 bridge.py 拆出 (超 500 红线), APIRouter 承载 /api/rules + /api/rule-violations +
# /api/health。跨段依赖 _load_sample_raw 走 bridge_common, rag_health 函数体惰性 import。
# 端点路径 0 改动, 挂载即注册。
from src.gui.bridge_rules import router as _rules_router
app.include_router(_rules_router)


# ─── C Agent 域段: /api/pipeline (Agent 出方案+违规) + /api/preview (出图) ───
# 命脉段: 前端左区真户型图靠它。langgraph/easydxf/matplotlib 全部懒加载进函数体,
# 模块收集期不触发 ~100s 冷启动。复用 run.py 的渲染逻辑, 但绝不弹窗 (GUI 里渲染成 bytes)。

from fastapi.responses import Response


class PipelineReq(BaseModel):
    sample: str = "residential_100sqm.json"
    use_llm: bool = False


def _sample_path(sample: str) -> str:
    p = os.path.join(ROOT, "data", "sample", sample)
    if not os.path.exists(p):
        raise HTTPException(400, f"样本不存在: {sample}")
    return p


@app.post("/api/pipeline")
def api_pipeline(req: PipelineReq) -> dict:
    """跑 Agent 全链路 (默认本地快验路径, 秒级确定结果; use_llm=True 走真 LLM 主导)。"""
    from src.agents.src.graph import run_agent_demo  # 懒: langgraph 栈

    sample = _sample_path(req.sample)
    inject = not req.use_llm  # False -> LLM 主导 (inject_sample_structure=False)
    result = run_agent_demo(sample_path=sample, auto_mode=True, inject_sample_structure=inject)

    zones = []
    for z in (result.get("project_structure") or {}).get("zones", []):
        zones.append({"name": z.get("name", ""), "type": z.get("type", ""), "area": z.get("area", "")})

    return {
        "project_type": result.get("project_type", ""),
        "zones": zones,
        "task_count": len(result.get("task_list", [])),
        "violations": [
            {
                "rule_id": v.get("rule_id"),
                "rule_name": v.get("rule_name"),
                "severity": v.get("severity"),
                "description": v.get("description"),
                "code_ref": v.get("code_ref"),
                "element_id": v.get("element_id"),
            }
            for v in result.get("rule_violations", [])
        ],
        "dwg_path": result.get("final_dwg_path", ""),
        "preview_url": f"/api/preview?sample={req.sample}",
    }


def render_sample_png(sample: str) -> bytes:
    """把样本 Agent 出图渲染成 PNG bytes (matplotlib Agg + CJK), 不弹窗。"""
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend, setup_axes
    from src.agents.src.tools.matplotlib_cjk import configure_cjk  # 懒
    from src.agents.src.graph import run_agent_demo  # 懒

    sample_full = _sample_path(sample)
    result = run_agent_demo(sample_path=sample_full, auto_mode=True, inject_sample_structure=True)
    dwg_path = result.get("final_dwg_path") or os.path.join(ROOT, "output", "ai_cad_output.dwg")

    import ezdxf
    configure_cjk()
    doc = ezdxf.readfile(dwg_path)
    msp = doc.modelspace()

    fig, ax = plt.subplots(figsize=(10, 7), dpi=110)
    ctx = RenderContext(doc)
    backend = MatplotlibBackend(ax)
    Frontend(ctx, backend).draw_layout(msp, finalize=True)
    setup_axes(ax)
    ax.set_title("AI-CAD 出图预览", fontsize=13)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


@app.get("/api/preview", response_class=Response)
def api_preview(sample: str = "residential_100sqm.json") -> Response:
    """返回样本 Agent 出图的 PNG bytes, Content-Type image/png。GUI 里不弹窗。"""
    png = render_sample_png(sample)
    return Response(content=png, media_type="image/png")


# ─── B2+B3 规则 DSL 域段: 拆到 bridge_dsl.py, include_router 挂载 ───
# 从 bridge.py 拆出 (超 500 红线), APIRouter 承载 /api/rules/dsl + /api/rules/validate +
# /api/rules/dsl/apply + /api/rules/backfill (设计器编辑+写回落盘 default.json)。端点路径 0 改动。
from src.gui.bridge_dsl import router as _dsl_router
app.include_router(_dsl_router)


# ─── F 碰撞/冲突域段 (M4 碰撞 + M5 冲突): 拆到 bridge_clash.py, include_router 挂载 ──
# 从 bridge.py 拆出 (超 500 红线), APIRouter 承载 /api/clash + /api/conflict +
# /api/dwg-marker-verify。跨段依赖 _load_sample_raw 已上提 bridge_common (B 段共用)。
# 端点路径 0 改动, 挂载即注册。
from src.gui.bridge_clash import router as _clash_router
app.include_router(_clash_router)


# ─── I M2 制图约定对齐工具域段: 扫真实 DWG → 图层/块名/ATTRIB 频率报告 ──
# 让业务专家在 GUI 面板里直接扫 DWG 看「各院用什么图层/块名画点位」, 把
# docs/element-upstream-contract.md §5 的 TBD 映射 dict 从填空题变选择题。
# 诚实边界 (不虚标): 只报频率 + 图层/块名清单, **不**判定「哪个图层=梁/柱/插座」
# — 判定是业务约定, 专家看报告回填映射 dict (改 JSON 即可), 不在本端点冒称自动映射。

_DWGSAMPLES = [
    "electrical_sample.dxf", "hvac_sample.dxf",
    "plumbing_sample.dxf", "structural_sample.dxf",
]


@app.get("/api/dwg-scan")
def api_dwg_scan(sample: str = "electrical_sample.dxf") -> dict:
    """M2 制图约定对齐: 扫 data/sample/<sample> (DXF) → 图层/块名/ATTRIB 频率报告。

    返回 {sample, layers, entity_type_totals, attrib_tags, layer_count,
          insert_total, available_samples, note}。
    sample 非 DXF / 不存在 → 诚实 404 (不崩不造假); 缺图层 → 空报告 (诚实两态)。
    懒 import: dwg_layer_scan 纯函数库 (依赖 ezdxf, 放函数体不触发模块收集冷启)。"""
    from src.agents.src.tools.dwg_layer_scan import (  # 懒
        scan_sample_reader, verify_dwg_scan_report)
    p = os.path.join(ROOT, "data", "sample", sample)
    if not os.path.exists(p) or not sample.endswith(".dxf"):
        raise HTTPException(404,
            f"样本不存在或非 DXF: {sample} "
            f"(可用: {', '.join(_DWGSAMPLES)})")
    report = scan_sample_reader(sample, ROOT)
    report["sample"] = sample
    report["available_samples"] = _DWGSAMPLES
    report["note"] = ("图层/块名频率报告 — 专家据此回填映射 dict "
                      "(docs/element-upstream-contract.md §5), 不判定 kind 归属")
    # 机制层自洽诊断 (仿 verify_clashes.clashes_consistent 范式): 扫出的报告
    # 聚合数字 (layer_count/insert_total/entity_type_totals) 与图层明细是否失步,
    # 失步不静默穿透 — 专家照着一份「数字对不上」的报告回填映射 dict 会被误导。
    check = verify_dwg_scan_report(report)
    report["scan_consistent"] = check["ok"]
    report["scan_issues"] = check["issues"]
    return report


# ─── G 人在回路确认闸域段: Agent 步进/确认接口 (原 src/server routes.py 并入) ───
# 配合 graph.py 的暂停机制 (interrupt + checkpointer + awaiting_confirmation_node)。
# 本段只负责 FastAPI 端: 登记人工决定 + 触发 resume。图侧真实「写 human_confirmations
# 并 resume」尚未定死, 故 _resume_agent_graph() 是预留对接点 (TODO)。内存态 (Phase 0)。

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

# session 级人在回路: thread_id → start_agent_run_suspended 返回的 session 快照
# (持有 saver/app/config/pending_task_ids), 供 resume 端点真续跑同一 thread。
_agent_sessions: dict[str, dict] = {}


class AgentRunRequest(BaseModel):
    """POST /agent/run 入参: 起一次真实图并挂起在确认点。"""
    sample: str = "residential_100sqm.json"


def _task_type_of(task_id: str, raw_data: dict) -> str:
    """从 task_id + raw_data 反查它属于哪类图元 (门/窗/梁/柱/管...), 供前端显示。

    纯 join 不重算出图: 优先看 raw_data 各元素类里有没有这个 id (门/窗 有 id),
    命中就取该类; 没命中退到 task_id 前缀 (door-/window-... 命名约定); 都查不到
    返回 'unknown' (诚实, 不瞎猜)。"""
    if isinstance(raw_data, dict):
        for key, kind in (
            ("doors", "door"), ("windows", "window"),
            ("structural_beams", "beam"), ("structural_columns", "column"),
            ("pipes", "pipe"), ("outlets", "outlet"), ("switches", "switch"),
        ):
            for e in raw_data.get(key, []) or []:
                if isinstance(e, dict) and e.get("id") == task_id:
                    return kind
    # task_id 前缀兜底 (cad_execute_node 的 task 命名约定)
    for prefix, kind in (
        ("door", "door"), ("window", "window"), ("beam", "beam"),
        ("column", "column"), ("pipe", "pipe"), ("outlet", "outlet"),
        ("switch", "switch"), ("hvac", "hvac"),
    ):
        if task_id.startswith(prefix):
            return kind
    return "unknown"


def _register_agent_task(run_id: str, task_id: str, node: str) -> None:
    """登记一个挂起在某 node、待人工确认的 task。内存态，供 status/confirm 用。"""
    _agent_task_confirms[task_id] = {"run_id": run_id, "node": node, "confirmed": False}


@app.post("/agent/run")
def agent_run(req: AgentRunRequest) -> dict:
    """起一次 auto_mode=False 的真实图, 跑到确认点挂起。

    session 级人在回路的入口: 真起图 (非演示) → 停在 awaiting_confirmation →
    返回 thread_id + 真实 pending_task_ids, 前端拿这些去 /agent/confirm 逐个确认。
    诚实边界: langgraph 未装/起图失败 → 400/500 + 原因, 不造假挂起。"""
    from src.agents.src.graph import start_agent_run_suspended  # 懒: langgraph 栈

    sample_path = _sample_path(req.sample)  # 样本不存在 → 400 (诚实报错)
    try:
        session = start_agent_run_suspended(sample_path=sample_path)
    except Exception as e:
        raise HTTPException(500, f"起图挂起失败: {e}")

    thread_id = session["thread_id"]
    _agent_sessions[thread_id] = session
    # 把真实 pending task 逐个登记, 让 /agent/status + /agent/confirm 能操作它们
    pending_ids = session["pending_task_ids"]
    for tid in pending_ids:
        _register_agent_task(thread_id, tid, "awaiting_confirmation")

    # 结构化 pending[] (接真实 CAD 数据源): 把 cad_execute_node 已产好的 cad_results
    # 按 task_id join 进响应, 让设计师看得懂每个待确认项是什么/出了什么。纯 join,
    # 不重算 (数据在 snapshot 里躺着)。非 pending_confirm 的 task 不进 pending[]。
    cad_results = session["snapshot"].get("cad_results", [])
    result_by_task = {r.get("task_id"): r for r in cad_results if isinstance(r, dict)}
    pending_detail = []
    for tid in pending_ids:
        r = result_by_task.get(tid, {})
        pending_detail.append({
            "task_id": tid,
            "type": _task_type_of(tid, session.get("snapshot", {}).get("raw_data", {})),
            "description": r.get("description", ""),
            "result": r,  # cad_execute_node 产的该 task 出图结果 (status/count/...)
        })

    return {
        "thread_id": thread_id,
        "sample": req.sample,
        "node": "awaiting_confirmation",
        # 向后兼容: 老字段原样保留 (现有 session 测试断言这些)
        "pending_task_ids": pending_ids,
        "pending_task_count": len(pending_ids),
        "cad_result_count": len(cad_results),
        # 新增: 结构化 pending 详情 + 图面预览关联 (前端对照看每个待确认 task)
        "pending": pending_detail,
        "preview_url": f"/api/preview?sample={req.sample}",
        "message": "图已挂起在确认点, 请对 pending_task_ids 逐个 /agent/confirm。"
                   if pending_ids else "无待确认 task, 图已跑到底。",
    }


def _resume_agent_graph(run_id: str, confirmed: bool, modifications: Optional[dict]) -> dict:
    """触发 graph 的人回路确认闸: 按 confirmed 放行→resume 续跑。

    两级通路 (诚实区分 session 级 vs 演示级):
      1. **session 级** (run_id 是 /agent/run 起的真实挂起 run): 用存住的 session
         真续跑同一 thread (start_agent_run_suspended → resume_agent_run),
         放行 confirmed 对应的 task。这是设计师对真实出图结果的确认。
      2. **演示级** (无 session 的 run_id, 前端直接点确认): 回退到
         run_agent_with_confirmation 用默认样本跑一次挂起→放行→resume, 证明链路通。
    诚实边界: confirmed=False 只登记不 resume; langgraph 未装/失败 → reason 降级, 不造假。
    """
    if not confirmed:
        return {"resumed": False, "reason": "pending_confirm (confirmed=False, 图继续挂起)"}

    try:
        from src.agents.src.graph import (  # 懒: langgraph 栈
            resume_agent_run, run_agent_with_confirmation)
    except Exception as e:
        return {"resumed": False, "reason": f"agent_graph_not_available: {e}"}

    # ── 1. session 级: 有真实挂起 session 就续跑它 (设计师确认的是真实出图结果) ──
    session = _agent_sessions.get(run_id)
    if session is not None:
        try:
            result = resume_agent_run(session, release_all=True)
        except Exception as e:
            return {"resumed": False, "reason": f"agent_graph_resume_failed: {e}"}
        return {
            "resumed": True,
            "session": True,
            "thread_id": run_id,
            "modifications": modifications,
            "rule_violation_count": len(result.get("rule_violations", [])),
            "final_dwg_path": result.get("final_dwg_path"),
            "export_status": result.get("export_status"),
        }

    # ── 2. 演示级: 无 session 回退到默认样本跑通链路 ──
    try:
        result = run_agent_with_confirmation(confirm_all=True)
    except Exception as e:
        return {"resumed": False, "reason": f"agent_graph_resume_failed: {e}"}

    return {
        "resumed": True,
        "session": False,
        "thread_id": run_id,
        "modifications": modifications,
        "rule_violation_count": len(result.get("rule_violations", [])),
        "final_dwg_path": result.get("final_dwg_path"),
        "export_status": result.get("export_status"),
    }


@app.post("/agent/confirm")
def agent_confirm(data: AgentConfirmRequest) -> dict:
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
def agent_status() -> dict:
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


# ─── H 在线协同域段 (M5 持久层协议: 快照 + 本地锁演示) ──────────
# 从 bridge.py 拆到 bridge_collab.py (bridge 1575 行超 500 红线), 用 APIRouter
# 承载本域段全部 /api/collab/* + /api/permission/* 端点, 这里 include_router 挂载。
# 端点路径 0 改动, 段间无调用依赖 (已核实 H 段自包含), 拆物理文件不破坏既有端点。
from src.gui.bridge_collab import router as _collab_router  # 拆出的 H 域段
app.include_router(_collab_router)
# 协同 state 路径的单一事实源 (bridge_collab 端点运行时读本名, 测试 patch 此处即对端点生效)。
# 拆出 H 段后保留该名字在 bridge, 锚定 test_bridge_collab_snapshot 的 monkeypatch 契约。
_COLLAB_STATE_PATH = os.path.join(ROOT, "data", "collab", "state.json")

# ─── E 入口域段: 兜底落地页 + 端口探测 + uvicorn 起法 ─────────────
# (fork E 追加, 不碰 B/C/D 段。CORS 已在上, 这里补 127.0.0.1 各端口 origin。)
from fastapi.responses import HTMLResponse

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000", "http://localhost:3000",
        "http://127.0.0.1:5173", "http://localhost:5173",
        "http://127.0.0.1:8642", "http://localhost:8642",
    ],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

DEFAULT_BRIDGE_PORT = 8642


def find_free_port(start: int = DEFAULT_BRIDGE_PORT, host: str = "127.0.0.1",
                   max_tries: int = 50) -> int:
    """从 start 起找第一个可用端口; 全占回 start。"""
    import socket
    for port in range(start, start + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    return start


def run_bridge(host: str = "127.0.0.1", port: Optional[int] = None) -> int:
    """起桥 (阻塞)。返回实际监听端口。"""
    import uvicorn
    actual = port if port is not None else find_free_port()
    uvicorn.run(app, host=host, port=actual, log_level="warning")
    return actual


_LANDING_HTML = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI-CAD 施工图深化 · 控制台</title>
<style>
  body{font-family:'Segoe UI','PingFang SC','Microsoft YaHei',system-ui;max-width:720px;margin:48px auto;padding:0 24px;color:#1c2540;background:#f5f7fc}
  h1{border-bottom:3px solid #0f3460;padding-bottom:10px;margin-bottom:8px}
  .ok{color:#1a9866;font-weight:600}
  .card{background:#fff;border-left:4px solid #0f3460;padding:18px 22px;margin:18px 0;border-radius:8px;box-shadow:0 1px 4px rgba(15,52,96,.08)}
  code{background:#eef1f8;padding:2px 6px;border-radius:4px;color:#0f3460}
  .seg{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:600;margin-right:6px}
  .on{background:#e3f7ee;color:#1a9866}.off{background:#f3f4f8;color:#8b93a8}
</style></head><body>
<h1>AI-CAD 施工图深化 · 控制台</h1>
<p class="ok">● 引擎桥已就绪</p>
<div class="card">
  <p>这是 <b>FastAPI 引擎桥</b> 的兜底落地页。GUI 前端 (React/Electron) 应指向本桥, 通过 <code>/api/*</code> 取数。</p>
  <p>能力段: <span class="seg on">规则</span><span class="seg on">Agent</span><span class="seg on">RAG</span></p>
  <p>前端 dev 地址 (若已起): <code>http://127.0.0.1:3000</code> 或 <code>http://127.0.0.1:5173</code></p>
</div>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
def landing() -> HTMLResponse:
    """E 段兜底页: 引擎就绪确认 + 指向前端地址。"""
    return HTMLResponse(_LANDING_HTML)


if __name__ == "__main__":
    run_bridge()
