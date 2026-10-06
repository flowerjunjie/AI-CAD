"""
违规清单结构自洽体检测试 (机制层自主子集)

覆盖:
  ① src/rules/src/diff.verify_violations — 纯函数, 校验违规清单 (to_dict 产物)
     的 rule_id 非空 / severity 合法 / rule_id 属引擎已注册集合 (防幽灵 rule_id
     静默穿透前端), 畸形输入优雅降级不崩。
  ② bridge /api/rules/violations-verify — 读真实样本跑引擎出违规, 过
     verify_violations 对账 (引擎自产违规必自洽), 端点契约 {ok, checked, issues}。

红线对齐 (CLAUDE.md 不虚标): 只校验「违规清单自身结构 + rule_id 是否真实存在」,
**不判**业务阈值对不对。仿 verify_clashes / test_dsl_rule_audit 范式:
纯函数 + 畸形不崩 + __main__ 只列无 fixture 子集 + ASCII print (Windows GBK 直跑不崩)。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _vv():
    from src.rules.src import diff
    return diff


# ─── ① verify_violations 纯函数 ─────────────────────────────────


def test_all_valid_ok():
    """全部合规 (rule_id 已注册 + severity 合法 + 非空) → ok=True, 0 issue。"""
    vv = _vv()
    vios = [
        {"rule_id": "r1", "severity": "error"},
        {"rule_id": "r2", "severity": "warning", "element_id": "e1"},
    ]
    res = vv.verify_violations(vios, {"r1", "r2"})
    assert res["ok"] is True and res["issues"] == [], f"全合规应自洽, 得 {res}"
    assert res["checked"] == 2


def test_ghost_rule_id_flagged():
    """rule_id 不在已注册集合 (引擎已删/写错) → 如实标幽灵 (无从溯源)。"""
    vv = _vv()
    res = vv.verify_violations([{"rule_id": "gone-rule", "severity": "error"}],
                               {"r1", "r2"})
    assert res["ok"] is False
    assert any("gone-rule" in it for it in res["issues"])


def test_invalid_severity_flagged():
    """severity 非合法枚举值 (大写/写错) → 如实标出。"""
    vv = _vv()
    res = vv.verify_violations([{"rule_id": "r1", "severity": "FATAL"}], {"r1"})
    assert res["ok"] is False
    assert any("FATAL" in it for it in res["issues"])


def test_missing_rule_id_flagged():
    """缺 rule_id / 空串 → 如实标出 (前端无法分组展示)。"""
    vv = _vv()
    res = vv.verify_violations([{"severity": "error"},
                                {"rule_id": "", "severity": "error"}], {"r1"})
    assert res["ok"] is False
    assert len(res["issues"]) >= 2


def test_malformed_input_no_crash():
    """violations 非 list / 条非 dict → 计入 issues 不崩 (优雅降级)。"""
    vv = _vv()
    assert vv.verify_violations("not-a-list", {"r1"})["ok"] is False
    res = vv.verify_violations([object(), 42], {"r1"})
    assert res["ok"] is False and res["checked"] == 2
    # 空 list 合法 (无违规 = 无缺口)
    assert vv.verify_violations([], {"r1"})["ok"] is True


# ─── ② bridge /api/rules/violations-verify 端点 ─────────────────


def test_bridge_violations_verify_endpoint():
    """/api/rules/violations-verify 200 + 契约字段; 引擎自产违规必自洽 (ok=True),
    注入的脏条目 (幽灵 rule_id + 非法 severity) 被如实揪出 (dirty_detected=True,
    证明体检非「恒绿」摆设) — 不虚标。"""
    from fastapi.testclient import TestClient
    from src.gui.bridge import app
    with TestClient(app) as client:
        resp = client.get("/api/rules/violations-verify")
        assert resp.status_code == 200, f"应 200, 实际 {resp.status_code} {resp.text}"
        body = resp.json()
        for k in ("ok", "checked", "issues", "dirty_detected", "dirty_issues"):
            assert k in body, f"缺字段 {k}, 实际 {list(body)}"
        # 引擎自产违规, rule_id 全在注册集 + severity 全合法 → 自洽
        assert body["ok"] is True, f"引擎自产违规应自洽, 得 {body['issues']}"
        # 注入的脏条目 (幽灵 rule_id / 非法 severity) 被揪出 → 体检非摆设
        assert body["dirty_detected"] is True
        assert len(body["dirty_issues"]) >= 2
        assert any("ghost-rule-not-registered" in it for it in body["dirty_issues"])
        assert any("NOT_A_SEVERITY" in it for it in body["dirty_issues"])


if __name__ == "__main__":
    # 只跑无 pytest fixture 依赖的用例 (test_direct_run 会直跑 __main__ 块)
    test_all_valid_ok()
    test_ghost_rule_id_flagged()
    test_invalid_severity_flagged()
    test_missing_rule_id_flagged()
    test_malformed_input_no_crash()
    test_bridge_violations_verify_endpoint()
    print("OK: all verify_violations tests passed")
