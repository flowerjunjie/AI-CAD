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
    verify_event_log,
    record_wait, clear_waits_for, wait_edges_of,
    check_deadlock_from_state,
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


# ─── 事件日志完整性校验 (verify_event_log, 协同正确性地基) ───

def _state_with_lock_events():
    """构造一份「合法」协同 state: alice 锁 sheet-a + carol 锁 sheet-b, 锁态与事件对齐。"""
    store = InMemoryCollabStore()
    persistent_acquire(store, "sheet-a", "alice", "write", now=1.0)
    persistent_acquire(store, "sheet-b", "carol", "write", now=2.0)
    return store.load()


def test_verify_event_log_valid_state():
    """合法 state: 锁态与事件回放对齐 → valid=True, issues=[]。"""
    state = _state_with_lock_events()
    res = verify_event_log(state)
    assert res["valid"] is True
    assert res["issues"] == []
    assert res["replayed_write_holders"] == {"sheet-a": "alice", "sheet-b": "carol"}


def test_verify_event_log_clean_log_seq():
    """seq 断裂 (跳号) → 检出 (events[i].seq 必须 == i)。"""
    state = _state_with_lock_events()
    state["events"][1]["seq"] = 7  # 人为制造跳号
    res = verify_event_log(state)
    assert res["valid"] is False
    assert any("seq" in it for it in res["issues"])


def test_verify_event_log_lock_mismatch_detected():
    """锁态与事件不可回放对齐: 改了持久锁但没对应事件 → 检出。"""
    state = _state_with_lock_events()
    # 持久锁态多写一条 alice→sheet-c, 但事件里从没锁过 sheet-c
    state["locks"].append({"resource_id": "sheet-c", "holder": "alice",
                            "mode": "write", "acquired_at": 9.0})
    res = verify_event_log(state)
    assert res["valid"] is False
    assert any("回放" in it for it in res["issues"])


def test_verify_event_log_unlock_release_reflects():
    """释放锁后, 回放与持久锁态一致 → 仍 valid (lock+unlock 自洽)。"""
    store = InMemoryCollabStore()
    persistent_acquire(store, "sheet-a", "alice", "write", now=1.0)
    persistent_release(store, "sheet-a", "alice")
    res = verify_event_log(store.load())
    assert res["valid"] is True
    assert res["replayed_write_holders"] == {}


def test_verify_event_log_malformed_events_no_crash():
    """events 非 list / 事件缺字段 → 计入 issues, 不崩 (优雅降级)。"""
    state = _state_with_lock_events()
    state["events"] = "not-a-list"
    res = verify_event_log(state)
    assert res["valid"] is False
    assert res["replayed_write_holders"] == {}


def test_verify_event_log_missing_field_flagged():
    """事件缺必填字段 → 检出 (type/actor/resource_id/seq)。"""
    state = _state_with_lock_events()
    del state["events"][0]["actor"]  # 摘掉一条事件的 actor
    res = verify_event_log(state)
    assert res["valid"] is False
    assert any("缺字段" in it for it in res["issues"])


# ─── wait-edge 采集 + 死锁检测端到端 (机制层自主子集) ───

def test_persistent_acquire_rejected_records_wait():
    """取锁被拒 (他人持写锁) → 记一条 wait-edge (requester 等 holder)。"""
    store = InMemoryCollabStore()
    persistent_acquire(store, "sheet-a", "alice", "write")
    ok, state, _ = persistent_acquire(store, "sheet-a", "bob", "write")  # 被拒
    assert ok is False
    waits = state.get("waits", [])
    assert any(w["requester"] == "bob" and w["holder"] == "alice" for w in waits), \
        f"被拒应记 bob 等 alice, 得 {waits}"


def test_persistent_acquire_success_no_wait():
    """取锁成功 (锁空) → 不记 wait-edge (无需等待)。"""
    store = InMemoryCollabStore()
    ok, state, _ = persistent_acquire(store, "sheet-a", "alice", "write")
    assert ok is True
    assert state.get("waits", []) == []


