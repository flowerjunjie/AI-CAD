"""方向② 端点失步 False 态护栏 (机制层自主子集, 纯测试层, 零引擎判据变更)。

P12 前端已把 4 个诊断端点接进 UI (ClashSection/ConflictSection/DwgScanSection/
RuleEditorPanel), UI 逻辑是「consistent===false && issues 非空 才显失步警示行」
(src/client/src/ClashSection.tsx:75 等)。既有端点测试只钉死「自产恒 True」单态
(test_bridge_clash_conflict.py L92/139/159 全是 is True), 从未证明「verify 报 issues
时端点确实把 consistent=False 透给前端」。

本文件补上这条缺失契约: 让真 verify 自然判 False (喂 ghost-id 碰撞 / 失步 summary),
断言端点透出 consistent=False 且 issues 非空 — 把前端那条「失步才示警」的 if 分支
从死代码级风险钉成有护栏的真契约。

实现要点 (防猴补脆弱): 端点内部对 detect_clashes / summarize_conflicts 是「函数体
内 from ... import」, 故 patch 源头模块 (clash_detection.detect_clashes 等) 属性即可
命中端点调用路径; verify_* 是源头纯函数不 patch (让它真跑, 判 False 才可信)。

红线: 全用例带 monkeypatch fixture, **绝不进 __main__** (test_direct_run 硬约束:
__main__ 只列无 fixture 子集)。__main__ 只留一条无 fixture 的前端契约锚点兜底。
ASCII 输出。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from fastapi.testclient import TestClient


def test_clash_inconsistent_surfaced_at_endpoint(monkeypatch):
    """/api/clash: patch detect_clashes 返回一条 ghost-id 碰撞 (a_id 'ghostX' 不在
    raw) → 真 verify_clashes 判 valid=False → 端点透出 clashes_consistent=False 且
    clashes_issues 非空 (前端失步警示行真能触发)。"""
    from src.gui import bridge as bridge_main
    from src.agents.src.tools import clash_detection as cd

    def fake_detect(raw, tolerance_m=None, **kw):
        return [{"a_id": "ghostX", "b_id": "sbX", "kind": "pipe-beam",
                 "detail": "d", "overlap_m": 0.1}]
    monkeypatch.setattr(cd, "detect_clashes", fake_detect)
    with TestClient(bridge_main.app) as client:
        resp = client.get("/api/clash?sample=residential_100sqm.json")
        assert resp.status_code == 200
        body = resp.json()
        assert body["clashes_consistent"] is False
        assert body["clashes_issues"], "失步诊断应透出非空 issues"


def test_conflict_inconsistent_surfaced_at_endpoint(monkeypatch):
    """/api/conflict: patch summarize_conflicts 返回与列表失步的 summary (total 对
    不上条数) → 真 verify_summary 判 consistent=False → 端点透出
    summary_consistent=False 且 summary_issues 非空。"""
    from src.gui import bridge as bridge_main
    from src.agents.src.tools import conflict_detection as cfd

    def fake_summarize(conflicts, **kw):
        # 故意 total 与列表条数失步 (0 条列表却 total=5) → verify_summary 揪出;
        # by_category 端点直接读, 必带 (形状齐全, 别漏)。
        return {"total": 5, "value_conflicts": 5, "added": 0, "removed": 0,
                "duplicates": 0, "by_category": {}}
    monkeypatch.setattr(cfd, "summarize_conflicts", fake_summarize)
    with TestClient(bridge_main.app) as client:
        resp = client.get("/api/conflict?sample_a=residential_100sqm.json"
                          "&sample_b=residential_100sqm.json")
        assert resp.status_code == 200
        body = resp.json()
        assert body["summary_consistent"] is False
        assert body["summary_issues"], "失步诊断应透出非空 issues"


def test_dwg_scan_inconsistent_surfaced_at_endpoint(monkeypatch):
    """/api/dwg-scan: patch verify_dwg_scan_report 判 ok=False (层数对不上) → 端点透出
    scan_consistent=False 且 scan_issues 非空 (端点内 from dwg_layer_scan import
    verify_dwg_scan_report, patch 源模块属性即命中)。"""
    from src.gui import bridge as bridge_main
    from src.agents.src.tools import dwg_layer_scan as dls

    def fake_verify(report):
        return {"ok": False, "issues": ["layer_count=3 ≠ len(layers)=5"], "checked": 3}
    monkeypatch.setattr(dls, "verify_dwg_scan_report", fake_verify)
    with TestClient(bridge_main.app) as client:
        resp = client.get("/api/dwg-scan?sample=electrical_sample.dxf")
        assert resp.status_code == 200
        body = resp.json()
        assert body["scan_consistent"] is False
        assert body["scan_issues"], "失步诊断应透出非空 issues"


def test_dsl_apply_inconsistent_surfaced_at_endpoint(monkeypatch):
    """/api/rules/dsl/apply: patch verify_diff_buckets 判 consistent=False (同 rule_id
    既进 added 又进 changed) → 端点透出 diff_consistent=False 且 diff_issues 非空。"""
    from src.gui import bridge as bridge_main
    from src.rules.src import diff as diff_mod

    def fake_verify(buckets, key_of):
        return {"ok": False, "issues": ["rule 'r1' 既在 added 又在 changed"],
                "checked": 3}
    monkeypatch.setattr(diff_mod, "verify_diff_buckets", fake_verify)
    with TestClient(bridge_main.app) as client:
        resp = client.post("/api/rules/dsl/apply", json={"rules": [], "confirm": False})
        assert resp.status_code == 200
        body = resp.json()
        # confirm=False 走 diff 预览, 端点带出 diff_consistent 诊断
        assert body.get("diff_consistent") is False
        assert body.get("diff_issues"), "失步诊断应透出非空 issues"


if __name__ == "__main__":
    # 无 fixture 兜底: 断言前端确实消费这些失步字段名 (防契约漂移 — 字段改名而 UI
    # 没跟上时先炸)。带 monkeypatch 的 4 个失步用例归 pytest 专属, 不进 __main__。
    _clash = open(os.path.join(project_root, "src", "client", "src",
                               "ClashSection.tsx"), encoding="utf-8").read()
    _conf = open(os.path.join(project_root, "src", "client", "src",
                              "ConflictSection.tsx"), encoding="utf-8").read()
    assert "clashes_consistent" in _clash, "前端 ClashSection 未消费 clashes_consistent"
    assert "summary_consistent" in _conf, "前端 ConflictSection 未消费 summary_consistent"
    print("OK: endpoint false-state guardrails — front-end contract anchors hold")
