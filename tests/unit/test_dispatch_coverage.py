"""方向① 分发表规则覆盖护栏 (机制层自主子集, 不判业务值):
「confirmed=True 的 DSL 规则, 若其 element_types 命中某分发表项的 build 类,
则该 rule_id 必须出现在该表项 rule_ids 里」— 否则真实主链路
(rule_check_node 走 engine.check(elems, rule_ids=表项.rule_ids)) 永远跑不到它,
隔离测试全绿也盖不住这条主链路盲区。

红线 (诚实边界): 只校验「已 confirmed 规则是否漏 dispatch」这一**机制自洽**面,
不替专家把 confirmed=False 的占位规则翻成 True (M1 数值仍待专家回填); 护栏对
confirmed=False 的规则一律不报。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def _real_confirmed_map() -> dict:
    """读真实 default.json → {rule_id: confirmed}(只取机制量 confirmed 字段)。"""
    import json
    from src.agents.src.nodes.cad_rule_export import _dsl_rules_path
    with open(_dsl_rules_path(), encoding="utf-8") as f:
        data = json.load(f)
    rules = data.get("rules") or data.get("dsl_rules") or []
    return {r.get("rule_id"): bool(r.get("confirmed")) for r in rules if r.get("rule_id")}


def _mk_rule(rid, etypes):
    """最小规则实例 (鸭子: 直挂 rule_id / element_types, 仿 dsl._rule_type_fields)。"""
    class _R:
        pass
    r = _R()
    r.rule_id = rid
    r.element_types = etypes
    return r


def test_dispatch_covers_all_confirmed_hit_rules():
    """真实 _ELEMENT_CHECKS + 真实 default.json: 每条 confirmed 规则若命中某表项
    build 类, 就必须在该表项 rule_ids 里 (当前 default.json 全绿, 无漏 dispatch)。"""
    from src.agents.src.nodes.cad_rule_export import (
        _ELEMENT_CHECKS, constructible_element_types, _dsl_rules_path as cre_dsl_path,
    )
    from src.rules.src.dsl import audit_dispatch_coverage, load_dsl_rules

    confirmed = _real_confirmed_map()
    # 规则实例: 从真实 default.json 载入 (element_types 真实), 喂给纯函数对账
    rules = load_dsl_rules(cre_dsl_path())
    # 不喂 entry_class_hints → 函数走各表项 build 的返回类型注解现读 (单项精确类,
    # 非全集), 命中判定 = 规则 element_types ∩ 该表项 build 类。当前 default.json
    # 全绿 (每条 confirmed 规则都 dispatch 在其所属表项), 断言无漏。
    res = audit_dispatch_coverage(_ELEMENT_CHECKS, rules, confirmed)
    assert res["ok"] is True, f"存在 confirmed 规则漏 dispatch: {res['issues']}"
    assert res["issues"] == []
    assert all(c["confirmed_missing"] == [] for c in res["coverage"])


def test_dispatch_coverage_flags_missing_confirmed_rule():
    """confirmed 规则命中某表项 build 类, 但该表项 rule_ids 没列它 → 护栏揪出
    (钉死「漏 dispatch 会被报」, 非只认全绿)。"""
    from src.rules.src.dsl import audit_dispatch_coverage

    table = [{"raw_key": "structural_beams", "build": None,
              "rule_ids": ["structural-beam-width-depth-ratio"]}]
    rules = [_mk_rule("structural-beam-min-height", ["StructuralBeam"]),
             _mk_rule("structural-beam-width-depth-ratio", ["StructuralBeam"])]
    confirmed = {"structural-beam-min-height": True,
                 "structural-beam-width-depth-ratio": True}
    res = audit_dispatch_coverage(table, rules, confirmed,
                                 entry_class_hints={"structural_beams": {"StructuralBeam"}})
    assert res["ok"] is False
    assert any("structural-beam-min-height" in i for i in res["issues"]), res["issues"]


def test_dispatch_coverage_ignores_unconfirmed_rules():
    """confirmed=False 的规则即使命中类且漏 dispatch, 护栏**不报** (M1 占位,
    机制层不判; 专家回填 confirmed 后才自动要求进分发表)。"""
    from src.rules.src.dsl import audit_dispatch_coverage

    table = [{"raw_key": "k", "build": None, "rule_ids": []}]
    rules = [_mk_rule("some-rule", ["StructuralBeam"])]
    confirmed = {"some-rule": False}
    res = audit_dispatch_coverage(table, rules, confirmed,
                                 entry_class_hints={"k": {"StructuralBeam"}})
    assert res["issues"] == [], f"未 confirmed 规则不应触发 dispatch 护栏: {res['issues']}"
    assert res["coverage"][0]["confirmed_missing"] == []


if __name__ == "__main__":
    # 无 fixture 子集直跑 (红线: __main__ 不碰 pytest fixture, 不 print 中文)
    test_dispatch_coverage_flags_missing_confirmed_rule()
    test_dispatch_coverage_ignores_unconfirmed_rules()
    test_dispatch_covers_all_confirmed_hit_rules()
    print("test_dispatch_coverage: all pass")