def test_wait_cleared_on_acquire_success():
    """bob 先被拒记 wait; alice 放锁后 bob 再取成功 → wait-edge 消散。"""
    store = InMemoryCollabStore()
    persistent_acquire(store, "sheet-a", "alice", "write")
    persistent_acquire(store, "sheet-a", "bob", "write")  # 被拒, 记 bob 等 alice
    persistent_release(store, "sheet-a", "alice")         # 放锁
    ok, state, _ = persistent_acquire(store, "sheet-a", "bob", "write")  # 成功
    assert ok is True
    assert state.get("waits", []) == [], "拿到锁后等待意图应消散"


def test_wait_cleared_on_release():
    """放锁 (owner) → 清掉 owner 相关 wait-edge (等它的人不再等)。"""
    store = InMemoryCollabStore()
    persistent_acquire(store, "sheet-a", "alice", "write")
    persistent_acquire(store, "sheet-a", "bob", "write")  # 记 bob 等 alice
    state = persistent_release(store, "sheet-a", "alice")
    # alice 放锁后, bob 等 alice 的 edge 应清掉 (alice 不再持锁)
    assert wait_edges_of(state) == {}, f"放锁后应清 wait-edge, 得 {wait_edges_of(state)}"


def test_wait_edges_of_projects_to_deadlock_input():
    """wait_edges_of: state['waits'] → {requester: holder} (同请求多 holder 取首个)。"""
    state = {
        "waits": [
            {"requester": "bob", "holder": "alice"},
            {"requester": "bob", "holder": "carol"},  # 同请求第 2 条, 投影取首个
        ]
    }
    assert wait_edges_of(state) == {"bob": "alice"}


def test_check_deadlock_cross_two_designers():
    """端到端: alice 锁 A + bob 锁 B, 交叉要对方的锁 → 真实 state 检出等待环。

    构造: alice 持 sheet-a, bob 持 sheet-b;
      alice 想锁 sheet-b → 被拒, 记 alice 等 bob;
      bob 想锁 sheet-a   → 被拒, 记 bob 等 alice;
    → wait_edges = {alice: bob, bob: alice} → detect_deadlock 检出环。"""
    store = InMemoryCollabStore()
    persistent_acquire(store, "sheet-a", "alice", "write")
    persistent_acquire(store, "sheet-b", "bob", "write")
    persistent_acquire(store, "sheet-b", "alice", "write")  # alice 等 bob
    persistent_acquire(store, "sheet-a", "bob", "write")    # bob 等 alice
    res = check_deadlock_from_state(store.load())
    assert res["deadlocked"] is True
    assert set(res["cycle"]) == {"alice", "bob"}, f"应检出 alice↔bob 环, 得 {res}"


def test_check_deadlock_no_cycle_when_linear():
    """线性等待 (alice 等 bob, 无回边) → 无环。"""
    store = InMemoryCollabStore()
    persistent_acquire(store, "sheet-a", "alice", "write")
    persistent_acquire(store, "sheet-b", "bob", "write")
    persistent_acquire(store, "sheet-b", "alice", "write")  # 仅 alice 等 bob, 单向
    res = check_deadlock_from_state(store.load())
    assert res["deadlocked"] is False and res["cycle"] == []


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
    test_verify_event_log_valid_state()
    test_verify_event_log_clean_log_seq()
    test_verify_event_log_lock_mismatch_detected()
    test_verify_event_log_unlock_release_reflects()
    test_verify_event_log_malformed_events_no_crash()
    test_verify_event_log_missing_field_flagged()
    test_persistent_acquire_rejected_records_wait()
    test_persistent_acquire_success_no_wait()
    test_wait_cleared_on_acquire_success()
    test_wait_cleared_on_release()
    test_wait_edges_of_projects_to_deadlock_input()
    test_check_deadlock_cross_two_designers()
    test_check_deadlock_no_cycle_when_linear()
    # ASCII print — Windows GBK 终端不能 print emoji (直跑护栏见 test_direct_run.py)
    print("OK: all collab protocol tests passed")
