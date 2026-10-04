"""
M5 权限模型机制骨架测试 — 角色/权限/锁/审批 (纯函数库, 仿 M4 clash 范式)

验证 permission_model.py 的 5 个判定函数 (纯函数, 缺角色/未知动作优雅拒绝, 不崩)。
红线二: 只测机制 (给定角色能否做某动作), 不断言「具体权限矩阵该定成什么」
(那是业务回填 DEFAULT_PERMISSIONS 的事)。
__main__ 直跑护栏: 无 fixture + ASCII print (Windows GBK 不崩, 见 test_direct_run.py)。
"""
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from src.agents.src.tools.permission_model import (
    Role, ResourceLock, ChangeRequest, DEFAULT_PERMISSIONS,
    resolve_role, can, acquire_lock, release_lock, approve_change, merge_ready,
    detect_deadlock, check_action_format, validate_permissions_matrix,
)


def test_resolve_role_known_and_unknown():
    """已知角色取到权限; 未知角色 → 空权限 (不崩, 后续 can 自然拒绝)。"""
    designer = resolve_role("designer")
    assert "design.write" in designer.permissions
    unknown = resolve_role("nonexistent-role")
    assert unknown.permissions == (), "未知角色应空权限 (优雅拒绝, 不崩)"


def test_can_lookup():
    """can: 有权限 True / 无权限 False。"""
    reviewer = resolve_role("reviewer")
    assert can(reviewer, "design.read") is True
    assert can(reviewer, "design.write") is False  # reviewer 只能读 + 审批
    admin = resolve_role("admin")
    assert can(admin, "merge.lock") is True


def test_acquire_lock_write_mutex():
    """写锁互斥: 别人持写锁时第三请求被拒; 幂等 (自己重锁) 成功。"""
    locks = []
    ok, locks, _ = acquire_lock(locks, "sheet-a", "alice", "write", now=1.0)
    assert ok
    # bob 想抢 alice 的写锁 → 拒绝
    ok2, locks2, reason = acquire_lock(locks, "sheet-a", "bob", "write", now=2.0)
    assert ok2 is False
    assert "alice" in reason
    assert locks2 is not locks, "应返回新列表 (不改入参)"
    # alice 幂等重锁 → 成功
    ok3, _, reason3 = acquire_lock(locks, "sheet-a", "alice", "write", now=3.0)
    assert ok3 is True and reason3 == "已持有"


def test_acquire_lock_read_not_mutual_exclusive():
    """read 锁不互斥: 多请求都成功。"""
    locks = [ResourceLock("r", "alice", "read")]
    ok, new_locks, _ = acquire_lock(locks, "r", "bob", "read")
    assert ok is True


def test_release_lock_only_owner():
    """释放: 只摘 owner 的写锁, 别人的不动。"""
    locks = [ResourceLock("r", "alice", "write"), ResourceLock("r", "bob", "write")]
    released = release_lock(locks, "r", "alice")
    holders = {l.holder for l in released if l.resource_id == "r"}
    assert holders == {"bob"}, "释放 alice 后只该剩 bob"


def test_approve_change_ok():
    """审批通过: 审批人有 review.approve 且非自审 → approved。"""
    change = ChangeRequest("sheet-a", "alice", "designer")
    reviewer = resolve_role("reviewer")
    approved = approve_change(change, reviewer)
    assert approved.status == "approved"


def test_approve_change_no_permission_stays_pending():
    """审批人无权限 → 保持 pending (诚实记原因)。"""
    change = ChangeRequest("sheet-a", "alice", "designer")
    designer = resolve_role("designer")  # designer 无 review.approve
    rejected = approve_change(change, designer)
    assert rejected.status == "pending"
    assert "denied" in rejected.description


def test_approve_change_no_self_review():
    """自审红线: 不能审批自己提的改动。"""
    change = ChangeRequest("sheet-a", "alice", "designer")
    # 造一个 admin 但 author 也是 admin 同名 → 触发自审拒绝
    self_admin = Role(name="admin", permissions=("review.approve",))
    self_review = ChangeRequest("sheet-a", "admin", "admin")
    denied = approve_change(self_review, self_admin)
    assert denied.status == "pending"
    assert "自己的" in denied.description


def test_merge_ready_all_conditions():
    """合并就绪: 已批准 + 无他人写锁 + 合并人有 merge.lock。"""
    change = ChangeRequest("sheet-a", "alice", "designer", approved_by="bob", status="approved")
    admin = resolve_role("admin")
    assert merge_ready(change, [], admin) is True


def test_merge_rejected_if_still_locked_by_others():
    """他人还持写锁 → 不合 (即使已批准)。"""
    change = ChangeRequest("sheet-a", "alice", "designer", approved_by="bob", status="approved")
    admin = resolve_role("admin")
    locks = [ResourceLock("sheet-a", "bob", "write")]
    assert merge_ready(change, locks, admin) is False


def test_merge_requires_permission():
    """合并人无 merge.lock 权限 → 不合。"""
    change = ChangeRequest("sheet-a", "alice", "designer", approved_by="bob", status="approved")
    designer = resolve_role("designer")  # 无 merge.lock
    assert merge_ready(change, [], designer) is False


# ─── 死锁环检测 (detect_deadlock, 机制层自主子集) ───

