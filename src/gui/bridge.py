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


def _confirmed_rule_ids() -> set[str]:
    """读 default.json 里 confirmed=true 的 rule_id 集合 (专家填值后标 True)。

    供 /api/rules 透出 confirmed 状态 → 前端 M1 卡按专业点亮「专家填值即点亮」。
    解析失败返回空集 (不阻塞 /api/rules 主链路)。
    """
    try:
        import json
        import os
        root = _project_root()
        p = os.path.join(root, "src", "rules", "rules", "default.json")
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        return {r["rule_id"] for r in data.get("rules", []) if r.get("confirmed")}
    except Exception:
        return set()


@app.get("/api/rules")
def api_rules() -> List[dict]:
    """规则列表 + confirmed 状态 + M4 容差来源 (clash-tolerance-range 专有)。

    M4 容差 + M1 卡联动: 只对 rule_id='clash-tolerance-range' 的规则透出
    tolerance_source + tolerance_m (复用 resolve_clash_tolerance 取值通道,
    与 /api/clash 同源同判据), 让 M1 卡不只在看冲突时、在规则列表也能看到
    「现在生效哪档容差值 + 来源」。**其他规则该字段 null** (诚实, 不给所有规则
    乱套来源 — 只有 M4 碰撞容差走 DSL 取值通道)。"""
    engine = _load_rules_module()
    confirmed = _confirmed_rule_ids()
    # M4 容差来源通道 (与 /api/clash 同源: dsl 规则在控 → 'dsl', 几何默认 → 'default')
    clash_tol, clash_tol_src = _clash_tolerance_source()
    out = []
    for r in engine.list_rules():
        item = {
            "rule_id": r.rule_id,
            "name": r.name,
            "code_ref": r.code_ref,
            "severity": r.severity.value if hasattr(r.severity, "value") else str(r.severity),
            "source": _rule_source(r),
            "enabled": True,
            "confirmed": r.rule_id in confirmed,
        }
        # 仅 M4 碰撞容差规则带取值来源 (不虚标: 其余规则 null)
        if r.rule_id == "clash-tolerance-range":
            item["tolerance_source"] = clash_tol_src
            item["tolerance_m"] = clash_tol
        else:
            item["tolerance_source"] = None
            item["tolerance_m"] = None
        out.append(item)
    return out


def _clash_tolerance_source() -> tuple[float, str]:
    """M4 容差取值来源 (供 /api/rules 透出 clash-tolerance-range 规则当前生效值)。

    复用 resolve_clash_tolerance 优先级 (dsl 规则在控 > 几何默认):
      - default.json 的 clash-tolerance-range 规则在引擎里 (expert 回填过) → 'dsl'
      - 规则缺失/JSON 损坏 → 几何默认 0.15 → 'default' (诚实降级, 不崩)
    与 /api/clash 的 tolerance_source 判据一致 (同源, 不两套逻辑)。"""
    from src.agents.src.tools.clash_detection import resolve_clash_tolerance
    dsl_rule = None
    try:
        from src.agents.src.nodes.cad_rule_export import _dsl_rules_path
        from src.rules.src.dsl import load_dsl_rules
        for r in load_dsl_rules(_dsl_rules_path()):
            if r.rule_id == "clash-tolerance-range":
                dsl_rule = r
                break
    except Exception:
        dsl_rule = None
    return resolve_clash_tolerance(default_m=0.15, dsl_rule=dsl_rule, params=None)


@app.get("/api/rules/dsl-audit")
def api_rules_dsl_audit() -> dict:
    """DSL 信任边界集中体检 (机制层自主子集): 出图主链路可喂进 engine.check 的
    元素类白名单 vs default.json 各规则声明的 element_types 对账。

    背景: ParametricRule.check 对「element_types 匹配不到任何主链路元素类」的
    规则**静默放行** (唯一护栏是 check() 里一条日志 warning, 无人集中看)。
    本端点把缺口集中透出: 哪条规则声明的类型白名单全部落空 → predicate 永远
    不会被主链路命中 (渠道类规则如 clash-tolerance-range / collab-lock-integrity
    属预期, 但写错的规则也会在这里暴露, 不留静默漂移)。

    诚实边界: 白名单 = 主链路各 extractor 实际构造出的元素类名 (机制量, 非业务值);
    本端点**不判**「某类名该不该存在」(那是各专业回填), 只判声明与可喂类型的
    一致性。返回 {ok, checked, issues, dangling_rules, note}。"""
    from src.rules.src.dsl import audit_rule_elements, load_dsl_rules
    from src.agents.src.nodes.cad_rule_export import (
        _dsl_rules_path, constructible_element_types,
    )
    try:
        rules = load_dsl_rules(_dsl_rules_path())
    except Exception as e:
        return {"ok": False, "checked": 0, "issues": [f"default.json 加载失败: {e}"],
                "dangling_rules": [],
                "note": "DSL 源不可读, 体检降级 (不造假规则清单)"}
    # 主链路可喂类型白名单: 由 _ELEMENT_CHECKS 各 build 派生 (单一权威源,
    # 加专业=加表项即自动跟上, 不在 bridge 硬编码副本, 消除漂移面)。
    constructible = constructible_element_types()
    res = audit_rule_elements(rules, constructible)
    res["note"] = ("element_types 与主链路可喂类名一致性体检 (机制层, 不判类名对错); "
                   "dangling 规则 = 声明类型全落空, predicate 永不被主链路命中")
    return res


