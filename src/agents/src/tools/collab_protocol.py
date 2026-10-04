"""
M5 在线协同 · 持久层协议骨架 (锁/审批的持久化 + 事件溯源 + 跨进程传递)

纯函数、无外部依赖、可单测 — 仿 permission_model.py / clash_detection.py 范式。
把 permission_model 的**内存态锁/审批**升级为**可持久化、可跨进程共享**的协同地基:
  ① 锁持久化: list[ResourceLock] 落盘/取回 (JSON), 进程重启锁不丢
  ② 事件溯源: append-only 事件日志 (谁锁了/放行了/合并了), 协同的底层
  ③ 快照快照: 把「锁 + 事件」打包成一个可序列化协同快照, 可跨进程/跨设计师传递

边界 (诚实, 呼应 CLAUDE.md「不虚标」):
  - 这是**协议骨架**: 定「锁/事件如何持久化、如何传递」的机制, **不**定
    具体协同协议 (CRDT / OT / 单写者多读者等由业务定)。
  - 默认存储 = JSON 文件 (与项目 data/ 范式一致), 但**存储可注入**: 测试传
    内存 dict 即跑, 不碰盘; 接真实 DB/Redis 只需换后端, 协议不变。
  - 无网络/无多进程真实并发: 单进程内的「持久化 + 事件」机制, 真·多机在线
    协同 (socket/消息总线) 是后续一层, 不在本骨架内。

红线: 纯函数 + 可注入存储; 不碰 ezdxf/langgraph; 序列化用标准库 json, 无新依赖。
"""
import json
from dataclasses import asdict
from typing import Protocol

from src.agents.src.tools.permission_model import (
    ResourceLock, ChangeRequest,
    acquire_lock, release_lock,
)


# ─── 存储后端 (可注入: 测试传内存, 生产传 JSON 文件 / DB) ─────────

class CollabStore(Protocol):
    """协同状态存储后端 (最小契约: 存取一个 dict)。"""
    def load(self) -> dict: ...
    def save(self, state: dict) -> None: ...


class InMemoryCollabStore:
    """内存存储 (测试用, 不碰盘)。"""

    def __init__(self):
        self._state: dict = {}

    def load(self) -> dict:
        return self._state

    def save(self, state: dict) -> None:
        self._state = state


class JsonFileCollabStore:
    """JSON 文件存储 (默认, 与项目 data/ 范式一致)。

    缺文件 → 空 state (优雅, 不崩)。只读写「锁 + 事件」, 不动其他数据文件。
    """

    def __init__(self, path: str):
        self._path = path

    def load(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return {}
        except (json.JSONDecodeError, OSError):
            # 文件损坏/不可读 → 诚实返回空 state (上层据此重建), 不崩
            return {}

    def save(self, state: dict) -> None:
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)


# ─── 事件模型 (append-only, 协同溯源) ───────────────────────────

# 事件类型 (最小集; 业务可扩展, 机制不变):
#   lock / unlock / approve / reject / merge
# 每个事件带 (type, actor, resource_id, seq, payload), seq 单调递增 (溯源序)。


def _next_seq(state: dict) -> int:
    """append-only 日志的单调序号 (= 已有事件数)。"""
    return len(state.get("events", []))


def append_event(state: dict, event_type: str, actor: str,
                 resource_id: str, payload: dict | None = None) -> dict:
    """追加一条事件 (append-only, 不改入参, 返回新 state)。

    seq = 已有事件数 (追加前的长度), 单调递增, 供溯源排序。"""
    events = list(state.get("events", []))
    events.append({
        "seq": len(events),
        "type": event_type,
        "actor": actor,
        "resource_id": resource_id,
        "payload": payload or {},
    })
    new_state = dict(state)
    new_state["events"] = events
    return new_state


# ─── 持久化锁操作 (把 permission_model 的纯锁操作挂上存储) ───────

def _locks_of(state: dict) -> list[ResourceLock]:
    """从持久化 state 还原锁列表 (存的是 asdict 形式)。"""
    return [ResourceLock(**d) for d in state.get("locks", [])]


def _persist_locks(state: dict, locks: list[ResourceLock]) -> dict:
    new_state = dict(state)
    new_state["locks"] = [asdict(l) for l in locks]
    return new_state


def persistent_acquire(store: CollabStore, resource_id: str, requester: str,
                       mode: str = "write", now: float = 0.0) -> tuple[bool, dict, str]:
    """持久化取锁: load state → acquire_lock → 追加 lock 事件 → save。

    返回 (能否锁, 更新后持久化 state, 原因)。全程走注入 store, 可单测 (内存)。
    """
    state = store.load()
    locks = _locks_of(state)
    ok, new_locks, reason = acquire_lock(locks, resource_id, requester, mode, now)
    state = _persist_locks(state, new_locks)
    if ok:
        state = append_event(state, "lock", requester, resource_id, {"mode": mode})
    store.save(state)
    return ok, state, reason


def persistent_release(store: CollabStore, resource_id: str, owner: str,
                       ) -> dict:
    """持久化释放: load → release_lock → 追加 unlock 事件 → save。"""
    state = store.load()
    locks = release_lock(_locks_of(state), resource_id, owner)
    state = _persist_locks(state, locks)
    state = append_event(state, "unlock", owner, resource_id)
    store.save(state)
    return state


