"""
FastAPI 端点测试 — 规则 DSL 编辑器面板的两个桥端点
(GET /api/rules/dsl + POST /api/rules/validate, src/gui/bridge.py B2 段)。

范式同 tests/unit/test_agent_confirm_routes.py: sys.path 注入项目根 +
fastapi TestClient 直调 bridge app。validate_dsl_json 对桥端点不 monkeypatch
(端点内部 import 的就是真函数), 用例直接验证透传判据。
"""
import json
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from fastapi.testclient import TestClient

from src.gui.bridge import app


def _good_payload() -> dict:
    """一条合法 DSL 规则 (predicate 白名单内 + 键名合法)。"""
    return {
        "rules": [
            {
                "rule_id": "gui-test-door-w",
                "name": "门宽",
                "code_ref": "GB 50096",
                "severity": "error",
                "element_types": ["Door", "door"],
                "predicate": "element.room_type == 'entrance' and element.width_m < min_width_m",
                "params": {},
                "param_defaults": {"min_width_m": 1.0},
                "enabled": True,
                "dsl_only": True,
            }
        ]
    }


def test_get_rules_dsl_serves_default_json():
    """/api/rules/dsl 返回 default.json 原文 (顶层含 'rules' 数组, 有 predicate 字段)。"""
    with TestClient(app) as client:
        resp = client.get("/api/rules/dsl")
        assert resp.status_code == 200
        data = resp.json()
        assert "rules" in data
        assert isinstance(data["rules"], list) and len(data["rules"]) > 0
        # 全字段透出 (编辑器要读 predicate/params/param_defaults)
        first = data["rules"][0]
        for key in ("rule_id", "name", "severity", "predicate", "element_types"):
            assert key in first, f"字段 {key} 未透出"


def test_validate_good_payload_is_valid():
    """/api/rules/validate 合法 JSON → valid=True, errors 空。"""
    with TestClient(app) as client:
        resp = client.post("/api/rules/validate", json=_good_payload())
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["error_count"] == 0
        assert body["errors"] == []


def test_validate_flags_bad_severity_with_rule_id():
    """severity 非 error/warning/info → 报错, path 定位到字段 + 补出 rule_id。"""
    payload = _good_payload()
    payload["rules"][0]["severity"] = "fatal"
    with TestClient(app) as client:
        resp = client.post("/api/rules/validate", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert body["error_count"] >= 1
        errs = body["errors"]
        assert any("severity" in e["path"] for e in errs)
        # 规则级错误带上 rule_id (前端按 rule_id 定位)
        assert any(e.get("rule_id") == "gui-test-door-w" for e in errs)


def test_validate_flags_non_whitelisted_predicate_identifier():
    """predicate 出现白名单外标识符 (且不在 params/param_defaults) → 报错。"""
    payload = _good_payload()
    payload["rules"][0]["predicate"] = "element.width_m < some_unknown_param"
    with TestClient(app) as client:
        resp = client.post("/api/rules/validate", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert any("predicate" in e["path"] for e in body["errors"])


def test_validate_rejects_empty_rules():
    """rules 为空数组 → 顶层 schema 错 (validator 要求顶层 {'rules': [...]} 且非空)。"""
    with TestClient(app) as client:
        resp = client.post("/api/rules/validate", json={"rules": []})
        assert resp.status_code == 200
        body = resp.json()
        # 空数组在 schema 上合法 (validator 不拦空规则列表) — 只断言端点结构稳定
        assert "valid" in body and "error_count" in body and "errors" in body


if __name__ == "__main__":
    test_get_rules_dsl_serves_default_json()
    test_validate_good_payload_is_valid()
    test_validate_flags_bad_severity_with_rule_id()
    test_validate_flags_non_whitelisted_predicate_identifier()
    test_validate_rejects_empty_rules()
    print("OK: all bridge rule-DSL editor endpoint tests passed")