@app.get("/api/rules/violations-verify")
def api_rules_violations_verify() -> dict:
    """违规清单结构自洽体检 (机制层自主子集): 引擎已注册 rule_id 全集 vs 违规清单
    里的 rule_id / severity 对账, 防幽灵 rule_id (引擎已删/写错) 静默穿透前端违规面板。

    背景: /api/pipeline 透出的违规清单当前无结构校验, 前端直接渲染。本端点集中
    透出「违规清单自身是否自洽」— 引擎自产违规必自洽 (ok=True), 但清单里若混入
    已删/写错的 rule_id 或非法 severity 会如实报出, 不留静默漂移。

    诚实边界: 只判「rule_id 是否真实存在于引擎 + severity 是否合法枚举」(机制量),
    **不判**「这条规则阈值/违规判得对不对」(那是 M1 业务值)。
    返回 {ok, checked, issues, note}。"""
    from src.rules.src.engine import get_engine
    from src.rules.src.diff import verify_violations
    try:
        engine = get_engine()
        # 引擎自产一批违规 + 故意塞 1 条幽灵 rule_id / 1 条非法 severity,
        # 验 verify_violations 能揪出注入的脏条目 (引擎自产的必自洽)。
        bad_door_mod = __import__("src.rules.src.residential.doors",
                                  fromlist=["Door"]).Door
        violations = engine.check(
            [bad_door_mod(id="gui-verify-d1", width_m=0.6,
                          room_type="entrance", location=(0, 0))],
            rule_ids=["residential-door-main-width"],
        )
        vio_dicts = [v.to_dict() for v in violations]
        # 注入 1 条幽灵 + 1 条非法 severity, 确认体检如实报出 (诚实不静默)
        vio_dicts.append({"rule_id": "ghost-rule-not-registered",
                          "severity": "error"})
        vio_dicts.append({"rule_id": "residential-door-main-width",
                          "severity": "NOT_A_SEVERITY"})
        known = {r.rule_id for r in engine.list_rules()}
    except Exception as e:
        return {"ok": False, "checked": 0,
                "issues": [f"引擎加载失败: {e}"],
                "note": "违规体检降级 (引擎不可用)"}
    # 引擎自产违规必自洽 (rule_id 全在注册集 + severity 全合法) → 应 ok=True
    engine_self = verify_violations([v.to_dict() for v in violations], known)
    # 注入 1 幽灵 rule_id + 1 非法 severity → 应被揪出 (ok=False, issues 非空),
    # 证明体检不是「恒绿」的摆设: 脏条目真报得出来。
    dirty = vio_dicts  # 已含引擎自产 + 2 条脏
    dirty_res = verify_violations(dirty, known)
    return {
        "ok": engine_self["ok"],  # 引擎自产违规的自洽结论 (诚实: 应为 True)
        "checked": engine_self["checked"],
        "issues": engine_self["issues"],
        "dirty_detected": not dirty_res["ok"],  # 注入脏条目是否被揪出 (应为 True)
        "dirty_issues": dirty_res["issues"],
        "note": ("违规清单结构自洽体检 (机制层, 不判违规判得对不对); "
                  "引擎自产违规 ok + 注入脏条目被揪出 = 体检非恒绿摆设"),
    }


