"""
M1 数值回填端点测试 — bridge /api/rules/backfill (单规则写盘 + 备份 + fail-fast)

验证 bridge 单规则回填入口: 改指定 rule 的 confirmed/confidence/param_defaults,
备份可回滚, confidence 白名单 (不虚标), 未找到规则 404, 非目标规则 0 改动。
隔离策略: monkeypatch bridge._dsl_default_path 指向 tmp 副本, 不污染真实 default.json。
__main__ 直跑护栏: 无 fixture 子集 (monkeypatch 的 case 仅 pytest 跑), ASCII print。
"""
import sys
import os
import json
import shutil

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from fastapi.testclient import TestClient

import src.gui.bridge as bridge
from src.gui.bridge import app

DEFAULT_JSON = os.path.join(project_root, "src", "rules", "rules", "default.json")


def _patch_to(tmp_path: str):
    """让 bridge 写到 tmp_path 的 default.json 副本; 返回真实盘备份路径 (供回滚对比)。"""
    shutil.copy(DEFAULT_JSON, tmp_path + ".default.json")
    bridge._dsl_default_path = lambda: tmp_path + ".default.json"
    return tmp_path + ".default.json"


def _restore():
    """恢复 bridge._dsl_default_path 原函数 (防测试间泄漏)。"""
    import importlib
    importlib.reload(bridge)


def test_backfill_writes_and_backs_up(tmp_path, monkeypatch):
    """回填 confirmed=true + param → 写 tmp 盘 + 自动备份, 重载不炸。"""
    target = _patch_to(str(tmp_path))
    try:
        with TestClient(app) as client:
            resp = client.post("/api/rules/backfill", json={
                "rule_id": "clash-tolerance-range",
                "confirmed": True, "confidence": "high",
                "params": {"clash_tolerance_m": 0.25},
            })
        assert resp.status_code == 200, f"应 200, 实际 {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["status"] == "applied" and body["confirmed"] is True
        assert body["param_defaults"].get("clash_tolerance_m") == 0.25
        assert body["backup"], "应返回备份路径 (可回滚)"
        with open(target, encoding="utf-8") as fh:
            r = next(x for x in json.load(fh)["rules"]
                     if x["rule_id"] == "clash-tolerance-range")
        assert r["confirmed"] is True and r["param_defaults"]["clash_tolerance_m"] == 0.25
        print("PASS test_backfill_writes_and_backs_up")
    finally:
        _restore()


def test_backfill_confidence_whitelist(tmp_path, monkeypatch):
    """confidence 白名单: 非法值 → 422 拒写 (不虚标, 不静默降级)。"""
    target = _patch_to(str(tmp_path))
    try:
        with TestClient(app) as client:
            resp = client.post("/api/rules/backfill", json={
                "rule_id": "clash-tolerance-range", "confidence": "urgent"})
        assert resp.status_code == 422, f"非法 confidence 应 422, 实际 {resp.status_code}"
        print("PASS test_backfill_confidence_whitelist")
    finally:
        _restore()


def test_backfill_unknown_rule_404(tmp_path, monkeypatch):
    """未找到 rule_id → 404 + 列可用规则, 不误写盘。"""
    target = _patch_to(str(tmp_path))
    try:
        with TestClient(app) as client:
            resp = client.post("/api/rules/backfill", json={
                "rule_id": "no-such-rule", "confirmed": True})
        assert resp.status_code == 404, f"未知规则应 404, 实际 {resp.status_code}"
        assert "未找到规则" in resp.json()["detail"]
        print("PASS test_backfill_unknown_rule_404")
    finally:
        _restore()


def test_backfill_non_target_rules_unchanged(tmp_path, monkeypatch):
    """只回填目标规则, 其余规则 0 改动 (逐条比对)。"""
    target = _patch_to(str(tmp_path))
    try:
        with open(target, encoding="utf-8") as fh:
            before = json.load(fh)["rules"]
        with TestClient(app) as client:
            resp = client.post("/api/rules/backfill", json={
                "rule_id": "structural-beam-min-height",
                "confirmed": True, "confidence": "medium",
                "confirm_note": "结构专家背书: 梁高下限 300mm"})
        assert resp.status_code == 200
        with open(target, encoding="utf-8") as fh:
            after = json.load(fh)["rules"]
        others_b = [x for x in before if x["rule_id"] != "structural-beam-min-height"]
        others_a = [x for x in after if x["rule_id"] != "structural-beam-min-height"]
        assert others_b == others_a, "非目标规则应 0 改动"
        target_a = next(x for x in after if x["rule_id"] == "structural-beam-min-height")
        assert target_a["confirmed"] is True and target_a["confirm_note"]
        print("PASS test_backfill_non_target_rules_unchanged")
    finally:
        _restore()


if __name__ == "__main__":
    # 无 fixture 子集: monkeypatch 等价物 (手工 patch + restore), ASCII print
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        _patch_to(td)
        try:
            with TestClient(app) as client:
                r1 = client.post("/api/rules/backfill",
                                 json={"rule_id": "nope", "confirmed": True})
                assert r1.status_code == 404, f"未知规则应 404, 实际 {r1.status_code}"
                r2 = client.post("/api/rules/backfill", json={
                    "rule_id": "clash-tolerance-range", "confirmed": True,
                    "confidence": "high", "params": {"clash_tolerance_m": 0.25}})
                assert r2.status_code == 200, f"正常回填应 200, 实际 {r2.status_code}: {r2.text}"
            print("PASS direct-run: backfill 404 + applied")
        finally:
            _restore()
    print("OK: all backfill endpoint tests passed")
