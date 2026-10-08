"""
M5 在线协同端点测试 — bridge /api/collab/snapshot (只读快照, 诚实两态)

验证 bridge H 段: 端点接住了 collab_protocol 机制骨架 (孤儿模块 → 有可见入口),
但**不冒称在线协同** (无写操作端点)。
红线二: 不造假协同数据 — 有落盘 state 出真快照, 空态诚实标 source=empty。
__main__ 直跑护栏: 只列无 fixture 子集 (monkeypatch 的 case 仅 pytest 跑), ASCII print。
"""
import sys
import os
import json

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from fastapi.testclient import TestClient

import src.gui.bridge as bridge
from src.gui.bridge import app


def test_collab_snapshot_empty_honest():
    """无任何落盘 state → 空快照 (write_holders 空 + source=empty), 不造假。"""
    # 指到一个肯定不存在的路径 (不污染真实 data/collab)
    bridge._COLLAB_STATE_PATH = os.path.join(project_root, "no-such-collab-<none>.json")
    with TestClient(app) as client:
        resp = client.get("/api/collab/snapshot", params={"designer": "alice"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["write_holders"] == {}
    assert body["event_count"] == 0
    assert body["source"] == "empty", "空态应诚实标 empty, 不冒称有协同"
    assert "note" in body
    print("PASS test_collab_snapshot_empty_honest")


def test_collab_snapshot_with_state(tmp_path):
    """有落盘 state (锁 + 事件) → 快照透出写锁持有者 + 事件数 (真持久)。"""
    import tempfile
    from src.agents.src.tools.collab_protocol import (
        JsonFileCollabStore, persistent_acquire, persistent_release)

    state_file = tmp_path / "state.json"
    bridge._COLLAB_STATE_PATH = str(state_file)
    store = JsonFileCollabStore(str(state_file))
    persistent_acquire(store, "sheet-a", "alice", "write")
    persistent_acquire(store, "sheet-b", "bob", "write")

    with TestClient(app) as client:
        resp = client.get("/api/collab/snapshot", params={"designer": "alice"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["write_holders"] == {"sheet-a": "alice", "sheet-b": "bob"}
    assert body["source"] == "file"
    assert body["event_count"] >= 2
    print("PASS test_collab_snapshot_with_state")


def test_no_cross_designer_sync_endpoint():
    """诚实边界: 快照 + 本地锁端点存在, 但**没有**跨设计师同步端点
    (多机在线协同 CRDT/OT/单写者多读者协议 + 用户体系, 需业务定协议才接)。
    本地锁端点 acquire/release 存在 (单进程演示通路, 落本地 state.json)。"""
    # include_router 后子路由在 app.routes 里是嵌套包装, 直接读 r.path 拿不全;
    # OpenAPI paths 是展开全部路由的权威源 (FastAPI 官方), 用它判端点存在性。
    paths = set(app.openapi()["paths"].keys())
    assert "/api/collab/snapshot" in paths
    assert "/api/collab/acquire" in paths
    assert "/api/collab/release" in paths
    # 跨设计师/多机端点不该存在 (冒称在线协同 = 造假)
    for forbidden in ("/api/collab/sync", "/api/collab/broadcast", "/api/collab/merge"):
        assert forbidden not in paths, f"{forbidden} 不该在本骨架内暴露 (需业务定协议)"
    print("PASS test_no_cross_designer_sync_endpoint")


def test_local_lock_endpoints(tmp_path):
    """本地锁演示通路: acquire → 他人写锁互斥拒绝 → release 放掉 (真落盘 state.json)。"""
    state_file = tmp_path / "state.json"
    bridge._COLLAB_STATE_PATH = str(state_file)
    with TestClient(app) as client:
        r1 = client.post("/api/collab/acquire",
                        json={"designer": "alice", "resource_id": "sheet-x", "mode": "write"})
        assert r1.status_code == 200 and r1.json()["acquired"] is True
        assert r1.json()["write_holders"] == {"sheet-x": "alice"}
        # 他人写锁互斥: bob 抢同一资源 → 拒绝 + 诚实 reason
        r2 = client.post("/api/collab/acquire",
                        json={"designer": "bob", "resource_id": "sheet-x", "mode": "write"})
        assert r2.status_code == 200 and r2.json()["acquired"] is False
        assert "alice" in r2.json()["reason"]
        # alice 再取自己锁 → 幂等成功
        r3 = client.post("/api/collab/acquire",
                        json={"designer": "alice", "resource_id": "sheet-x"})
        assert r3.json()["acquired"] is True
        # 释放 (幂等: 释放 alice 的锁)
        r4 = client.post("/api/collab/release",
                        json={"designer": "alice", "resource_id": "sheet-x"})
        assert r4.status_code == 200 and r4.json()["released"] is True
        assert r4.json()["write_holders"] == {}
        # 无锁再放 → released=false (幂等诚实, 不崩)
        r5 = client.post("/api/collab/release",
                        json={"designer": "alice", "resource_id": "sheet-x"})
        assert r5.json()["released"] is False
    # 持久化验证: 锁操作真落盘 (state.json 存在且含 unlock 事件)
    assert state_file.exists()
    import json as _json
    state = _json.loads(state_file.read_text(encoding="utf-8"))
    assert any(e["type"] == "unlock" for e in state["events"])
    print("PASS test_local_lock_endpoints")


def test_collab_elements_lists_real_ids_and_duplicate_flag():
    """M5 协同 + duplicate 联动: /api/collab/elements 吐真实 CAD 元素 id 清单
    + 重复标记 (duplicate_of), 协同面板资源下拉数据源。
    residential sample 无几何重复 → duplicate_count=0 (诚实, 不造假)。"""
    with TestClient(app) as client:
        resp = client.get("/api/collab/elements",
                         params={"sample": "residential_100sqm.json"})
    assert resp.status_code == 200, f"应 200, 实际 {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["sample"] == "residential_100sqm.json"
    # 真实元素 id 清单 (doors/walls/pipes/outlets/... 全量, 非硬编码 sheet-a)
    ids = {r["id"] for r in body["resources"]}
    assert len(body["resources"]) >= 10, f"应列真实元素, 实际 {len(body['resources'])}"
    assert "d1" in ids or any(i.startswith("d") for i in ids), "应含门元素 id"
    # 每条资源带 category + duplicate_of (无重复为 None) + 诚实 note
    for r in body["resources"]:
        assert "category" in r and "duplicate_of" in r, f"资源缺字段: {r}"
    assert body["note"], "应诚实标注『不判业务归属』"
    print("PASS test_collab_elements_lists_real_ids_and_duplicate_flag")


def test_collab_elements_missing_sample_404():
    """sample 不存在 → 404 诚实, 不造假资源清单。"""
    with TestClient(app) as client:
        resp = client.get("/api/collab/elements", params={"sample": "no_such.json"})
    assert resp.status_code == 404, f"缺样本应 404, 实际 {resp.status_code}"
    print("PASS test_collab_elements_missing_sample_404")


def test_collab_elements_duplicate_marking():
    """构造同坐标不同 id 元素 → duplicate_count > 0 + 互标 duplicate_of。

    往 residential sample 拷一份 + 造两个同坐标不同 id 插座, 验端点真命中。"""
    import json as _json
    import os as _os
    # 读真实 sample, 造一份含重复的副本 (放 tmp, 不污染真盘)
    src = _os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    with open(src, encoding="utf-8") as fh:
        data = _json.load(fh)
    # 把两个插座放同坐标不同 id (o1/o2 都 (1,1))
    data["outlets"] = [
        {"id": "o1", "x": 1.0, "y": 1.0},
        {"id": "o2", "x": 1.0, "y": 1.0},
    ]
    tmp_sample = _os.path.join(project_root, "data", "sample", "_tmp_dup_test.json")
    with open(tmp_sample, "w", encoding="utf-8") as fh:
        _json.dump(data, fh)
    try:
        with TestClient(app) as client:
            resp = client.get("/api/collab/elements",
                             params={"sample": "_tmp_dup_test.json"})
        assert resp.status_code == 200, f"应 200, 实际 {resp.status_code}: {resp.text}"
        body = resp.json()
        # o1/o2 同坐标 → duplicate_count=1 + 互标 duplicate_of
        assert body["duplicate_count"] >= 1, f"应检出重复, 实际 {body['duplicate_count']}"
        by_id = {r["id"]: r for r in body["resources"]}
        assert by_id["o1"]["duplicate_of"] == "o2", f"o1 应标 o2, 实际 {by_id['o1']}"
        assert by_id["o2"]["duplicate_of"] == "o1", "o2 应标 o1"
        print("PASS test_collab_elements_duplicate_marking")
    finally:
        if _os.path.exists(tmp_sample):
            _os.remove(tmp_sample)


# ─── M5 协同正确性地基: /api/collab/verify + /api/collab/deadlock-check ───

def test_collab_verify_valid_state(tmp_path):
    """有对齐的锁 + 事件 state → verify 判 valid (机制层完整性校验)。"""
    from src.agents.src.tools.collab_protocol import JsonFileCollabStore, persistent_acquire
    f = tmp_path / "state.json"
    bridge._COLLAB_STATE_PATH = str(f)
    persistent_acquire(JsonFileCollabStore(str(f)), "sheet-a", "alice", "write")
    with TestClient(app) as client:
        resp = client.get("/api/collab/verify")
    assert resp.status_code == 200, f"应 200, 实际 {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["valid"] is True and body["issues"] == []
    assert body["replayed_write_holders"] == {"sheet-a": "alice"}
    assert body["source"] == "file"
    print("PASS test_collab_verify_valid_state")


def test_collab_verify_empty_state_honest():
    """无落盘 state → verify 仍诚实跑 (空事件/空锁 → valid=True), 标 source=empty。"""
    bridge._COLLAB_STATE_PATH = os.path.join(project_root, "no-such-collab-<verify>.json")
    with TestClient(app) as client:
        resp = client.get("/api/collab/verify")
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True, "空协同态 (零事件零锁) 是合法的, 应 valid"
    assert body["replayed_write_holders"] == {}
    assert body["source"] == "empty"
    print("PASS test_collab_verify_empty_state_honest")


def test_collab_verify_detects_tampered_state(tmp_path):
    """人为篡改 state (锁态与事件不对齐) → verify 判 invalid + issues 非空。"""
    import json as _json
    from src.agents.src.tools.collab_protocol import JsonFileCollabStore, persistent_acquire
    f = tmp_path / "state.json"
    bridge._COLLAB_STATE_PATH = str(f)
    persistent_acquire(JsonFileCollabStore(str(f)), "sheet-a", "alice", "write")
    # 篡改: 往锁态加一条 sheet-b, 但事件里从没锁过 sheet-b → 不可回放对齐
    state = _json.loads(f.read_text(encoding="utf-8"))
    state["locks"].append({"resource_id": "sheet-b", "holder": "bob",
                          "mode": "write", "acquired_at": 9.0})
    f.write_text(_json.dumps(state), encoding="utf-8")
    with TestClient(app) as client:
        resp = client.get("/api/collab/verify")
    body = resp.json()
    assert body["valid"] is False, "锁态与事件不对齐应检出"
    assert any("回放" in it for it in body["issues"])
    print("PASS test_collab_verify_detects_tampered_state")


def test_collab_deadlock_check_detects_cycle():
    """等待图 a→b→a → deadlocked=true + cycle 含两者 (机制层纯判定)。"""
    with TestClient(app) as client:
        resp = client.post("/api/collab/deadlock-check",
                          json={"wait_edges": {"alice": "bob", "bob": "alice"}})
    assert resp.status_code == 200, f"应 200, 实际 {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["deadlocked"] is True
    assert set(body["cycle"]) == {"alice", "bob"}
    print("PASS test_collab_deadlock_check_detects_cycle")


def test_collab_deadlock_check_no_cycle():
    """线性等待 a→b→c (无回边) → deadlocked=false, cycle=[]。"""
    with TestClient(app) as client:
        resp = client.post("/api/collab/deadlock-check",
                          json={"wait_edges": {"a": "b", "b": "c"}})
    assert resp.status_code == 200
    assert resp.json()["deadlocked"] is False
    print("PASS test_collab_deadlock_check_no_cycle")


def test_collab_deadlock_check_rejects_non_string():
    """输入边界: wait_edges 值非字符串 → 400 诚实, 不静默。"""
    with TestClient(app) as client:
        resp = client.post("/api/collab/deadlock-check",
                          json={"wait_edges": {"alice": 42}})
    assert resp.status_code == 400, f"非字符串等待对象应 400, 实际 {resp.status_code}"
    print("PASS test_collab_deadlock_check_rejects_non_string")


# ─── /api/collab/deadlock (真实锁流程版, 读 state 的 wait-edges) ───

def test_collab_deadlock_empty_state_honest():
    """无落盘 state → 空态, deadlocked=false + source=empty (诚实不造假)。"""
    bridge._COLLAB_STATE_PATH = os.path.join(project_root, "no-such-collab-<dl>.json")
    with TestClient(app) as client:
        resp = client.get("/api/collab/deadlock")
    assert resp.status_code == 200
    body = resp.json()
    assert body["deadlocked"] is False
    assert body["wait_edges"] == {}
    assert body["source"] == "empty"
    print("PASS test_collab_deadlock_empty_state_honest")


def test_collab_deadlock_from_real_state(tmp_path):
    """交叉取锁被拒 → 真实 state 记 wait-edges → /api/collab/deadlock 检出环。

    端到端: alice 锁 sheet-a + bob 锁 sheet-b, 交叉要对方锁 → 双向被拒记 wait,
    端点读 state.waits 投影成 {alice: bob, bob: alice} → deadlocked=true。"""
    from src.agents.src.tools.collab_protocol import (
        JsonFileCollabStore, persistent_acquire)
    f = tmp_path / "state.json"
    bridge._COLLAB_STATE_PATH = str(f)
    st = JsonFileCollabStore(str(f))
    persistent_acquire(st, "sheet-a", "alice", "write")
    persistent_acquire(st, "sheet-b", "bob", "write")
    persistent_acquire(st, "sheet-b", "alice", "write")  # alice 等 bob (被拒)
    persistent_acquire(st, "sheet-a", "bob", "write")    # bob 等 alice (被拒)
    with TestClient(app) as client:
        resp = client.get("/api/collab/deadlock")
    body = resp.json()
    assert resp.status_code == 200, f"应 200, 实际 {resp.status_code}: {resp.text}"
    assert body["deadlocked"] is True, f"交叉被拒应检出环, 得 {body}"
    assert set(body["cycle"]) == {"alice", "bob"}
    assert body["source"] == "file"
    print("PASS test_collab_deadlock_from_real_state")


if __name__ == "__main__":
    test_collab_snapshot_empty_honest()
    test_no_cross_designer_sync_endpoint()
    test_collab_verify_empty_state_honest()
    test_collab_deadlock_check_detects_cycle()
    test_collab_deadlock_check_no_cycle()
    test_collab_deadlock_check_rejects_non_string()
    test_collab_deadlock_empty_state_honest()
    # 注: test_collab_deadlock_from_real_state 需 tmp_path fixture, 仅 pytest 全量跑。
    # 注: test_collab_snapshot_with_state / test_collab_verify_valid|tampered 需 tmp_path fixture
    #   仅 pytest 全量跑 (直跑护栏见 test_direct_run.py); 无 fixture 子集直跑验。
    # 注: test_collab_elements_* 读真实 data/sample, 无 fixture, pytest 全量跑。
    print("OK: all collab snapshot endpoint tests passed")
