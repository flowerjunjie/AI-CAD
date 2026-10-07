"""
FastAPI 端点测试 — M4 碰撞 / M5 冲突的两个桥端点
(GET /api/clash + GET /api/conflict, src/gui/bridge.py F 段)。

范式同 tests/unit/test_bridge_rules_dsl_endpoints.py: sys.path 注入项目根 +
fastapi TestClient 直调 bridge app。检测工具库 (clash_detection /
conflict_detection) 不 monkeypatch — 端点懒 import 的就是真函数, 用例直接
验证透传判据 + 诚实降级 (缺 sample 404 / 无碰撞 0 列表 / 同稿自比 0 冲突)。
"""
import copy
import json
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from fastapi.testclient import TestClient

from src.gui.bridge import app

_SAMPLE = "residential_100sqm.json"
_SAMPLE_PATH = os.path.join(project_root, "data", "sample", _SAMPLE)


def _raw() -> dict:
    """可冲突/可碰撞的 sample 顶层元素数据 (键缺失优雅取空 dict)。

    取 M4 碰撞键 + M5 可冲突键的并集, 保证两条命中路径都有真数据可比对。
    """
    with open(_SAMPLE_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    keys = [
        "structural_beams", "structural_columns", "pipes", "hvac_ducts",
        "outlets", "hvac_grilles",          # M4 碰撞键
        "doors", "windows", "zones", "switches",  # M5 可冲突键补充
    ]
    return {k: data.get(k, []) for k in keys}


def _build_clashing_raw() -> dict:
    """造一份真实会碰撞的 raw (水管段横穿梁段 + 插座贴住柱):

    水管 (2,3)-(8,3) 与梁 (5,1)-(5,7) 垂直相交 → pipe-beam;
    插座 (5,3) 正好落在水管与梁交点上, 距梁 < 0.15 → outlet-beam。
    不用 sample 原数据 (原数据几何不碰撞 → 0), 命中路径必须真命中。
    """
    return {
        "structural_beams": [
            {"id": "sbX", "start": [5.0, 1.0], "end": [5.0, 7.0]},
        ],
        "structural_columns": [
            {"id": "scX", "x": 9.0, "y": 9.0},
        ],
        "pipes": [
            {"id": "pX", "start": [2.0, 3.0], "end": [8.0, 3.0]},
        ],
        "hvac_ducts": [],
        "outlets": [
            {"id": "oX", "x": 5.0, "y": 3.0},
        ],
        "hvac_grilles": [],
    }


# ─── /api/clash ───────────────────────────────────────────────────


def test_clash_sample_present_no_fake():
    """/api/clash 默认 sample 存在 → 200, 返回结构固定 {sample, tolerance_m, tolerance_source, clashes, count}。

    residential_100sqm.json 几何上无跨专业碰撞 → count=0 空列表 (诚实, 不造假)。
    M4 容差 + M1 卡联动: tolerance_source 透出取值来源 (默认走 default.json 规则
    → 'dsl', 显式 query 覆盖 → 'param'), 让前端 M4 占位卡看到「现在生效哪档值」。
    本用例守护的是「结构稳定 + 不崩 + 来源标注不虚标」, 命中路径由 monkeypatch 用例覆盖。
    """
    with TestClient(app) as client:
        resp = client.get(f"/api/clash?sample={_SAMPLE}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sample"] == _SAMPLE
        assert body["count"] == len(body["clashes"])
        assert body["tolerance_m"] == 0.15
        # M4 容差来源透出: 默认 (无 query 覆盖) 走 default.json clash-tolerance-range
        # 规则 params → 来源 "dsl" (专家改 JSON 即变值, 不虚标成 "param")
        assert body["tolerance_source"] == "dsl", \
            f"默认容差应走 dsl 来源, 实际 {body.get('tolerance_source')}"
        # 无碰撞时: 空列表且 count=0 (诚实降级, 不造假)
        assert body["clashes"] == [] and body["count"] == 0
        # 机制层自洽诊断透出 (P12): verify_clashes 结果带出, 前端 ClashSection 消费。
        # 无碰撞 (空列表) → 恒 valid=true / issues 空 (自洽, 不虚标)。
        assert body["clashes_consistent"] is True
        assert body["clashes_issues"] == []


def test_clash_tolerance_source_param_override():
    """M4 容差 + M1 卡联动: 显式 query tolerance_m=0.3 → 来源 "param" (压过 dsl)。

    前端 M4 占位卡据此透出「现在生效 param 档」; 显式 param 优先于 default.json
    规则值 (resolve_clash_tolerance 优先级: param > dsl > default)。"""
    with TestClient(app) as client:
        resp = client.get(f"/api/clash?sample={_SAMPLE}&tolerance_m=0.3")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tolerance_m"] == 0.3
        assert body["tolerance_source"] == "param", \
            f"显式 query 应走 param 来源, 实际 {body.get('tolerance_source')}"


def test_clash_missing_sample_404():
    """sample 文件不存在 → 404 诚实报错 (bridge 红线二: 不造假数据)。"""
    with TestClient(app) as client:
        resp = client.get("/api/clash?sample=no_such_sample.json")
        assert resp.status_code == 404
        assert "样本不存在" in resp.json()["detail"]


def test_clash_hit_path(monkeypatch, tmp_path):
    """命中路径: monkeypatch _load_sample_raw 返回构造的碰撞 raw → 真命中 pipe-beam。

    不碰真 sample 文件 (红线: 不改数据), 只替换端点的读取层,
    验证 detect_clashes 真被调用 + 结果真透传 (a_id/b_id/kind/detail 全字段)。
    """
    from src.gui import bridge as bridge_mod

    monkeypatch.setattr(bridge_mod, "_load_sample_raw", lambda s: _build_clashing_raw())
    with TestClient(bridge_mod.app) as client:
        resp = client.get(f"/api/clash?sample={_SAMPLE}")
        assert resp.status_code == 200
        body = resp.json()
        kinds = {(c["kind"], c["a_id"], c["b_id"]) for c in body["clashes"]}
        # 水管横穿梁 → pipe-beam; 插座落梁上 → outlet-beam
        assert ("pipe-beam", "pX", "sbX") in kinds
        assert ("outlet-beam", "oX", "sbX") in kinds
        assert body["count"] == len(body["clashes"]) >= 2
        # 每条带中文 detail (面板肉眼可读)
        assert all(c["detail"] for c in body["clashes"])
        # P12 自洽诊断: 构造的碰撞 raw 两端 id 都在 raw + kind 合法 → 自洽 valid=true
        assert body["clashes_consistent"] is True


# ─── /api/conflict ────────────────────────────────────────────────


def test_conflict_same_sample_zero():
    """/api/conflict 同稿自比 → 0 冲突 (诚实, 不造假)。"""
    with TestClient(app) as client:
        resp = client.get(f"/api/conflict?sample_a={_SAMPLE}&sample_b={_SAMPLE}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["conflicts"] == []
        assert body["by_category"] == {}
        assert body["summary"]["total"] == 0
        # 全字段透传 (面板要 summary 计数)
        for k in ("value_conflicts", "added", "removed"):
            assert body["summary"][k] == 0
        # P12 自洽诊断透出: 同稿自比 0 冲突 → 汇总/列表恒一致, valid=true (不虚标)
        assert body["summary_consistent"] is True
        assert body["summary_issues"] == []


def test_conflict_missing_sample_404():
    """任一稿 sample 不存在 → 404 诚实报错。"""
    with TestClient(app) as client:
        resp = client.get(f"/api/conflict?sample_a={_SAMPLE}&sample_b=no_such.json")
        assert resp.status_code == 404
        resp2 = client.get(f"/api/conflict?sample_a=no_such.json&sample_b={_SAMPLE}")
        assert resp2.status_code == 404


def test_conflict_hit_path(monkeypatch):
    """命中路径: monkeypatch 两稿读取层 (同 sample 改一个字段 + 删一个元素)
    → 真命中 value + removed, summary 计数对得上。"""
    from src.gui import bridge as bridge_mod

    raw_a = _raw()
    raw_b = copy.deepcopy(raw_a)
    # 稿B: 改第一个门宽 + 删最后一扇门 (真命中, 不造假)。doors 必非空。
    assert raw_b.get("doors"), "sample 应含 doors (可冲突键)"
    target = raw_b["doors"][0]
    target["width_m"] = 9.9  # 与原值必不同 (原值 < 9.9)
    raw_b["doors"].pop()

    def fake_loader(sample: str) -> dict:
        return raw_a if sample == "A.json" else raw_b

    monkeypatch.setattr(bridge_mod, "_load_sample_raw", fake_loader)
    with TestClient(bridge_mod.app) as client:
        resp = client.get("/api/conflict?sample_a=A.json&sample_b=B.json")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] >= 2  # 改值 + 删除, 至少 2 条
        kinds = {c["kind"] for c in body["conflicts"]}
        assert "value" in kinds and "removed" in kinds
        assert body["summary"]["value_conflicts"] >= 1
        assert body["summary"]["removed"] >= 1
        assert body["count"] == body["summary"]["total"]
        assert body["by_category"].get("doors", 0) >= 2
        # 机制层对账透出: summarize 自产必一致 → summary_consistent=true, issues 空
        assert body["summary_consistent"] is True
        assert body["summary_issues"] == []


if __name__ == "__main__":
    # 只跑无 pytest fixture 依赖的用例 (test_direct_run 会直接 exec __main__ 块,
    # 带 monkeypatch/tmp_path 的用例无法独立跑, 归 pytest 专属)。
    test_clash_sample_present_no_fake()
    test_clash_missing_sample_404()
    test_conflict_same_sample_zero()
    test_conflict_missing_sample_404()
    print("OK: bridge clash/conflict endpoint tests passed (fixture-free subset)")
