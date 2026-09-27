"""
FastAPI 端点测试 — 规则 DSL 写回端点 POST /api/rules/dsl/apply (bridge.py B3 段)。
范式同 test_bridge_rules_dsl_endpoints.py: sys.path 注入项目根 + TestClient 直调
bridge app。写回涉及真 default.json, 每例 monkeypatch 临时目录 + 还原, 守 229 基线不弄红。
"""
import json
import os
import shutil
import sys

import pytest

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from fastapi.testclient import TestClient

from src.gui import bridge

REAL_DEFAULT = os.path.join(project_root, "src", "rules", "rules", "default.json")


def _good_rules() -> list:
    """一条合法 DSL 规则 (predicate 白名单内 + 键名合法), 供写回。"""
    return [
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


@pytest.fixture()
def patched_dsl_dir(tmp_path, monkeypatch):
    """把 bridge._dsl_default_path 指到 tmp 目录, 写真 default.json 前备份可安全还原。"""
    fake = tmp_path / "default.json"
    fake.write_text(json.dumps({"rules": _good_rules()}, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(bridge, "_dsl_default_path", lambda: str(fake))
    return fake


def test_apply_validation_failure_rejects_write(patched_dsl_dir):
    """校验不过 (severity 非法) → 422 拒写, default.json 原封不动。"""
    bad = _good_rules()
    bad[0]["severity"] = "fatal"
    before = patched_dsl_dir.read_text(encoding="utf-8")
    with TestClient(bridge.app) as client:
        resp = client.post("/api/rules/dsl/apply", json={"rules": bad, "confirm": True})
    assert resp.status_code == 422
    assert resp.json()["detail"]["reason"] == "validation_failed"
    assert patched_dsl_dir.read_text(encoding="utf-8") == before  # 未动盘


def test_apply_confirm_false_returns_diff_no_write(patched_dsl_dir):
    """confirm=False → 200 pending_confirm + diff, default.json 未被写 (无备份)。"""
    payload = {"rules": _good_rules(), "confirm": False}
    before = patched_dsl_dir.read_text(encoding="utf-8")
    with TestClient(bridge.app) as client:
        resp = client.post("/api/rules/dsl/apply", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending_confirm"
    assert body["valid"] is True
    assert "diff" in body
    assert patched_dsl_dir.read_text(encoding="utf-8") == before  # 未落盘
    # 未确认不产备份
    for f in patched_dsl_dir.parent.iterdir():
        assert "default.json.bak." not in f.name


def test_apply_confirm_true_writes_and_backs_up(patched_dsl_dir):
    """confirm=True → 写盘 + 生成 .bak, 写后能重新 load (fail-fast 兜底)。"""
    from src.rules.src.dsl import DslRuleProvider

    new_rules = _good_rules()
    new_rules[0]["rule_id"] = "gui-test-door-w-v2"  # 模拟新增一条
    with TestClient(bridge.app) as client:
        resp = client.post("/api/rules/dsl/apply", json={"rules": new_rules, "confirm": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "applied"
    assert body["backup"] and os.path.exists(body["backup"])
    # 写盘成功: 文件内容 = 入参 rules
    written = json.loads(patched_dsl_dir.read_text(encoding="utf-8"))
    assert [r["rule_id"] for r in written["rules"]] == [r["rule_id"] for r in new_rules]
    # 写后 DslRuleProvider 能重载 (兜底判据)
    assert len(DslRuleProvider(patched_dsl_dir).load()) == len(new_rules)
    # diff 预览: 新增的 rule_id 落在 added
    assert "gui-test-door-w-v2" in body["diff"]["added"]


def test_apply_missing_file_404(tmp_path, monkeypatch):
    """default.json 不存在 → 404 (不造假)。"""
    missing = str(tmp_path / "nope.json")
    monkeypatch.setattr(bridge, "_dsl_default_path", lambda: missing)
    with TestClient(bridge.app) as client:
        resp = client.post("/api/rules/dsl/apply", json={"rules": _good_rules(), "confirm": True})
    assert resp.status_code == 404


if __name__ == "__main__":
    print("Run via pytest: python -m pytest tests/unit/test_bridge_rules_dsl_apply.py -q")
