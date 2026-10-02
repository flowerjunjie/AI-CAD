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
    paths = {r.path for r in app.routes if hasattr(r, "path")}
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


if __name__ == "__main__":
    test_collab_snapshot_empty_honest()
    test_no_cross_designer_sync_endpoint()
    # 注: test_collab_snapshot_with_state 需 tmp_path fixture, 只 pytest 跑 (直跑护栏)
    # 这里用一个临时目录手动补一个 (无 fixture, 直跑也能验有 state 态)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        from src.agents.src.tools.collab_protocol import JsonFileCollabStore, persistent_acquire
        import os as _os
        f = _os.path.join(td, "state.json")
        bridge._COLLAB_STATE_PATH = f
        st = JsonFileCollabStore(f)
        persistent_acquire(st, "s1", "carol", "write")
        with TestClient(app) as client:
            r = client.get("/api/collab/snapshot")
            assert r.json()["write_holders"].get("s1") == "carol"
        bridge._COLLAB_STATE_PATH = _os.path.join(project_root, "no-such-collab-<none>.json")
    print("OK: all collab snapshot endpoint tests passed")
