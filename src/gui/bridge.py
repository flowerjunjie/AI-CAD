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


# ─── B 规则域段 ──────────────────────────────────────────────────
# /api/rules + /api/rule-violations + /api/health。
# 引擎/元素模型懒加载 (放函数体), 模块收集期不 import src.rules 全量规则。
# 红线: 只读调用 engine, 不改 src/rules 任何文件。


def _load_rules_module() -> object:
    """触发全部 @register_rule 注册 + 拉 DSL 规则进全局引擎 (懒)。"""
    import src.rules.src.residential.doors  # noqa: F401
    import src.rules.src.residential.windows  # noqa: F401
    import src.rules.src.residential.corridors  # noqa: F401
    import src.rules.src.residential.rooms  # noqa: F401
    import src.rules.src.residential.areas  # noqa: F401
    import src.rules.src.residential.stairs  # noqa: F401
    import src.rules.src.residential.daylight  # noqa: F401
    import src.rules.src.fire_safety.corridors  # noqa: F401
    import src.rules.src.fire_safety.exits  # noqa: F401
    import src.rules.src.accessibility.ramps  # noqa: F401
    import src.rules.src.accessibility.entrances  # noqa: F401

    from src.rules.src.engine import get_engine

    engine = get_engine()
    # DSL 规则 (default.json, dsl_only 判据) upsert 进同一引擎 — 复用 agent 侧逻辑
    try:
        from src.agents.src.nodes import cad_rule_export as _cre
        _cre._ensure_dsl_rules_loaded(engine)
    except Exception:
        pass  # DSL 段挂了不阻塞 hardcoded 规则透出
    return engine


def _rule_source(rule: object) -> str:
    """source: 带 dsl_only 属性/来自 DSL 的 = dsl, 否则 = hardcoded。"""
    if getattr(rule, "dsl_only", False):
        return "dsl"
    try:
        from src.rules.src.dsl import ParametricRule
        if isinstance(rule, ParametricRule):
            return "dsl"
    except Exception:
        pass
    return "hardcoded"


@app.get("/api/rules")
def api_rules() -> List[dict]:
    engine = _load_rules_module()
    out = []
    for r in engine.list_rules():
        out.append({
            "rule_id": r.rule_id,
            "name": r.name,
            "code_ref": r.code_ref,
            "severity": r.severity.value if hasattr(r.severity, "value") else str(r.severity),
            "source": _rule_source(r),
            "enabled": True,
        })
    return out


@app.get("/api/rule-violations")
def api_rule_violations() -> List[dict]:
    """实测演示违规: 0.6m 户门 vs residential-door-main-width (照 run.py bad_door 写法)。"""
    import src.rules.src.residential.doors  # noqa: F401  (触发注册)
    from src.rules.src.engine import get_engine
    from src.rules.src.residential.doors import Door

    engine = get_engine()
    bad_door = Door(id="gui-demo-d1", width_m=0.6, room_type="entrance", location=(0, 0))
    violations = engine.check([bad_door], rule_ids=["residential-door-main-width"])
    return [v.to_dict() for v in violations]


@app.get("/api/health")
def api_health() -> dict:
    """引擎探活: 规则计数 (hardcoded/dsl) + rag/llm 布尔占位给前端画徽章。"""
    try:
        engine = _load_rules_module()
        counts = {"hardcoded": 0, "dsl": 0}
        for r in engine.list_rules():
            counts[_rule_source(r)] += 1
        rules_total = len(engine.list_rules())
    except Exception:
        rules_total, counts = 0, {"hardcoded": 0, "dsl": 0}
    return {
        "status": "ok",
        "phase": "Phase 6",
        "modules": {
            "rules": rules_total,
            "dsl": counts.get("dsl", 0),
            "hardcoded": counts.get("hardcoded", 0),
            "rag": rag_health(),
            "llm": False,  # 占位: LLM 冷启动 100s, 探活不真起, 前端按 False 置灰
        },
    }


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