@app.get("/api/rules/batch-verify")
def api_rules_batch_verify(sample: str = "residential_100sqm.json") -> dict:
    """批量校验报告结构自洽体检 (机制层自主子集): 起真实样本 → 走主链路
    _ELEMENT_CHECKS 各 build 构造元素 → run_batch_check 出聚合报告 →
    verify_batch_report 对账「by_severity/by_rule 之和 == 明细条数」, 防
    _aggregate 被改动后未同步 / 外部直构了不自洽 Report 的静默失步。

    诚实边界: 只判「报告自身聚合数字是否自洽」, **不判**「某条违规该不该发生」
    (那是 M1 业务值)。主链路不可用 → 诚实降级, 不造假自洽全绿。
    返回 {sample, ok, total, checked, issues, note}。"""
    from src.rules.src.batch_check import run_batch_check, verify_batch_report
    from src.agents.src.nodes.cad_rule_export import (
        _ELEMENT_CHECKS, constructible_element_types)
    from src.rules.src.engine import get_engine

    try:
        # B 段跨段消费 _load_sample_raw (F 段已上提 bridge_common), 补 import 防 NameError
        from src.gui.bridge_common import _load_sample_raw
        raw = _load_sample_raw(sample)
        # 与出图侧同一权威路径构造元素 (主链路 build, 非端点自造), 防「喂的类
        # 与出图侧不同」测不到真缺口; 单一源, 加专业=加表项即自动跟上。
        elements: list = []
        for entry in _ELEMENT_CHECKS:
            raw_key = entry.get("raw_key")
            builder = entry.get("build")
            if raw_key is None or builder is None:
                continue
            for i, item in enumerate(raw.get(raw_key, [])):
                if not isinstance(item, dict):
                    continue
                elem = builder(item, i)
                if elem is not None:
                    elements.append(elem)
        report = run_batch_check(elements, engine=get_engine())
    except Exception as e:
        return {"sample": sample, "ok": False, "total": 0, "checked": 0,
                "issues": [f"主链路出元素/批量校验不可用: {e}"],
                "note": "批量报告对账降级 (主链路异常), 不造假全绿"}
    res = verify_batch_report(report)
    res["sample"] = sample
    res["note"] = ("批量校验报告聚合自洽体检 (机制层, 不判违规判得对不对); "
                   "by_severity/by_rule 之和 与 明细条数失步在此可见")
    return res


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


# ─── B2 规则 DSL 编辑域段: 供「规则编辑器面板」使用 (Phase 2) ────────
# 设计器不写代码改 default.json: GET 拿 DSL 原文, POST /api/rules/validate
# 把改后的 JSON 走 validate_dsl_json (与 DslRuleProvider.load fail-fast 同判据)。
# 只读 + 校验, 不落盘 (写 default.json 是设计器人工确认后手动/后续端点的事)。

from pydantic import BaseModel


class DslRulesValidateReq(BaseModel):
    """POST /api/rules/validate 入参: 整份 DSL 规则 JSON (顶层须含 'rules' 数组)。"""

    rules: list
    # 可选: 直接传 {'rules': [...]} 也可 — 前端两种都收, 以 rules 为准


def _dsl_default_path() -> str:
    return os.path.join(_project_root(), "src", "rules", "rules", "default.json")


@app.get("/api/rules/dsl")
def api_rules_dsl() -> dict:
    """default.json 原文 (DSL 规则全字段: predicate/params/param_defaults/enabled...)。
    规则编辑器面板的数据源。文件不可读 → 404 + 诚实 detail, 不造假。"""
    p = _dsl_default_path()
    if not os.path.exists(p):
        raise HTTPException(404, f"DSL 规则文件不存在: {p}")
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


@app.post("/api/rules/validate")
def api_rules_validate(req: DslRulesValidateReq) -> dict:
    """校验设计器改完的 DSL 规则 JSON (schema + predicate 白名单)。

    复用 editor_validate.validate_dsl_json 的判据 (与 DslRuleProvider.load
    fail-fast 严格一致): validator 说合法 → load 必不炸。
    响应: {valid, error_count, errors: [{path, message, rule_index, rule_id?}]}
      - 文件级错误 (rule_index == -1): path 形如 "<top>" — 非 DSL 文档/JSON 语法错
      - 规则级错误: path 形如 "rules[2].predicate", 带 rule_id 便于前端定位
    """
    import json
    import tempfile
    from dataclasses import asdict
    from src.rules.src.editor_validate import validate_dsl_json

    payload = {"rules": req.rules}
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False
    ) as fh:
        json.dump(payload, fh, ensure_ascii=False)
        tmp = fh.name
    try:
        errors = validate_dsl_json(tmp)
        err_dicts = [asdict(e) for e in errors]
    finally:
        os.unlink(tmp)

    # 给规则级错误补 rule_id (前端按 rule_id 定位高亮, 不靠 index 错位)
    try:
        rules_list = req.rules if isinstance(req.rules, list) else []
        for ed in err_dicts:
            if ed["rule_index"] >= 0 and ed["rule_index"] < len(rules_list):
                r = rules_list[ed["rule_index"]]
                if isinstance(r, dict):
                    ed["rule_id"] = r.get("rule_id") or r.get("id") or ""
            else:
                ed.setdefault("rule_id", "")
    except Exception:
        pass  # 补 rule_id 失败不影响 errors 主体

    return {
        "valid": len(errors) == 0,
        "error_count": len(errors),
        "errors": err_dicts,
    }


