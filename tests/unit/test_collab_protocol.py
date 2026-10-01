"""
M5 在线协同持久层协议骨架测试 — collab_protocol.py (纯函数, 可注入内存存储)

验证 collab_protocol.py: 锁持久化 / 事件溯源 / 协同快照 / 快照冲突。
全部用 InMemoryCollabStore 跑 (不碰盘), 仿 permission_model 测试范式。
红线二: 只测「机制」(锁/事件/快照能否持久传递), 不断言具体协同协议 (那是业务定)。
__main__ 直跑护栏: 无 fixture + ASCII print (Windows GBK 不崩, 见 test_direct_run.py)。
"""
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from src.agents.src.tools.collab_protocol import (
    InMemoryCollabStore,
    persistent_acquire, persistent_release,
    append_event, make_snapshot, snapshot_conflicts,
)


def test_persistent_acquire_writes_lock_to_store():
    """持久化取锁: 锁落到 store, 下次 load 还在 (进程内「持久」)。"""
    store = InMemoryCollabStore()
    ok, state, _ = persistent_acquire(store, "sheet-a", "alice", "write", now=1.0)
    assert ok is True
    # 同资源 bob 再取写锁 → 被拒 (锁已在 store 里, 互斥生效)
    ok2, _, reason = persistent_acquire(store, "sheet-a", "bob", "write", now=2.0)
    assert ok2 is False
    assert "alice" in reason


def test_persistent_acquire_appends_lock_event():
    """取锁成功后追加一条 lock 事件 (事件溯源)。"""
    store = InMemoryCollabStore()
    persistent_acquire(store, "sheet-a", "alice", "write")
    state = store.load()
    events = state.get("events", [])
    assert any(e["type"] == "lock" and e["actor"] == "alice" for e in events), \
        "取锁应记 lock 事件"
    # seq 单调递增
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs)


def test_persistent_release_appends_unlock_event():
    """释放锁追加 unlock 事件, 且锁从 store 摘除 (之后别人能锁)。"""
    store = InMemoryCollabStore()
    persistent_acquire(store, "sheet-a", "alice", "write")
    persistent_release(store, "sheet-a", "alice")
    state = store.load()
    assert any(e["type"] == "unlock" for e in state["events"])
    # 释放后 bob 能锁
    ok, _, _ = persistent_acquire(store, "sheet-a", "bob", "write")
    assert ok is True


def test_failed_acquire_no_lock_event():
    """取锁被拒 (别人持锁) 不记 lock 事件 (诚实: 只有成功才溯源)。"""
    store = InMemoryCollabStore()
    persistent_acquire(store, "sheet-a", "alice", "write")
    persistent_acquire(store, "sheet-a", "bob", "write")  # 被拒
    events = store.load().get("events", [])
    lock_events = [e for e in events if e["type"] == "lock"]
    assert len(lock_events) == 1, "只有 alice 成功锁记 1 条, bob 被拒不记"


def test_make_snapshot_exposes_write_holders():
    """快照透出: 谁持有哪些写锁 + 事件数。"""
    store = InMemoryCollabStore()
    persistent_acquire(store, "sheet-a", "alice", "write")
    persistent_acquire(store, "sheet-b", "bob", "write")
    snap = make_snapshot(store, designer="alice")
    assert snap["write_holders"] == {"sheet-a": "alice", "sheet-b": "bob"}
    assert snap["designer"] == "alice"
    assert snap["event_count"] >= 2


def test_snapshot_conflicts_detects_same_resource_two_holders():
    """两个设计师快照对同一资源声称不同写持有者 → 冲突。"""
    snap_a = {"write_holders": {"sheet-a": "alice"}}
    snap_b = {"write_holders": {"sheet-a": "bob"}}
    assert snapshot_conflicts(snap_a, snap_b) == ["sheet-a"]


def test_snapshot_conflicts_none_when_distinct_resources():
    """各锁不同资源 → 无冲突。"""
    snap_a = {"write_holders": {"sheet-a": "alice"}}
    snap_b = {"write_holders": {"sheet-b": "bob"}}
    assert snapshot_conflicts(snap_a, snap_b) == []


def test_snapshot_conflicts_same_holder_no_conflict():
    """同一资源但持有者相同 (真共享/一致) → 不算冲突。"""
    snap_a = {"write_holders": {"sheet-a": "alice"}}
    snap_b = {"write_holders": {"sheet-a": "alice"}}
    assert snapshot_conflicts(snap_a, snap_b) == []


def test_json_file_store_roundtrip():
    """JsonFileCollabStore: save/load 往返 (锁 + 事件 都能还原)。"""
    import tempfile
    from src.agents.src.tools.collab_protocol import JsonFileCollabStore
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "collab.json")
        store = JsonFileCollabStore(path)
        persistent_acquire(store, "sheet-x", "carol", "write")
        # 新 store 实例读同一文件 → 锁还在 (真持久, 跨「进程」)
        store2 = JsonFileCollabStore(path)
        ok, _, reason = persistent_acquire(store2, "sheet-x", "dave", "write")
        assert ok is False and "carol" in reason, "跨实例读盘后锁仍互斥"


def test_json_file_store_missing_returns_empty():
    """缺文件 → 空 state (优雅, 不崩)。"""
    import tempfile
    from src.agents.src.tools.collab_protocol import JsonFileCollabStore
    with tempfile.TemporaryDirectory() as tmp:
        store = JsonFileCollabStore(os.path.join(tmp, "no-such.json"))
        assert store.load() == {}


if __name__ == "__main__":
    test_persistent_acquire_writes_lock_to_store()
    test_persistent_acquire_appends_lock_event()
    test_persistent_release_appends_unlock_event()
    test_failed_acquire_no_lock_event()
    test_make_snapshot_exposes_write_holders()
    test_snapshot_conflicts_detects_same_resource_two_holders()
    test_snapshot_conflicts_none_when_distinct_resources()
    test_snapshot_conflicts_same_holder_no_conflict()
    test_json_file_store_roundtrip()
    test_json_file_store_missing_returns_empty()
    # ASCII print — Windows GBK 终端不能 print emoji (直跑护栏见 test_direct_run.py)
    print("OK: all collab protocol tests passed")
