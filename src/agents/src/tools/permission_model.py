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
import re
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


# ─── 权限矩阵结构自洽校验 (机制层自主子集, 纯函数) ──────────────
# 边界 (诚实, 呼应 CLAUDE.md「不虚标」): 校验「矩阵结构是否自洽」(角色/动作命名
# 规范、值类型、无畸形条目) — **不**判定「谁到底能干什么」(那是业务回填值的红线,
# 本层只查结构, 不虚标终值)。纯函数, 畸形输入优雅降级不崩。消费侧 (can/resolve_role)
# 之前可挂此校验, 把「手滑写错动作串 → 静默全拒绝」从线上静默提前到可见告警。

# 动作命名规范: <资源>.<动作> — 恰好一个 ".", 两侧非空 (见 L51 约定)。
# 合法示例 design.read / review.approve / merge.lock; 畸形: "" / "design" (无点) /
# "design." (后半空) / "design..write" (双点) / "a.b.c" (多级点分, 非本层约定)。
_ACTION_FMT = re.compile(r"^[^.]+\.[^.]+$")


def check_action_format(action: str) -> bool:
    """动作命名是否符 `<资源>.<动作>` 规范 (纯判定, 不崩)。

    非字符串 / 空 / 缺点 / 空半 / 双点 / 多级点分 → False。合法 → True。"""
    if not isinstance(action, str):
        return False
    return bool(_ACTION_FMT.match(action))


def validate_permissions_matrix(matrix: dict) -> dict:
    """校验权限矩阵结构自洽。返回 {valid: bool, issues: [str], malformed_actions: [str]}。

    校验四条 (缺哪条报哪条, 全过 → valid=True):
      ① 值类型: 每个角色值须是 (str, ...) 可迭代动作串 (非 dict/标量)。
      ② 动作命名规范: 每个动作须符 <资源>.<动作> (check_action_format)。
      ③ 角色命名: 非空 + 非含 "." (角色名与动作串区分, 防歧义)。
      ④ 无重复动作: 单角色内动作不重复 (重复声明结构异味, 不判业务)。
    畸形输入 (matrix 非 dict) → 计入 issues, 不崩。malformed_actions 汇总所有命名
    不合规的动作串 (供消费侧告警, 不静默)。
    """
    issues: list[str] = []
    malformed: list[str] = []
    if not isinstance(matrix, dict):
        return {"valid": False, "issues": ["matrix 非 dict (畸形)"],
                "malformed_actions": malformed}
    for role_name, perms in matrix.items():
        if not isinstance(role_name, str) or not role_name or "." in role_name:
            issues.append(f"角色 {role_name!r} 命名不合规 (须非空且不含 '.')")
        if not isinstance(perms, (list, tuple)):
            issues.append(f"角色 {role_name!r} 权限非动作串序列 (须 list/tuple[str])")
            continue
        seen: set = set()
        for a in perms:
            if not isinstance(a, str):
                issues.append(f"角色 {role_name!r} 含非字符串动作 {a!r}")
                continue
            if not check_action_format(a):
                issues.append(f"角色 {role_name!r} 动作 {a!r} 命名不合规 (<资源>.<动作>)")
                malformed.append(a)
            if a in seen:
                issues.append(f"角色 {role_name!r} 动作 {a!r} 重复声明")
            seen.add(a)
    return {"valid": not issues, "issues": issues, "malformed_actions": malformed}


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


# ─── 死锁环检测 (机制层自主子集, 纯函数) ────────────────────────
# 边界 (诚实, 呼应 CLAUDE.md「不虚标」): 当前 acquire_lock 只做**单资源写互斥** —
# 请求被拒即返回 False, 不记录「谁在等谁」。多资源协同下真正的死锁来自「持有 A
# 者等 B、持有 B 者等 A」的**等待环**。这里提供独立纯函数检测等待图中的环:
# 输入 wait_edges (持有者→其正在等待的持有者), 输出成环的持有者清单。
# 不改变 acquire_lock 既有语义 (向后兼容), 是给上层「记录等待意图」后的环检测工具。


def detect_deadlock(wait_edges: dict[str, str]) -> list[str]:
    """检测等待图中的死锁环。wait_edges: {持有者: 其正在等待的持有者}。

    返回成环持有者的有序清单 (如 ["alice", "bob"]), 无环 → []。
    语义: 持有 alice 的人等 bob、持有 bob 的人等 alice → 环 [alice, bob]。
    纯图遍历 (着色法找环), 不碰 I/O, 可单测。未知指向 (等待的对象不在图里) 优雅忽略。
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}
    stack: list[str] = []
    cycle: list[str] | None = None

    def dfs(node: str) -> None:
        nonlocal cycle
        color[node] = GRAY
        stack.append(node)
        nxt = wait_edges.get(node)
        if nxt is not None and nxt in wait_edges:
            if color.get(nxt) == GRAY:
                # 回溯栈定位环: 从 nxt 到当前 node
                idx = stack.index(nxt)
                cycle = list(stack[idx:])
                return
            if color.get(nxt, WHITE) == WHITE and cycle is None:
                dfs(nxt)
        stack.pop()
        color[node] = BLACK

    for start in list(wait_edges):
        if color.get(start, WHITE) == WHITE:
            if dfs(start):
                break
    return cycle or []