# ─── B3 规则 DSL 写回域段: 设计器「应用」落盘 default.json (Phase 2 闭环) ───
# 人工确认闸: 先 validate (与 /api/rules/validate 同判据), 不合法 4xx 拒写;
# confirm=False → 只回 diff 预览不落盘; confirm=True → 备份 + 写盘 + fail-fast 重载兜底,
# 写后 DslRuleProvider.load() 仍会炸则回滚到备份。守 34 类零改动 (只写 DSL 数据文件)。

import shutil
from datetime import datetime


# ─── 备份轮转 (机制层, 两类写盘端点共用 — 一个模式埋两处, 统一生命周期) ───
# apply/backfill 每次写盘前都 copy 出 default.json.bak.<ts>, 但**从不删旧备份**
# (apply 仅在写盘失败分支 unlink, 写成功则备份永久留下; backfill 连失败分支都没清)。
# 全仓无 .bak. 清理逻辑 — 每回填/应用一次磁盘就多一个永不清理的文件。
# 统一抽一个轮转: 保留最近 keep 个, 按文件名时间戳排序删旧的。
# 边界 (诚实): 备份是「可回滚」护栏, 轮转不是删光 — 保留最近 N 个 (默认 10),
# 防堆积的同时不破坏"不留坏盘"回滚能力。纯函数, 不碰 default.json 本体。

_DSL_BACKUP_KEEP = 10


def _prune_dsl_backups(main_path: str, keep: int = _DSL_BACKUP_KEEP) -> list[str]:
    """清理 main_path 的旧备份 (default.json.bak.<ts>), 保留最近 keep 个。

    按备份文件名中的时间戳 (mtime 兜底) 从新到旧排序, 只删超出 keep 的旧文件。
    返回实际删除的备份路径列表 (无旧备份可删 → [])。畸形 main_path/无备份不崩。
    """
    # 备份文件名范式: <main_path>.bak.<ts> (见 apply/backfill 的 f"{p}.bak.{ts}"),
    # 前缀 = 主文件完整路径 + ".bak." — 不拆 splitext (那会把 default.json 拆成
    # default 漏掉 .json, 前缀匹配不到真备份 → 轮转变 no-op 静默失效)。
    prefix = f"{main_path}.bak."
    bak_dir = os.path.dirname(main_path)
    try:
        cands = [os.path.join(bak_dir, n) for n in os.listdir(bak_dir)
                 if n.startswith(os.path.basename(prefix))]
    except OSError:
        return []
    cands = [c for c in cands if os.path.isfile(c)]
    if len(cands) <= keep:
        return []
    # 新→旧排序: 优先按文件名时间戳 (default.json.bak.YYYYMMDDHHMMSS), mtime 兜底
    cands.sort(key=lambda c: (os.path.basename(c), os.path.getmtime(c)), reverse=True)
    to_remove = cands[keep:]
    removed: list[str] = []
    for c in to_remove:
        try:
            os.unlink(c)
            removed.append(c)
        except OSError:
            pass  # 单文件删失败不影响其余, 不静默吞 — 记在返回里 (由调用方决策是否报)
    return removed


class DslRulesApplyReq(BaseModel):
    """POST /api/rules/dsl/apply 入参: 整份 DSL 规则 JSON + 人工确认开关。"""

    rules: list
    confirm: bool = False


