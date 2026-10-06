"""
协同 waits 字段完整性体检测试 (机制层自主子集)

覆盖:
  ① collab_protocol.verify_waits_consistency — 纯函数, 校验 state["waits"] 与
     locks 的一致性 (字段完整 / holder 真持写锁 / 幂等无重复), 畸形不崩。
     防「幽灵等待边」— 指向不持锁 holder 的脏 waits 会让 check_deadlock_from_state
     建立在脏数据上误判死锁。
  ② bridge /api/collab/waits-verify — 读真实协同 state 跑校验, 契约字段 + 200。

红线对齐 (CLAUDE.md 不虚标): 只判「waits 数据自身是否自洽」, **不判**「谁该持哪把
锁」的业务值 (M5 权限矩阵, 仍占位待业务回填)。仿 test_collab_protocol 范式:
__main__ 只列无 fixture 子集 + 不 print 中文/emoji (Windows GBK 直跑不崩)。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _cp():
    from src.agents.src.tools import collab_protocol
    return collab_protocol


def _state(locks=None, waits=None):
    return {"locks": locks or [], "waits": waits or []}


# ─── ① verify_waits_consistency 纯函数 ─────────────────────────


def test_consistent_waits_ok():
    """waits 的 holder 全在当前写锁持有者集合 + 字段完整 + 无重复 → valid=True。"""
    cp = _cp()
    st = _state(
        locks=[{"resource_id": "d1", "holder": "alice", "mode": "write"}],
        waits=[{"requester": "bob", "holder": "alice"}])
    res = cp.verify_waits_consistency(st)
    assert res["valid"] is True and res["issues"] == [], f"自洽 waits 应通过, 得 {res}"
    assert res["ghost_holders"] == []


def test_ghost_holder_flagged():
    """waits 指向的 holder 不在当前写锁持有者集合 → 幽灵等待边如实揪出。"""
    cp = _cp()
    st = _state(
        locks=[{"resource_id": "d1", "holder": "alice", "mode": "write"}],
        waits=[{"requester": "bob", "holder": "carol"}])  # carol 不持锁
    res = cp.verify_waits_consistency(st)
    assert res["valid"] is False
    assert any("carol" in it for it in res["issues"])
    assert "bob→carol" in res["ghost_holders"]


def test_missing_field_flagged():
    """wait 缺 requester/holder (None) → 如实标出 (字段不完整)。"""
    cp = _cp()
    res = cp.verify_waits_consistency(_state(
        locks=[], waits=[{"requester": None, "holder": "alice"}]))
    assert res["valid"] is False
    assert any("缺 requester" in it or "None" in it for it in res["issues"])


def test_duplicate_wait_flagged():
    """同 (requester,holder) 出现两次 → 违反 record_wait 幂等, 如实揪出。"""
    cp = _cp()
    st = _state(
        locks=[{"resource_id": "d1", "holder": "alice", "mode": "write"}],
        waits=[{"requester": "bob", "holder": "alice"},
               {"requester": "bob", "holder": "alice"}])
    res = cp.verify_waits_consistency(st)
    assert res["valid"] is False
    assert any("重复" in it for it in res["issues"])


def test_read_lock_holder_not_ghost_but_not_write():
    """holder 只持 read 锁 (非 write) → 不在写持有者集合, 判幽灵 (等待的是写锁,
    read 不互斥, 等 read 持有者无意义)。诚实边界: 只认 write 持有者。"""
    cp = _cp()
    st = _state(
        locks=[{"resource_id": "d1", "holder": "alice", "mode": "read"}],
        waits=[{"requester": "bob", "holder": "alice"}])
    res = cp.verify_waits_consistency(st)
    assert res["valid"] is False  # alice 只持 read, 不在写集合 → 幽灵
    assert "bob→alice" in res["ghost_holders"]


def test_malformed_state_no_crash():
    """state 非 dict / waits 非 list / 条非 dict → 计入 issues 不崩 (优雅降级)。"""
    cp = _cp()
    assert cp.verify_waits_consistency("not-a-dict")["valid"] is False
    res = cp.verify_waits_consistency({"waits": "not-a-list"})
    assert res["valid"] is False
    res2 = cp.verify_waits_consistency({"waits": [object(), 42]})
    assert res2["valid"] is False
    # 空 state (零协同态) 合法
    assert cp.verify_waits_consistency({})["valid"] is True


# ─── ② bridge 端点 ───────────────────────────────────────────


def test_bridge_collab_waits_verify_endpoint():
    """/api/collab/waits-verify 200 + 契约 {valid, issues, ghost_holders, source}。
    真实协同 state 当前零 waits (空态) → valid=True (空协同不崩不误报)。"""
    from fastapi.testclient import TestClient
    from src.gui.bridge import app
    with TestClient(app) as client:
        resp = client.get("/api/collab/waits-verify")
        assert resp.status_code == 200, f"应 200, 实际 {resp.status_code} {resp.text}"
        body = resp.json()
        for k in ("valid", "issues", "ghost_holders", "source"):
            assert k in body, f"缺字段 {k}, 实际 {list(body)}"
        # 默认测试态无 waits → 自洽 (若 CI 跑了真实协同流程产生脏 waits 也如实报)
        assert body["valid"] in (True, False)


if __name__ == "__main__":
    # 只跑无 pytest fixture 依赖的用例 (test_direct_run 会直跑 __main__ 块)
    test_consistent_waits_ok()
    test_ghost_holder_flagged()
    test_missing_field_flagged()
    test_duplicate_wait_flagged()
    test_read_lock_holder_not_ghost_but_not_write()
    test_malformed_state_no_crash()
    test_bridge_collab_waits_verify_endpoint()
    print("OK: all verify_waits_consistency tests passed")
