"""
批量校验报告结构自洽体检测试 (机制层自主子集)

覆盖:
  ① batch_check.verify_batch_report — 纯函数, 校验 BatchCheckReport 的
     by_severity/by_rule 聚合计数与明细 len(violations) 是否自洽 (防 _aggregate
     改动后未同步 / 外部直构不自洽 Report 的静默失步), 畸形不崩。
  ② bridge /api/rules/batch-verify — 走主链路 _ELEMENT_CHECKS 构造元素 →
     run_batch_check → 对账, 契约字段 + 200。

红线对齐 (CLAUDE.md 不虚标): 只判「报告自身聚合数字是否自洽」, 不判「某条违规
该不该发生」(M1 业务值)。仿 test_batch_check / test_dsl_rule_audit 范式:
__main__ 只列无 fixture 子集 + 不 print 中文/emoji (Windows GBK 直跑不崩)。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _bc():
    from src.rules.src import batch_check
    return batch_check


def _mk_report(violations, by_severity=None, by_rule=None):
    bc = _bc()
    return bc.BatchCheckReport(
        violations=violations,
        by_severity=by_severity if by_severity is not None else {},
        by_rule=by_rule if by_rule is not None else {},
    )


# ─── ① verify_batch_report 纯函数 ────────────────────────────


def test_consistent_report_ok():
    """by_severity 之和 / by_rule 之和 都 == len(violations) → ok=True。"""
    bc = _bc()
    from src.rules.src.engine import RuleViolation, ViolationSeverity
    vios = [
        RuleViolation("r1", "n1", ViolationSeverity.ERROR, "d", "GB-x", element_id="e1"),
        RuleViolation("r1", "n1", ViolationSeverity.WARNING, "d", "GB-x", element_id="e2"),
        RuleViolation("r2", "n2", ViolationSeverity.ERROR, "d", "GB-y"),
    ]
    rep = _mk_report(vios, {"error": 2, "warning": 1}, {"r1": 2, "r2": 1})
    res = bc.verify_batch_report(rep)
    assert res["ok"] is True and res["issues"] == [], f"自洽报告应通过, 得 {res}"
    assert res["total"] == 3


def test_severity_sum_mismatch_flagged():
    """by_severity 之和 ≠ 明细数 → 如实报聚合失步。"""
    bc = _bc()
    from src.rules.src.engine import RuleViolation, ViolationSeverity
    vios = [RuleViolation("r1", "n", ViolationSeverity.ERROR, "d", "GB-x")]
    rep = _mk_report(vios, {"error": 2}, {"r1": 1})  # by_severity 之和=2≠1
    res = bc.verify_batch_report(rep)
    assert res["ok"] is False
    assert any("by_severity" in it for it in res["issues"])


def test_rule_sum_mismatch_flagged():
    """by_rule 之和 ≠ 明细数 → 如实报聚合失步。"""
    bc = _bc()
    from src.rules.src.engine import RuleViolation, ViolationSeverity
    vios = [RuleViolation("r1", "n", ViolationSeverity.ERROR, "d", "GB-x"),
             RuleViolation("r1", "n", ViolationSeverity.ERROR, "d", "GB-x")]
    rep = _mk_report(vios, {"error": 2}, {"r1": 1})  # by_rule 之和=1≠2
    res = bc.verify_batch_report(rep)
    assert res["ok"] is False
    assert any("by_rule" in it for it in res["issues"])


def test_negative_count_flagged():
    """聚合计数出现负数 (手工/篡改) → 如实揪出。"""
    bc = _bc()
    rep = _mk_report([], {"error": -1}, {})
    res = bc.verify_batch_report(rep)
    assert res["ok"] is False
    assert any("负计数" in it for it in res["issues"])


def test_malformed_report_no_crash():
    """report 非 BatchCheckReport / 字段缺失 → 优雅降级不崩。"""
    bc = _bc()
    res = bc.verify_batch_report(object())
    assert res["ok"] is False and res["total"] == 0
    # 空报告 (0 违规) 合法, 不虚报
    rep = _mk_report([], {}, {})
    assert bc.verify_batch_report(rep)["ok"] is True


# ─── ② bridge 端点 ───────────────────────────────────────────


def test_bridge_batch_verify_endpoint():
    """/api/rules/batch-verify 200 + 契约字段; 走主链路构造元素 (非端点自造),
    residential_100sqm 合规样本 0 违规 → 空报告自洽 ok=True。"""
    from fastapi.testclient import TestClient
    from src.gui.bridge import app
    with TestClient(app) as client:
        resp = client.get("/api/rules/batch-verify")
        assert resp.status_code == 200, f"应 200, 实际 {resp.status_code} {resp.text}"
        body = resp.json()
        for k in ("sample", "ok", "total", "checked", "issues"):
            assert k in body, f"缺字段 {k}, 实际 {list(body)}"
        # 合规样本走主链路出 0 违规 → 空报告自洽 (诚实, 不虚报缺口)
        assert body["ok"] is True


if __name__ == "__main__":
    # 只跑无 pytest fixture 依赖的用例 (test_direct_run 会直跑 __main__ 块)
    test_consistent_report_ok()
    test_severity_sum_mismatch_flagged()
    test_rule_sum_mismatch_flagged()
    test_negative_count_flagged()
    test_malformed_report_no_crash()
    test_bridge_batch_verify_endpoint()
    print("OK: all verify_batch_report tests passed")