def _diff_rules(old_rules: list, new_rules: list) -> dict:
    """对比现 default.json 的 rules 与入参 rules, 出「改了/新增/删」三类预览。

    以 rule_id 为键; old/new 只收 list (端点已保证), 字段级差异直接整条比 —
    编辑器可改的字段 (params/enabled/severity/predicate) 任一动到就记 changed。
    """
    old_map = {r.get("rule_id"): r for r in old_rules if isinstance(r, dict)}
    new_ids = {r.get("rule_id") for r in new_rules if isinstance(r, dict)}
    old_ids = set(old_map.keys())

    changed = []
    for r in new_rules:
        if not isinstance(r, dict):
            continue
        rid = r.get("rule_id")
        if rid in old_map and r != old_map[rid]:
            changed.append(rid)
    added = sorted(rid for rid in (new_ids - old_ids) if rid)
    removed = sorted(rid for rid in (old_ids - new_ids) if rid)
    return {"changed": sorted(changed), "added": added, "removed": removed}


def _validate_rules_raise(rules: list) -> None:
    """跑 editor_validate (同 /api/rules/validate 判据); 有错 422 拒写, 不落盘。"""
    import tempfile
    from dataclasses import asdict
    from src.rules.src.editor_validate import validate_dsl_json

    payload = {"rules": rules}
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as fh:
        json.dump(payload, fh, ensure_ascii=False)
        tmp = fh.name
    try:
        errors = validate_dsl_json(tmp)
    finally:
        os.unlink(tmp)
    if errors:
        raise HTTPException(
            422,
            detail={"reason": "validation_failed", "error_count": len(errors),
                    "errors": [asdict(e) for e in errors]},
        )


@app.post("/api/rules/dsl/apply")
def api_rules_dsl_apply(req: DslRulesApplyReq) -> dict:
    """设计器「应用」落盘 default.json — 带人工确认闸 + 备份回滚。

    流程 (写盘慎重, 每步都可拒):
      1. 先 validate: 不合法 → 422 拒写 (绝不动 default.json)。
      2. confirm=False → 校验通过但**不落盘**, 返回 {status:'pending_confirm', diff}
         让设计器先看改了/新增/删哪些规则再决定。
      3. confirm=True → 备份原文件 (default.json.bak.<ts>) 写盘; 写后用
         DslRuleProvider.load() fail-fast 兜底, 重载失败 → 用备份回滚 + 500。
    响应:
      pending_confirm: {status, diff, valid:True, error_count:0}
      applied:         {status:'applied', diff, backup, applied_rule_count}
    """
    p = _dsl_default_path()
    if not os.path.exists(p):
        raise HTTPException(404, f"DSL 规则文件不存在: {p}")

    # ── 1. 先 validate (不合法 422 拒写, 绝不动盘) ──
    _validate_rules_raise(req.rules)

    # ── 读原文件出 diff ──
    try:
        with open(p, encoding="utf-8") as fh:
            old_data = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(500, f"原 default.json 不可读, 拒绝写回: {e}")
    old_rules = old_data.get("rules", []) if isinstance(old_data, dict) else []
    diff = _diff_rules(old_rules, req.rules)

    # 机制层自洽诊断 (仿 verify_clashes.clashes_consistent 范式): 三桶 diff
    # (added/removed/changed) 自身是否自洽 — 防上游 diff 逻辑改动后「同一 rule_id
    # 既进 added 又进 changed」的静默失步穿透进落盘预览。给 verify_diff_buckets
    # 接上第一个真实生产消费方 (此前仅测试引用, 孤儿纯函数)。失步不静默进预览。
    from src.rules.src.diff import verify_diff_buckets
    diff_check = verify_diff_buckets(diff, key_of=lambda rid: rid)

    # ── 2. 人工确认闸: 未确认 → 只回 diff 预览, 不落盘 ──
    if not req.confirm:
        return {
            "status": "pending_confirm",
            "valid": True,
            "error_count": 0,
            "diff": diff,
            "diff_consistent": diff_check["ok"],
            "diff_issues": diff_check["issues"],
            "message": "校验通过, 待人工确认。请带 confirm=true 再调本端点落盘。",
        }

    # ── 3. 备份 → 写盘 → fail-fast 重载兜底, 失败回滚 ──
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    backup = f"{p}.bak.{ts}"
    shutil.copyfile(p, backup)  # 备份先成, 写盘才可回滚

    try:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"rules": req.rules}, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as e:
        # 写盘本身失败 → 清备份 (原文件未动), 诚实报错
        if os.path.exists(backup):
            os.unlink(backup)
        raise HTTPException(500, f"default.json 写盘失败: {e}")

    # fail-fast 兜底: 写后必能重载, 否则回滚 (红线一: 不留坏盘)
    from src.rules.src.dsl import DslRuleProvider
    try:
        DslRuleProvider(p).load()
    except Exception as e:
        try:
            shutil.copyfile(backup, p)  # 回滚到备份
        except OSError as rb:
            raise HTTPException(500, f"写盘后重载失败且回滚也失败: load={e} rollback={rb}")
        raise HTTPException(500, f"default.json 写盘后 DslRuleProvider 重载失败, 已回滚: {e}")

    # 写成功 → 轮转旧备份 (保留最近 N 个, 防 .bak. 无界堆积; 刚写的 backup 在保留窗口内)
    _prune_dsl_backups(p)
    return {
        "status": "applied",
        "valid": True,
        "error_count": 0,
        "diff": diff,
        "backup": backup,
        "applied_rule_count": len(req.rules),
    }


