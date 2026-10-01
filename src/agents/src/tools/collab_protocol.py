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
