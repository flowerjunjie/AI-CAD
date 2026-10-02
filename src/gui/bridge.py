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
    engine = _load_rules_module()
    confirmed = _confirmed_rule_ids()
    out = []
    for r in engine.list_rules():
        out.append({
            "rule_id": r.rule_id,
            "name": r.name,
            "code_ref": r.code_ref,
            "severity": r.severity.value if hasattr(r.severity, "value") else str(r.severity),
            "source": _rule_source(r),
            "enabled": True,
            "confirmed": r.rule_id in confirmed,
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

    # ── 2. 人工确认闸: 未确认 → 只回 diff 预览, 不落盘 ──
    if not req.confirm:
        return {
            "status": "pending_confirm",
            "valid": True,
            "error_count": 0,
            "diff": diff,
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

    return {
        "status": "applied",
        "valid": True,
        "error_count": 0,
        "diff": diff,
        "backup": backup,
        "applied_rule_count": len(req.rules),
    }


# ─── F 碰撞/冲突域段: M4 跨专业碰撞 + M5 两稿改动冲突 (只调用工具库, 不重写) ───
# 懒 import 放函数体: module 收集期不触发 clash/conflict 重依赖。
# 红线二: sample 不存在 → 404 诚实报错, 无碰撞/无冲突 → 0 + 空列表, 绝不造假。

_CLASH_SAMPLE_KEYS = [
    "structural_beams", "structural_columns", "pipes", "hvac_ducts",
    "outlets", "hvac_grilles",
]


def _load_sample_raw(sample: str) -> dict:
    """读 data/sample/<sample> 顶层元素数据 (键缺失/缺键优雅取空 dict)。
    文件不存在 → HTTPException 404 (诚实报错, 不造假数据)。"""
    p = os.path.join(ROOT, "data", "sample", sample)
    if not os.path.exists(p):
        raise HTTPException(404, f"样本不存在: {sample}")
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    # 顶层是元素数据 (doors/pipes/... 各带 id), 只取碰撞检测用到的键
    return {k: data.get(k, []) for k in _CLASH_SAMPLE_KEYS}


@app.get("/api/clash")
def api_clash(sample: str = "residential_100sqm.json",
              tolerance_m: Optional[float] = None) -> dict:
    """M4 跨专业碰撞: 读 sample 顶层元素数据调 detect_clashes。

    容差取值通道 (M4 ← default.json 回填, 同 M1 数值范式):
      ① query tolerance_m 显式传 → 来源 "param"
      ② default.json 的 clash-tolerance-range 规则 params.clash_tolerance_m
         → 来源 "dsl" (专家改 JSON 即生效, 零代码)
      ③ 几何默认 0.15m → 来源 "default"
    返回 {sample, tolerance_m, tolerance_source, clashes: [...], count}。
    无碰撞 → count=0 空列表 (诚实, 不造假)。"""
    from src.agents.src.tools.clash_detection import (  # 懒
        detect_clashes, resolve_clash_tolerance)

    dsl_rule = None
    try:
        from src.agents.src.nodes.cad_rule_export import _dsl_rules_path
        from src.rules.src.dsl import load_dsl_rules
        for r in load_dsl_rules(_dsl_rules_path()):
            if r.rule_id == "clash-tolerance-range":
                dsl_rule = r
                break
    except Exception:
        dsl_rule = None  # JSON 缺/损坏 → 降级几何默认, 不崩
    tol, tol_src = resolve_clash_tolerance(
        default_m=0.15, dsl_rule=dsl_rule,
        params={"clash_tolerance_m": tolerance_m} if tolerance_m else None,
    )
    raw = _load_sample_raw(sample)
    clashes = detect_clashes(raw, tolerance_m=tol)
    return {"sample": sample, "tolerance_m": tol, "tolerance_source": tol_src,
            "clashes": clashes, "count": len(clashes)}


@app.get("/api/conflict")
def api_conflict(sample_a: str = "residential_100sqm.json",
                 sample_b: str = "residential_100sqm.json") -> dict:
    """M5 两稿改动冲突: 两份 sample 顶层数据调 detect_conflicts + summarize_conflicts。

    默认开启几何等价类维度 (check_duplicates=True): 同坐标不同 id = 疑似重复元素
    (kind='duplicate', 琥珀色 UI 标注), 捕捉设计师两稿「画了同位置但用了不同 id」
    的常见疏漏。传 check_duplicates=False 可关闭 (老调用方零改动, 向后兼容)。

    返回 {sample_a, sample_b, count, by_category, conflicts, summary}。
    summary 含 value_conflicts/added/removed/duplicates 四维度计数。
    同稿自比 → count=0 空列表 (诚实, 不造假)。"""
    from src.agents.src.tools.conflict_detection import (  # 懒
        detect_conflicts, summarize_conflicts)

    raw_a = _load_sample_raw(sample_a)
    raw_b = _load_sample_raw(sample_b)
    conflicts = detect_conflicts(raw_a, raw_b, check_duplicates=True)
    summary = summarize_conflicts(conflicts)
    return {
        "sample_a": sample_a,
        "sample_b": sample_b,
        "count": len(conflicts),
        "by_category": summary["by_category"],
        "conflicts": conflicts,
        "summary": summary,
    }


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
    from src.agents.src.tools.dwg_layer_scan import scan_sample_reader  # 懒
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
# 让 collab_protocol 机制骨架有可见入口: 读 data/collab/state.json (真持久, 缺文件
# 诚实返回空态, 不造假)。
# 诚实边界 (不虚标):
#   - 快照只读: /api/collab/snapshot 透出「当前协同快照」(写锁持有者 + 最近事件)。
#   - 锁端点 (/api/collab/acquire|release) 是**本地单进程演示通路**: 锁态落本地
#     state.json, 无跨设计师同步/无多机仲裁 — 真·在线协同 (CRDT/OT/单写者多读者
#     协议 + 用户体系) 需业务定协议后再接, 端点 docstring 与响应 note 均显式标注。
# 懒 import: collab_protocol 依赖 permission_model (纯函数, 无重依赖), 但照范式放函数体。

_COLLAB_STATE_PATH = os.path.join(ROOT, "data", "collab", "state.json")


@app.get("/api/collab/snapshot")
def api_collab_snapshot(designer: str = "designer") -> dict:
    """M5 在线协同持久层: 读协同状态快照 (谁持哪些写锁 + 最近协同事件)。

    返回 {designer, write_holders, recent_events, event_count, source}。
    状态文件不存在 → 空快照 (write_holders={}, 事件 0), 诚实标注 source="empty",
    不造假协同数据。"""
    from src.agents.src.tools.collab_protocol import (  # 懒
        JsonFileCollabStore, make_snapshot)

    store = JsonFileCollabStore(_COLLAB_STATE_PATH)
    snap = make_snapshot(store, designer=designer)
    # 诚实标注来源: 真有落盘 state 才 "file", 空态标 "empty"
    has_state = store.load()
    snap["source"] = "file" if has_state else "empty"
    snap["note"] = ("持久协同快照" if has_state
                    else "无落盘协同状态 (写操作待业务定协同协议后接入)")
    return snap


def _collab_store() -> object:
    """懒建默认协同 store (data/collab/state.json, 缺目录自动建)。"""
    from src.agents.src.tools.collab_protocol import JsonFileCollabStore
    os.makedirs(os.path.dirname(_COLLAB_STATE_PATH), exist_ok=True)
    return JsonFileCollabStore(_COLLAB_STATE_PATH)


class CollabLockReq(BaseModel):
    designer: str
    resource_id: str
    mode: str = "write"  # write / read (read 不互斥, 总是成功)


@app.post("/api/collab/acquire")
def api_collab_acquire(req: CollabLockReq) -> dict:
    """本地取锁演示通路: persistent_acquire (load→acquire_lock→追加 lock 事件→save)。

    返回 {acquired, resource_id, designer, mode, reason, write_holders}。
    被他人写锁占用 → acquired=false + reason (诚实, 不崩)。
    诚实标注: 本地单进程, 无跨设计师同步 — 真·在线协同待业务定协议后再接。"""
    from src.agents.src.tools.collab_protocol import persistent_acquire, make_snapshot
    import time
    store = _collab_store()
    ok, state, reason = persistent_acquire(
        store, req.resource_id, req.designer, req.mode, now=time.time())
    snap = make_snapshot(store, designer=req.designer)
    snap.update({
        "acquired": ok,
        "resource_id": req.resource_id,
        "designer": req.designer,
        "mode": req.mode,
        "reason": reason,
        "note": "本地锁演示 (单进程, 无跨设计师同步; 真·在线协同待业务定协议)",
    })
    return snap


class CollabReleaseReq(BaseModel):
    designer: str
    resource_id: str


@app.post("/api/collab/release")
def api_collab_release(req: CollabReleaseReq) -> dict:
    """本地放锁演示通路: persistent_release (load→release_lock→追加 unlock 事件→save)。

    返回 {released, resource_id, designer, write_holders}。释放后该写锁消失
    (幂等: 无对应锁也返回 200, released=false 诚实标注)。"""
    from src.agents.src.tools.collab_protocol import persistent_release, make_snapshot
    store = _collab_store()
    before = store.load()
    held = any(l.get("resource_id") == req.resource_id and l.get("holder") == req.designer
               and l.get("mode") == "write" for l in before.get("locks", []))
    persistent_release(store, req.resource_id, req.designer)
    snap = make_snapshot(store, designer=req.designer)
    snap.update({
        "released": held,  # 确有该写锁被放掉才 true; 无锁释放 (幂等) → false
        "resource_id": req.resource_id,
        "designer": req.designer,
        "note": "本地锁演示 (单进程, 无跨设计师同步; 真·在线协同待业务定协议)",
    })
    return snap


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