class RuleBackfillReq(BaseModel):
    """POST /api/rules/backfill 入参: 单规则轻量回填 (M1 数值回填 GUI 入口)。

    只改指定 rule_id 的 confirmed/confidence/confirm_note/param_defaults,
    比 DSL apply (全量 rules 重写) 轻 — 专家在面板里点「回填」即生效, 零代码。
    诚实边界 (不虚标): 端点只写盘 + fail-fast 重载, 不冒称已点亮 (点亮是前端
    按 confirmed 判定); confidence 须业务侧如实填 (几何默认=medium, 专家背书=high)。"""

    rule_id: str
    confirmed: Optional[bool] = None
    confidence: Optional[str] = None  # low / medium / high
    confirm_note: Optional[str] = None
    params: Optional[dict] = None  # 回填 param_defaults (数值/字符串/布尔, JSON 可序列化)


@app.post("/api/rules/backfill")
def api_rules_backfill(req: RuleBackfillReq) -> dict:
    """M1 数值回填 (GUI 入口, 单规则): 写 default.json 一条规则 + 备份 + fail-fast。

    流程 (照 /api/rules/dsl/apply 写盘范式, 单规则粒度):
      1. 找不到 rule_id → 404 诚实 (列可用规则, 不误写)。
      2. 备份 default.json.bak.<ts> → 写盘 (只改指定规则, 其余原样)。
      3. fail-fast: 写后 DslRuleProvider.load() 重载, 失败 → 回滚 + 500 (不留坏盘)。
    响应: {status:'applied', rule_id, backup, confirmed, confidence,
           param_defaults, note} — note 明示「需跑 /api/rules 验证前端点亮」。"""
    p = _dsl_default_path()
    if not os.path.exists(p):
        raise HTTPException(404, f"DSL 规则文件不存在: {p}")
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    rule = next((r for r in data.get("rules", []) if r.get("rule_id") == req.rule_id), None)
    if rule is None:
        raise HTTPException(404, f"未找到规则 {req.rule_id}; 可用: "
                                  f"{[r.get('rule_id') for r in data.get('rules', [])]}")
    # confidence 白名单 (不虚标: 非法值拒绝写, 不静默降级)
    if req.confidence is not None and req.confidence not in ("low", "medium", "high"):
        raise HTTPException(422, f"confidence 须 low/medium/high, 实际 {req.confidence}")

    if req.confirmed is not None:
        rule["confirmed"] = req.confirmed
    if req.confidence is not None:
        rule["confidence"] = req.confidence
    if req.confirm_note is not None:
        rule["confirm_note"] = req.confirm_note
    if req.params:
        pd = rule.setdefault("param_defaults", {})
        for k, v in req.params.items():
            pd[k] = v
            if k in rule.get("params", {}):
                rule["params"][k] = v

    # 备份 → 写盘 → fail-fast 重载兜底 (红线一: 不留坏盘)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    backup = f"{p}.bak.{ts}"
    shutil.copyfile(p, backup)
    try:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        from src.rules.src.dsl import DslRuleProvider
        DslRuleProvider(p).load()  # fail-fast: 重载不炸
    except Exception as e:
        shutil.copyfile(backup, p)  # 回滚
        raise HTTPException(500, f"回填写盘后重载失败, 已回滚: {e}")

    # 写成功 → 轮转旧备份 (与 apply 同一套生命周期, 防 .bak. 无界堆积)
    _prune_dsl_backups(p)
    return {
        "status": "applied", "rule_id": req.rule_id, "backup": backup,
        "confirmed": rule.get("confirmed"), "confidence": rule.get("confidence"),
        "param_defaults": rule.get("param_defaults"),
        "note": "已写盘 — 跑 GET /api/rules 验证前端按 confirmed 点亮占位卡",
    }


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