# ─── 协同快照 (跨进程 / 跨设计师传递) ───────────────────────────

def make_snapshot(store: CollabStore, designer: str) -> dict:
    """打包当前协同状态成一个可 json 序列化的快照 (锁 + 事件 + 持有者)。

    设计师端拿快照能看到: 谁持有哪些写锁 / 协同历史 / 自己是谁。
    """
    state = store.load()
    locks = _locks_of(state)
    return {
        "designer": designer,
        "write_holders": {
            l.resource_id: l.holder for l in locks if l.mode == "write"
        },
        "recent_events": state.get("events", [])[-10:],
        "event_count": len(state.get("events", [])),
    }


def snapshot_conflicts(snap_a: dict, snap_b: dict) -> list[str]:
    """两个设计师快照的写锁冲突: 对同一资源都持有写锁 (撞车)。

    复用「按资源比对」的极简逻辑, 输出资源 id 清单。无冲突 → []。
    (与 conflict_detection 的两稿比对是不同层: 这里比锁, 那里比稿内容。)
    """
    holders_a = set(snap_a.get("write_holders", {}))
    holders_b = set(snap_b.get("write_holders", {}))
    # 冲突 = 两个快照声称持有同一资源的写锁 (且持有者不同)
    out = []
    for res in holders_a & holders_b:
        a_holder = snap_a["write_holders"].get(res)
        b_holder = snap_b["write_holders"].get(res)
        if a_holder != b_holder:
            out.append(res)
    return out


# ─── 事件日志完整性校验 (协同正确性地基, 机制层自主子集) ─────────
# 边界 (诚实, 呼应 CLAUDE.md「不虚标」): 这是 append-only 事件溯源的**消费契约
# 校验** — 纯函数, 输入 state 输出「校验结论 + 问题清单」, 不修数据 (数据修复是
# 上层决定)。缺了它, snapshot_conflicts / make_snapshot 的仲裁建立在未验证的日志
# 上。机制通 (可写可测), 判定阈值本身是机制默认 (无业务值)。


def verify_event_log(state: dict) -> dict:
    """校验协同 state 的事件日志 + 锁态是否自洽。返回结构化结论 (纯函数, 不崩)。

    校验三条 (缺哪条报哪条, 全过 → valid=True, issues=[]):
      ① seq 连续: events[i].seq 必须 == i (append-only 追加序, 无跳号/无重复/无空洞)。
      ② 事件字段完整: 每条事件须有 type/actor/resource_id/seq 四键。
      ③ 锁态与事件可回放对齐: 按事件序回放 lock/unlock 还原「谁持哪些写锁」,
         应与 state["locks"] 声称的写锁持有者集合一致 (回放结果 = 持久锁态)。

    返回 {valid: bool, issues: [str...], replayed_write_holders: {res: holder}}。
    畸形输入 (events 非 list / 缺键) → 计入 issues, 不崩 (优雅降级)。
    """
    issues: list[str] = []
    events = state.get("events", [])
    if not isinstance(events, list):
        issues.append("events 非 list (畸形 state)")
        events = []

    # ② 字段完整性 (逐条)
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            issues.append(f"events[{i}] 非 dict")
            continue
        for field in ("type", "actor", "resource_id", "seq"):
            if field not in ev:
                issues.append(f"events[{i}] 缺字段 {field}")

    # ① seq 连续 (0..n-1 严格单调无空洞)
    for i, ev in enumerate(events):
        if isinstance(ev, dict) and ev.get("seq") != i:
            issues.append(f"events[{i}].seq={ev.get('seq')} 应=={i} (跳号/重复/空洞)")
            break  # 首个 seq 断裂即足以判不连续, 不逐条堆噪音

    # ③ 锁态可回放对齐: 按事件序重放, 还原当前写锁持有者
    replayed = _replay_write_holders(events)
    claimed = {l.get("resource_id"): l.get("holder")
               for l in state.get("locks", [])
               if isinstance(l, dict) and l.get("mode") == "write"}
    # 只比「资源→写持有者」投影 (忽略 acquired_at/非写锁): 回放 vs 持久锁态
    if replayed != claimed:
        issues.append(
            f"锁态与事件不可回放对齐: 回放写持有者={replayed} vs 持久={claimed}")

    return {
        "valid": not issues,
        "issues": issues,
        "replayed_write_holders": replayed,
    }


def _replay_write_holders(events: list) -> dict:
    """按事件序回放 lock/unlock, 还原「资源 → 写持有者」投影 (纯函数)。

    语义: lock(mode=write) 设该资源写持有者=actor; unlock 摘除 actor 的写锁
    (若仍是其持有); 其余事件 (read/approve/reject/merge) 不影响写持有者投影。
    同资源后事件覆盖前事件 (append-only 序即因果序)。
    """
    holders: dict[str, str] = {}
    for ev in events:
        if not isinstance(ev, dict):
            continue
        etype, actor, res = ev.get("type"), ev.get("actor"), ev.get("resource_id")
        if etype == "lock" and (ev.get("payload") or {}).get("mode", "write") == "write":
            if res is not None:
                holders[res] = actor
        elif etype == "unlock" and res is not None:
            # 只有 actor 仍是该资源写持有者时, unlock 才摘除
            if holders.get(res) == actor:
                holders.pop(res, None)
    return holders