def test_deadlock_two_node_cycle():
    """持有 alice 等 bob、持有 bob 等 alice → 检出环 [alice, bob]。"""
    res = detect_deadlock({"alice": "bob", "bob": "alice"})
    assert set(res) == {"alice", "bob"}, f"两节点环应含 alice+bob, 得 {res}"


def test_deadlock_three_node_cycle():
    """a→b→c→a 三节点环 → 全部检出。"""
    res = detect_deadlock({"a": "b", "b": "c", "c": "a"})
    assert set(res) == {"a", "b", "c"}


def test_no_deadlock_linear_wait():
    """线性等待 a→b→c (无回边) → 无环。"""
    assert detect_deadlock({"a": "b", "b": "c"}) == []


def test_no_deadlock_empty():
    """空等待图 → 无环。"""
    assert detect_deadlock({}) == []


def test_deadlock_ignores_unknown_target():
    """等待对象不在图里 (悬空指向) → 优雅忽略, 不误判为环。"""
    assert detect_deadlock({"alice": "ghost"}) == []


def test_self_wait_is_cycle():
    """自己等资源 (自环 a→a) → 检出。"""
    res = detect_deadlock({"alice": "alice"})
    assert res == ["alice"]


# ─── 权限矩阵结构自洽校验 (validate_permissions_matrix / check_action_format,
#     机制层自主子集: 查结构不查业务值) ───

def test_check_action_format_valid():
    """合法动作串 <资源>.<动作> → True。"""
    pm = _pm()
    for a in ("design.read", "review.approve", "merge.lock", "role.manage"):
        assert pm.check_action_format(a), f"{a!r} 应合法"


def test_check_action_format_malformed():
    """畸形动作串 (无点/空半/双点/多级/非字符串) → False。"""
    pm = _pm()
    for a in ("design", "design.", ".write", "design..write", "a.b.c", "", 42, None):
        assert not pm.check_action_format(a), f"{a!r} 应不合法"


def test_validate_matrix_default_valid():
    """DEFAULT_PERMISSIONS 自身结构自洽 → valid=True (占位值命名都合规)。"""
    pm = _pm()
    res = pm.validate_permissions_matrix(pm.DEFAULT_PERMISSIONS)
    assert res["valid"] is True and res["issues"] == [] and res["malformed_actions"] == []


def test_validate_matrix_flags_malformed_action():
    """角色含畸形动作 (design..write) → 检出 + 入 malformed_actions。"""
    pm = _pm()
    res = pm.validate_permissions_matrix({"designer": ("design.read", "design..write")})
    assert res["valid"] is False
    assert "design..write" in res["malformed_actions"]
    assert any("命名不合规" in it for it in res["issues"])


def test_validate_matrix_flags_bad_role_name():
    """角色名含 '.' (与动作串歧义) → 检出。"""
    pm = _pm()
    res = pm.validate_permissions_matrix({"bad.role": ("design.read",)})
    assert res["valid"] is False
    assert any("命名不合规" in it for it in res["issues"])


def test_validate_matrix_flags_duplicate_action():
    """单角色内动作重复声明 → 检出 (结构异味)。"""
    pm = _pm()
    res = pm.validate_permissions_matrix({"designer": ("design.read", "design.read")})
    assert res["valid"] is False
    assert any("重复" in it for it in res["issues"])


def test_validate_matrix_flags_non_string_action():
    """角色值含非字符串动作 (42) → 检出。"""
    pm = _pm()
    res = pm.validate_permissions_matrix({"designer": ("design.read", 42)})
    assert res["valid"] is False
    assert any("非字符串" in it for it in res["issues"])


def test_validate_matrix_malformed_input_no_crash():
    """matrix 非 dict / 值非序列 → 计入 issues 不崩 (优雅降级)。"""
    pm = _pm()
    assert pm.validate_permissions_matrix("not-a-dict")["valid"] is False
    res = pm.validate_permissions_matrix({"designer": 42})  # 值非 list/tuple
    assert res["valid"] is False
    assert any("非动作串序列" in it for it in res["issues"])


def _pm():
    from src.agents.src.tools import permission_model
    return permission_model


if __name__ == "__main__":
    test_resolve_role_known_and_unknown()
    test_can_lookup()
    test_acquire_lock_write_mutex()
    test_acquire_lock_read_not_mutual_exclusive()
    test_release_lock_only_owner()
    test_approve_change_ok()
    test_approve_change_no_permission_stays_pending()
    test_approve_change_no_self_review()
    test_merge_ready_all_conditions()
    test_merge_rejected_if_still_locked_by_others()
    test_merge_requires_permission()
    test_deadlock_two_node_cycle()
    test_deadlock_three_node_cycle()
    test_no_deadlock_linear_wait()
    test_no_deadlock_empty()
    test_deadlock_ignores_unknown_target()
    test_self_wait_is_cycle()
    test_check_action_format_valid()
    test_check_action_format_malformed()
    test_validate_matrix_default_valid()
    test_validate_matrix_flags_malformed_action()
    test_validate_matrix_flags_bad_role_name()
    test_validate_matrix_flags_duplicate_action()
    test_validate_matrix_flags_non_string_action()
    test_validate_matrix_malformed_input_no_crash()
    # ASCII print — Windows GBK 终端不能 print emoji (直跑护栏见 test_direct_run.py)
    print("OK: all permission model tests passed")
