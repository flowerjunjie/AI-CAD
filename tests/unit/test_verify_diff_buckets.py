"""
三桶 diff 结果结构自洽体检测试 (机制层自主子集)

覆盖:
  ① diff.verify_diff_buckets — 纯函数 (key 提取器注入, diff_violations/diff_rule_lists
     共用), 校验 {added/removed/changed} 三桶自身结构不变量: 同 key 不跨桶交叠 /
     桶内无重复。防上游 diff 逻辑改动后「同一 key 既 added 又 changed」的静默失步。
  ② 用真实 diff_violations / diff_rule_lists 输出喂 verify_diff_buckets, 验证
     「正确实现的 diff 产物本身必自洽」(回归护栏, 钉死两条 diff 通路没被改坏)。

红线对齐 (CLAUDE.md 不虚标): 只判「三桶自身结构是否自洽」, 不判桶里业务内容
(M1 数值)。仿 test_diff.py / test_dsl_rule_audit 范式: __main__ 只列无 fixture
子集 + 不 print 中文/emoji (Windows GBK 直跑不崩)。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _diff():
    from src.rules.src import diff
    return diff


def _vio(rule_id, element_id, severity):
    from src.rules.src.engine import RuleViolation, ViolationSeverity
    return RuleViolation(rule_id, rule_id, severity, "d", "GB-x", element_id)


# ─── ① verify_diff_buckets 纯函数 (喂 dict 桶, key 提取器注入) ───


def _dict_buckets(added=(), removed=(), changed=()):
    return {"added": [{"rule_id": r} for r in added],
            "removed": [{"rule_id": r} for r in removed],
            "changed": [{"rule_id": r, "fields": {}} for r in changed]}


def test_disjoint_buckets_ok():
    """三桶 key 互斥 + 桶内无重复 → ok=True。"""
    d = _diff()
    res = d.verify_diff_buckets(_dict_buckets(added=("a",), removed=("b",), changed=("c",)),
                                key_of=lambda x: x["rule_id"])
    assert res["ok"] is True and res["issues"] == [], f"三桶互斥应自洽, 得 {res}"


def test_added_changed_overlap_flagged():
    """同一 rule_id 既进 added 又进 changed → 跨桶交叠失步, 如实揪出。"""
    d = _diff()
    res = d.verify_diff_buckets(_dict_buckets(added=("a",), changed=("a",)),
                                key_of=lambda x: x["rule_id"])
    assert res["ok"] is False
    assert any("added ∩ changed" in it for it in res["issues"])


def test_removed_changed_overlap_flagged():
    """同一 rule_id 既进 removed 又进 changed → 跨桶交叠失步, 如实揪出。"""
    d = _diff()
    res = d.verify_diff_buckets(_dict_buckets(removed=("a",), changed=("a",)),
                                key_of=lambda x: x["rule_id"])
    assert res["ok"] is False
    assert any("removed ∩ changed" in it for it in res["issues"])


def test_duplicate_within_bucket_flagged():
    """桶内重复 key (added 里 a 出现两次) → 上游 diff 失步, 如实揪出。"""
    d = _diff()
    res = d.verify_diff_buckets(_dict_buckets(added=("a", "a")),
                                key_of=lambda x: x["rule_id"])
    assert res["ok"] is False
    assert any("重复 key" in it for it in res["issues"])


def test_malformed_buckets_no_crash():
    """buckets 非 dict / 桶非 list → 优雅降级不崩。"""
    d = _diff()
    assert d.verify_diff_buckets("not-dict", lambda x: x)["ok"] is False
    res = d.verify_diff_buckets({"added": "not-list", "removed": [], "changed": []},
                                lambda x: x.get("rule_id"))
    assert res["ok"] is False
    # 空三桶 (两份完全一致的清单 diff 结果) 合法
    assert d.verify_diff_buckets({"added": [], "removed": [], "changed": []},
                                 lambda x: x)["ok"] is True


# ─── ② 真实 diff 产物必自洽 (回归护栏) ─────────────────────


def test_real_diff_violations_self_consistent():
    """diff_violations 正确实现的产物喂 verify_diff_buckets 必自洽 (key=rule_id+element_id)。"""
    d = _diff()
    base = [_vio("r1", "e1", None), _vio("r2", None, None)]
    curr = [_vio("r1", "e1", None), _vio("r3", "e3", None)]  # r2 删, r3 增
    res_diff = d.diff_violations(base, curr)
    res = d.verify_diff_buckets(res_diff,
                                key_of=lambda v: (v.rule_id, v.element_id or ""))
    assert res["ok"] is True, f"diff_violations 产物应自洽, 得 {res['issues']}"


def test_real_diff_rule_lists_self_consistent():
    """diff_rule_lists 正确实现的产物喂 verify_diff_buckets 必自洽 (key=rule_id)。"""
    d = _diff()
    # BaseRule 是 ABC (check 是 abstractmethod), 不能直接构造 — 用一个最小具体
    # 子类实例 (规则清单 diff 只读 _rule_sig 的字段, 不触发 check, 合规最小对象)。
    from src.rules.src.engine import BaseRule, ViolationSeverity

    class _ConcreteRule(BaseRule):
        def __init__(self, rid, name="n"):
            BaseRule.__init__(self)
            self.rule_id = rid
            self.name = name
            self.severity = ViolationSeverity.ERROR

        def check(self, element):
            from src.rules.src.engine import RuleResult
            return RuleResult(self, [])

    old = [_ConcreteRule("r1"), _ConcreteRule("r2")]
    new = [_ConcreteRule("r1"), _ConcreteRule("r3")]  # r2 删, r3 增
    res_diff = d.diff_rule_lists(old, new)
    res = d.verify_diff_buckets(res_diff, key_of=lambda x: x["rule_id"])
    assert res["ok"] is True, f"diff_rule_lists 产物应自洽, 得 {res['issues']}"


if __name__ == "__main__":
    # 只跑无 pytest fixture 依赖的用例 (test_direct_run 会直跑 __main__ 块)
    test_disjoint_buckets_ok()
    test_added_changed_overlap_flagged()
    test_removed_changed_overlap_flagged()
    test_duplicate_within_bucket_flagged()
    test_malformed_buckets_no_crash()
    test_real_diff_violations_self_consistent()
    test_real_diff_rule_lists_self_consistent()
    print("OK: all verify_diff_buckets tests passed")
