"""
AI-CAD GUI FastAPI 桥 — B 规则域段 (/api/rules + /api/rule-violations + /api/health)。

从 bridge.py 拆出的子模块 (bridge 超 500 红线, 结构性拆分)。用 APIRouter 承载
本域段端点, bridge.py 顶层 include_router 挂载 (app 注册方式不变, 端点路径 0 改动)。
跨段依赖: _load_sample_raw 走共享层 bridge_common; rag_health (D 段 api_health
探活用) 用函数体内惰性 import from src.gui.bridge, 规避顶层循环 import。
引擎/元素模型懒加载 (函数体), module 收集期不 import src.rules 全量规则。
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException

# _project_root 是 bridge.py 顶层函数 (被 B 段 _confirmed_rule_ids 引用, 未随段体搬);
# 顶层 import 之 (它自身不 import bridge 内容, 无循环风险)。
from src.gui.bridge import _project_root  # noqa: E402

router = APIRouter()

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


@router.get("/api/rules")
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


@router.get("/api/rules/dsl-audit")
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


@router.get("/api/rules/dsl-dispatch-audit")
def api_rules_dsl_dispatch_audit() -> dict:
    """分发表规则覆盖护栏 (机制层自主子集, 不判业务值): 对账 _ELEMENT_CHECKS 各
    表项 rule_ids 是否 dispatch 了「全部 confirmed=True 且 element_types 命中该表项
    build 类」的 DSL 规则。

    背景: rule_check_node 主链路走 engine.check(elems, rule_ids=表项.rule_ids), 只跑
    表项声明的 rule_ids; 隔离测试 (engine.check 不带 rule_ids) 跑全部注册规则是绿的,
    恰好盖住「主链路分发表漏 dispatch」盲区 — 一条 confirmed 规则若命中某表项 build
    类却漏列进该表项 rule_ids, 真实出图永远跑不到它。

    诚实边界: 只校验「confirmed 规则是否漏 dispatch」的机制自洽; confirmed=False 的
    占位规则 (M1 待专家回填) 一律不报 — 专家把某规则 confirmed 那天, 本端点即自动
    要求其进分发表, 把「回填后忘接主链路」的坑前置暴露。返回 {ok, checked, issues,
    coverage, note}。"""
    from src.rules.src.dsl import audit_dispatch_coverage, load_dsl_rules
    from src.agents.src.nodes.cad_rule_export import (
        _ELEMENT_CHECKS, _dsl_rules_path,
    )
    try:
        rules = load_dsl_rules(_dsl_rules_path())
    except Exception as e:
        return {"ok": False, "checked": 0, "issues": [f"default.json 加载失败: {e}"],
                "coverage": [],
                "note": "DSL 源不可读, 体检降级 (不造假规则清单)"}
    # confirmed 机制量: 直接从 default.json 读 (只取 confirmed 字段, 不碰业务值)
    import json
    try:
        with open(_dsl_rules_path(), encoding="utf-8") as f:
            data = json.load(f)
        confirmed = {r.get("rule_id"): bool(r.get("confirmed"))
                     for r in (data.get("rules") or data.get("dsl_rules") or [])
                     if r.get("rule_id")}
    except Exception as e:
        return {"ok": False, "checked": 0, "issues": [f"default.json 读 confirmed 失败: {e}"],
                "coverage": [], "note": "降级"}
    res = audit_dispatch_coverage(_ELEMENT_CHECKS, rules, confirmed)
    res["checked"] = len(res.get("coverage", []))
    res["note"] = ("confirmed 规则 vs 分发表 dispatch 覆盖对账 (机制层, 不判阈值); "
                   "confirmed_missing = 该表项漏 dispatch 的 confirmed 规则 "
                   "(confirmed=False 占位规则不参与, 专家回填后自动纳入)")
    return res


@router.get("/api/rules/violations-verify")
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


@router.get("/api/rules/batch-verify")
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


@router.get("/api/rule-violations")
def api_rule_violations() -> List[dict]:
    """实测演示违规: 0.6m 户门 vs residential-door-main-width (照 run.py bad_door 写法)。"""
    import src.rules.src.residential.doors  # noqa: F401  (触发注册)
    from src.rules.src.engine import get_engine
    from src.rules.src.residential.doors import Door

    engine = get_engine()
    bad_door = Door(id="gui-demo-d1", width_m=0.6, room_type="entrance", location=(0, 0))
    violations = engine.check([bad_door], rule_ids=["residential-door-main-width"])
    return [v.to_dict() for v in violations]


@router.get("/api/health")
def api_health() -> dict:
    """引擎探活: 规则计数 (hardcoded/dsl) + rag/llm 布尔占位给前端画徽章。"""
    from src.gui.bridge import rag_health  # 惰性: D 段探活函数, 规避顶层循环 import
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


