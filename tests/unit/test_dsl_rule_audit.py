"""
DSL 规则注册一致性体检测试 (机制层自主子集)

覆盖两个新增能力:
  ① src/rules/src/dsl.audit_rule_elements — 纯函数, 对账规则声明的
     element_types 与主链路可喂元素类白名单 + predicate 引用面自诊断。
  ② bridge /api/rules/dsl-audit — 集中透出体检结论 (默认 default.json
     的渠道规则 clash-tolerance-range / collab-lock-integrity 类型落空
     被如实标出, 不虚标「全绿」)。

红线对齐 (CLAUDE.md「不虚标」): 只校验「声明 vs 可喂类型」的机制一致性,
**不**判业务类名该叫什么。仿 verify_clashes / detect_deadlock 范式:
纯函数 + 畸形输入优雅降级不崩 + __main__ 只列无 fixture 子集 +
ASCII print (Windows GBK 直跑不崩, 见 test_direct_run.py)。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _import_dsl():
    from src.rules.src import dsl
    return dsl


class _StubRule:
    """最小规则对象 (鸭子类型, 不绑死 ParametricRule)。"""
    def __init__(self, rule_id="r1", element_types=None, predicate="True",
                 params=None, param_defaults=None):
        self.rule_id = rule_id
        self.element_types = element_types
        self.predicate = predicate
        self.params = params or {}
        self.param_defaults = param_defaults or {}


# ─── ① element_types 与可喂类型白名单对账 ──────────────────────


def test_audit_all_types_known_ok():
    """规则声明类型全在白名单 (含小写变体) → ok=True, 0 issue。"""
    dsl = _import_dsl()
    rules = [_StubRule("a", ["Door", "door"]),
             _StubRule("b", ["Window"])]
    res = dsl.audit_rule_elements(rules, {"Door", "Window"})
    assert res["ok"] is True and res["issues"] == [], f"全命中应自洽, 得 {res}"
    assert res["checked"] == 2 and res["dangling_rules"] == []


def test_audit_case_insensitive_variant_ok():
    """小写变体 (如 'plumbingpipe') 并入白名单同源判定 → 不报落空。"""
    dsl = _import_dsl()
    rules = [_StubRule("a", ["plumbingpipe"])]
    res = dsl.audit_rule_elements(rules, {"PlumbingPipe"})
    assert res["ok"] is True, f"小写变体应命中白名单, 得 {res}"


def test_audit_dangling_rule_flagged():
    """规则声明类型全部不在白名单 (渠道规则/写错类名) → 入 dangling_rules。"""
    dsl = _import_dsl()
    rules = [_StubRule("channel-rule", ["design_sheet", "structural_beam"]),
             _StubRule("ok-rule", ["Door"])]
    res = dsl.audit_rule_elements(rules, {"Door", "Window"})
    assert res["ok"] is False
    assert len(res["dangling_rules"]) == 1
    assert res["dangling_rules"][0]["rule_id"] == "channel-rule"
    assert res["dangling_rules"][0]["element_types"] == ["design_sheet", "structural_beam"]
    assert any("channel-rule" in it for it in res["issues"])


def test_audit_empty_element_types_flagged_wildcard():
    """element_types 为空 → 通配全类判定, 标出「无类型约束」(不判对错)。"""
    dsl = _import_dsl()
    res = dsl.audit_rule_elements([_StubRule("wc", [])], {"Door"})
    assert res["ok"] is False
    assert any("通配" in it or "无类型约束" in it for it in res["issues"])


def test_audit_malformed_input_no_crash():
    """rules 非 list / 条缺字段 → 计入 issues 不崩 (优雅降级)。"""
    dsl = _import_dsl()
    res = dsl.audit_rule_elements("not-a-list", {"Door"})
    assert res["ok"] is False and "非 list" in res["issues"][0]
    res2 = dsl.audit_rule_elements([object()], {"Door"})  # 无 rule_id/element_types
    assert res2["ok"] is False
    assert any("无 element_types" in it for it in res2["issues"])
    # 空 list 合法 (无规则 = 无缺口)
    assert dsl.audit_rule_elements([], {"Door"})["ok"] is True


# ─── ② predicate 引用面自诊断 (引用了未声明标识符) ─────────────


def test_audit_predicate_unknown_identifier_flagged():
    """predicate 引用既不在 params 也非白名单的标识符 → 检出 (防漂移)。"""
    dsl = _import_dsl()
    rules = [_StubRule("bad", ["Door"], "element.width_m < limit",
                       params={"other": 1})]
    res = dsl.audit_rule_elements(rules, {"Door"})
    assert res["ok"] is False
    assert any("limit" in it for it in res["issues"])


def test_audit_predicate_declared_param_ok():
    """predicate 引用的标识符已在 params/param_defaults 声明 → 不报。"""
    dsl = _import_dsl()
    rules = [_StubRule("ok", ["Door"], "element.width_m < limit",
                       params={"limit": 0.5})]
    res = dsl.audit_rule_elements(rules, {"Door"})
    assert res["ok"] is True and res["issues"] == [], f"已声明 params 应自洽, 得 {res}"


def test_audit_predicate_base_names_allowed():
    """element / True / False / None / len 是白名单基础名, 不视为未声明。"""
    dsl = _import_dsl()
    rules = [_StubRule("ok", ["Door"],
                       "element.room_type in ('a','b') or len(element.x) > 0")]
    res = dsl.audit_rule_elements(rules, {"Door"})
    assert res["ok"] is True, f"基础名不应误报, 得 {res}"


# ─── 真实 ParametricRule 兼容性 (字段挂在 _spec 上) ────────────


def test_audit_real_parametric_rule_compatibility():
    """真实 ParametricRule (element_types/predicate 在 _spec, 实例只挂 params)
    也能被体检正确对账 — 兼容 _rule_type_fields 的鸭子取字段路径。"""
    from src.rules.src.dsl import DslRuleProvider, ParametricRule
    provider = DslRuleProvider(
        os.path.join(project_root, "src", "rules", "rules", "default.json"))
    rules = provider.load()
    real = next(r for r in rules if r.rule_id == "dsl-stair-riser")
    assert isinstance(real, ParametricRule)
    # Stair 不在主链路可喂类型白名单 (楼梯无 extractor) → 如实标出 dangling
    res = _import_dsl().audit_rule_elements([real], {"Door"})
    assert res["ok"] is False
    assert res["dangling_rules"] and res["dangling_rules"][0]["rule_id"] == "dsl-stair-riser"
    # Stair 在白名单里 → 自洽 (predicate 引用 max_riser_m 已在 param_defaults)
    res2 = _import_dsl().audit_rule_elements([real], {"Stair"})
    assert res2["ok"] is True and res2["issues"] == [], f"白名单命中应自洽, 得 {res2}"


# ─── ③ 派生白名单防漂移 ───────────────────────────────────────


def test_constructible_types_derivation():
    """constructible_element_types() 由 _ELEMENT_CHECKS 各 build 返回注解派生,
    覆盖全 11 类 (含 Door/Window 具名壳 _build_door_2/_build_window_2)。

    钉死「派生 == 主链路可喂类」: 防将来误删 build 返回注解 / 改回 lambda
    后白名单静默漂回 9 类 (丢 Door/Window), 体检把门窗规则误判 dangling。"""
    from src.agents.src.nodes.cad_rule_export import constructible_element_types
    derived = constructible_element_types()
    expected = {
        "Door", "Window", "Room",
        "PlumbingPipe", "ElectricalOutlet", "ElectricalSwitch",
        "HvacDuct", "HvacUnit", "HvacGrille",
        "StructuralBeam", "StructuralColumn",
    }
    assert derived == expected, f"派生白名单漂移: {sorted(derived)} 期望 {sorted(expected)}"
    # 门/窗是主链路核心, 必须在白名单 (曾因 lambda 无注解丢失)
    assert "Door" in derived and "Window" in derived


# ─── ④ bridge /api/rules/dsl-audit 端点 ────────────────────────


def test_bridge_dsl_audit_endpoint():
    """/api/rules/dsl-audit 200 + 结构固定 {ok, checked, issues, dangling_rules, note}。

    真 default.json 的渠道/占位规则如实进 dangling_rules (不虚标全绿):
      · collab-lock-integrity 声明 ['design_sheet'] — 主链路无 DesignSheet extractor, 真落空。
      · clash-tolerance-range 声明 snake_case (structural_beam/plumbing_pipe/...) —
        主链路 _matches_type 匹配的是类名本身或其 .lower() (StructuralBeam →
        structuralbeam, 无下划线), **不**等于 snake_case 声明 structural_beam (有下划线),
        故主链路真实引擎本就命中不了 → 体检如实判 dangling (提醒改回类名本身)。
    判据与 ParametricRule._matches_type 严格同源 (小写并入、不去下划线), 不放宽也不收紧。"""
    from fastapi.testclient import TestClient
    from src.gui.bridge import app
    with TestClient(app) as client:
        resp = client.get("/api/rules/dsl-audit")
        assert resp.status_code == 200, f"应 200, 实际 {resp.status_code} {resp.text}"
        body = resp.json()
        for k in ("ok", "checked", "issues", "dangling_rules", "note"):
            assert k in body, f"缺字段 {k}, 实际 {list(body)}"
        dangling_ids = {d["rule_id"] for d in body["dangling_rules"]}
        # 真落空 + snake_case 主链路命中不了, 均如实入 dangling (不虚标)
        assert "collab-lock-integrity" in dangling_ids
        assert "clash-tolerance-range" in dangling_ids
        # 渠道规则 predicate="True" 无未声明标识符, 不误报 predicate
        assert not any("predicate" in it for it in body["issues"])


def test_audit_snake_case_declaration_not_matched_by_engine():
    """判据同源正例 (钉死与 _matches_type 一致, 防误放宽): 规则声明 snake_case
    (structural_beam) 对主链路 PascalCase 类 (StructuralBeam) — _matches_type 匹配
    类名本身或 .lower() (structuralbeam, 无下划线), 不等于 snake_case structural_beam
    → 主链路命中不了 → 体检如实判 dangling (不放宽: 不去下划线做假命中)。"""
    dsl = _import_dsl()
    rules = [_StubRule("sn-rule", ["structural_beam", "plumbing_pipe"])]
    res = dsl.audit_rule_elements(rules, {"StructuralBeam", "PlumbingPipe"})
    assert res["ok"] is False
    assert res["dangling_rules"] and res["dangling_rules"][0]["rule_id"] == "sn-rule"
    # 对照: 用类名本身或类名 .lower() 声明则命中
    res2 = dsl.audit_rule_elements(
        [_StubRule("ok-rule", ["StructuralBeam", "structuralbeam", "PlumbingPipe"])],
        {"StructuralBeam", "PlumbingPipe"})
    assert res2["ok"] is True and res2["dangling_rules"] == [], f"类名/.lower() 应命中, 得 {res2}"


if __name__ == "__main__":
    # 只跑无 pytest fixture 依赖的用例 (test_direct_run 会直跑 __main__ 块)
    test_audit_all_types_known_ok()
    test_audit_case_insensitive_variant_ok()
    test_audit_dangling_rule_flagged()
    test_audit_empty_element_types_flagged_wildcard()
    test_audit_malformed_input_no_crash()
    test_audit_predicate_unknown_identifier_flagged()
    test_audit_predicate_declared_param_ok()
    test_audit_predicate_base_names_allowed()
    test_audit_real_parametric_rule_compatibility()
    test_constructible_types_derivation()
    test_audit_snake_case_declaration_not_matched_by_engine()
    test_bridge_dsl_audit_endpoint()
    print("OK: all dsl rule audit tests passed")
