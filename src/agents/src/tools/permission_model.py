"""
M5 权限模型机制骨架 (多设计师协作 — 可自主子集)

纯函数、无 I/O、可单测 — 仿 clash_detection.py (M4) / conflict_detection.py (M5 冲突) 范式。
给「多个设计师同时改同一份施工图」提供一套**最小可用**的协作权限机制:
角色 → 权限 → 资源锁 → 改动审批。业务侧只填配置 (角色/权限矩阵), 不改本模块。

边界 (诚实, 呼应 CLAUDE.md「不虚标」):
  - 这是**机制骨架**, 角色/权限的具体条目是**占位配置** (DEFAULT_PERMISSIONS),
    需业务定夺后回填 — 就像 M1 数值回填 / M2 图层约定。机制通, 值待人。
  - 默认不接 auth 后端 (无 DB / 无 token): 纯内存判定, 可单测。接真实用户体系
    是后续一层, 本骨架只定「给定角色, 能否做某动作」的判据。

红线: 纯函数库, 不碰 ezdxf/langgraph/DB; 未知角色/动作优雅拒绝 (不崩, 返回可判定结果)。
"""
from dataclasses import dataclass, field


# ─── 数据模型 ─────────────────────────────────────────────────

@dataclass(frozen=True)
class Role:
    """设计师角色 (占位: 业务可加任意角色, 机制不变)。"""
    name: str
    permissions: tuple[str, ...] = ()


@dataclass
class ResourceLock:
    """资源锁: 某资源被某设计师持有 (协作编辑的写互斥)。"""
    resource_id: str
    holder: str
    mode: str = "write"  # write / read (read 不互斥)
    acquired_at: float = 0.0


@dataclass
class ChangeRequest:
    """改动申请: 设计师对某资源提的改动, 需审批 (权限闸)。"""
    resource_id: str
    author: str
    role_name: str
    description: str = ""
    approved_by: str | None = None
    status: str = "pending"  # pending / approved / rejected


# ─── 权限矩阵 (占位配置, 业务回填) ────────────────────────────

# 占位默认权限: 常见角色 → 可做动作。业务定夺「谁到底能干什么」时改这里即可。
# 动作命名约定: <资源>.<动作> (如 design.read / design.write / review.approve / merge.lock)。
DEFAULT_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "designer": ("design.read", "design.write"),
    "reviewer": ("design.read", "review.approve"),
    "admin": ("design.read", "design.write", "review.approve", "merge.lock", "role.manage"),
}


def resolve_role(role_name: str, permissions: dict[str, tuple[str, ...]] | None = None) -> Role:
    """按名字取角色。未知角色 → 空权限 Role (不崩, 后续 can 判定自然拒绝)。"""
    matrix = permissions if permissions is not None else DEFAULT_PERMISSIONS
    return Role(name=role_name, permissions=tuple(matrix.get(role_name, ())))


# ─── 判定函数 (纯, 可单测) ────────────────────────────────────

def can(role: Role, action: str) -> bool:
    """角色能否做某动作 (纯查表)。"""
    return action in role.permissions


def acquire_lock(
    locks: list[ResourceLock],
    resource_id: str,
    requester: str,
    mode: str = "write",
    now: float = 0.0,
) -> tuple[bool, list[ResourceLock], str]:
    """请求资源锁。返回 (能否锁成功, 更新后锁列表, 原因)。

    写锁互斥规则:
      - 资源已有 write 锁且持有者 != requester → 拒绝 (别人正改, 不能抢)。
      - 无 write 锁 → requester 获得 write 锁。
    read 锁不互斥 (多个可读), 简化处理: read 请求总是成功 (不阻塞读)。
    返回新列表 (不可变风格, 不改入参)。
    """
    has_write = any(l.resource_id == resource_id and l.mode == "write" for l in locks)
    if mode == "write" and has_write:
        holder = next(l.holder for l in locks
                      if l.resource_id == resource_id and l.mode == "write")
        if holder != requester:
            return False, list(locks), f"资源 {resource_id} 正被 {holder} 写锁占用"
        # 自己已持有 → 幂等成功
        return True, list(locks), "已持有"
    new_locks = [l for l in locks if not (l.resource_id == resource_id and l.mode == "write")]
    new_locks.append(ResourceLock(resource_id, requester, mode, now))
    return True, new_locks, "锁定成功"


def release_lock(locks: list[ResourceLock], resource_id: str, owner: str) -> list[ResourceLock]:
    """释放某资源上 owner 持有的锁 (写锁才需显式释放; 返回新列表)。"""
    return [l for l in locks
            if not (l.resource_id == resource_id and l.holder == owner and l.mode == "write")]


def approve_change(
    change: ChangeRequest,
    approver_role: Role,
) -> ChangeRequest:
    """审批改动申请: 审批人须有 review.approve 权限且不能是自审。

    返回更新状态后的 ChangeRequest (不可变风格)。权限不足/自审 → 保持 pending + 记原因。
    """
    if not can(approver_role, "review.approve"):
        return ChangeRequest(
            change.resource_id, change.author, change.role_name,
            f"denied: {approver_role.name} 无 review.approve 权限", "pending")
    if approver_role.name == change.author:
        # 自审红线: 不能审批自己提的改动
        return ChangeRequest(
            change.resource_id, change.author, change.role_name,
            "denied: 不能审批自己的改动", "pending")
    return ChangeRequest(
        change.resource_id, change.author, change.role_name,
        change.description, change.approved_by, "approved")


def merge_ready(change: ChangeRequest, locks: list[ResourceLock], merger_role: Role) -> bool:
    """合并是否就绪: 已批准 + 目标资源无他人写锁 + 合并人有 merge.lock 权限。"""
    if change.status != "approved":
        return False
    if not can(merger_role, "merge.lock"):
        return False
    held_by_others = any(
        l.resource_id == change.resource_id and l.mode == "write"
        and l.holder != change.author for l in locks)
    return not held_by_others
