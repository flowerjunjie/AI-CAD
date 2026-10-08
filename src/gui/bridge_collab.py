"""
AI-CAD GUI FastAPI 桥 — H 在线协同域段 (M5 持久层协议: 快照 + 本地锁演示)。

从 bridge.py 拆出的自包含子模块 (bridge.py 1575 行超 500 红线, 结构性拆分)。
用 APIRouter 承载本域段全部 /api/collab/* + /api/permission/* 端点,
bridge.py 顶层 include_router 挂载 (app 注册方式不变, 端点路径 0 改动)。

拆分自包含性 (已核实): 本段只依赖模块级 ROOT/BaseModel/HTTPException/json/os,
不引用 B/C/F 段任何函数 (_load_sample_raw 仅在注释里说「不复用它」), 独立成文件安全。
段间无调用依赖 → 物理搬家不破坏既有端点。
"""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 与 bridge.py 同源的项目根定位 (子模块也在 <root>/src/gui/ 下, 上溯两级)。
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

router = APIRouter()

# ─── H 在线协同域段 (M5 持久层协议: 快照 + 本地锁演示) ──────────
# 让 collab_protocol 机制骨架有可见入口: 读 data/collab/state.json (真持久, 缺文件
# 诚实返回空态, 不造假)。
# 诚实边界 (不虚标):
#   - 快照只读: /api/collab/snapshot 透出「当前协同快照」(写锁持有者 + 最近事件)。
#   - 锁端点 (/api/collab/acquire|release) 是**本地单进程演示通路**: 锁态落本地
#     state.json, 无跨设计师同步/无多机仲裁 — 真·在线协同 (CRDT/OT/单写者多读者
#     协议 + 用户体系) 需业务定协议后再接, 端点 docstring 与响应 note 均显式标注。
# 懒 import: collab_protocol 依赖 permission_model (纯函数, 无重依赖), 但照范式放函数体。

# 协同 state 路径的单一事实源留在 bridge.py (测试 monkeypatch bridge._COLLAB_STATE_PATH
# 的契约稳定, 拆文件不破坏它)。本模块端点运行时惰性读 bridge 的当前值 (函数内 import
# 规避循环), 测试改 bridge 侧的名字即对本模块端点生效 — 拆与不拆测试都绿。
# 默认值 (bridge 未 patch 时) 与 bridge 模块初始 _COLLAB_STATE_PATH 一致。
_DEFAULT_COLLAB_STATE_PATH = os.path.join(ROOT, "data", "collab", "state.json")


def _collab_state_path() -> str:
    """运行时读 bridge 模块当前的 _COLLAB_STATE_PATH (测试 patch 目标)。

    惰性 import 规避循环 (bridge 顶层 import 本模块挂 router)。bridge 若未定义该
    名 (理论上不会, 契约锚点) 回退默认值。"""
    import src.gui.bridge as _bridge
    return getattr(_bridge, "_COLLAB_STATE_PATH", _DEFAULT_COLLAB_STATE_PATH)


@router.get("/api/collab/snapshot")
def api_collab_snapshot(designer: str = "designer") -> dict:
    """M5 在线协同持久层: 读协同状态快照 (谁持哪些写锁 + 最近协同事件)。

    返回 {designer, write_holders, recent_events, event_count, source}。
    状态文件不存在 → 空快照 (write_holders={}, 事件 0), 诚实标注 source="empty",
    不造假协同数据。"""
    from src.agents.src.tools.collab_protocol import (  # 懒
        JsonFileCollabStore, make_snapshot)

    store = JsonFileCollabStore(_collab_state_path())
    snap = make_snapshot(store, designer=designer)
    # 诚实标注来源: 真有落盘 state 才 "file", 空态标 "empty"
    has_state = store.load()
    snap["source"] = "file" if has_state else "empty"
    snap["note"] = ("持久协同快照" if has_state
                    else "无落盘协同状态 (写操作待业务定协同协议后接入)")
    return snap


@router.get("/api/permission/matrix")
def api_permission_matrix() -> dict:
    """M5 权限矩阵 (机制层): 透出默认角色→权限矩阵 + 结构自洽校验结论。

    业务专家回填 DEFAULT_PERMISSIONS 时, 本端点把「矩阵结构是否自洽」(角色/动作
    命名规范 <资源>.<动作>、值类型、无重复/畸形条目) 提前透出, 而非线上静默全拒绝。
    返回 {roles, valid, issues, malformed_actions, note}。

    诚实边界 (不虚标): 校验的是**矩阵结构** (命名/类型/重复), **不**判定「谁到底能
    干什么」的业务值 — 具体角色/权限条目仍需业务定夺 (占位配置), 本端点只报结构异味。"""
    from src.agents.src.tools.permission_model import (  # 懒
        DEFAULT_PERMISSIONS, validate_permissions_matrix)
    res = validate_permissions_matrix(DEFAULT_PERMISSIONS)
    res["roles"] = {k: list(v) for k, v in DEFAULT_PERMISSIONS.items()}
    res["note"] = ("权限矩阵结构自洽 (命名/类型/无重复); 具体角色/权限值仍为占位, "
                   "需业务定夺" if res["valid"]
                   else "权限矩阵存在结构异味, 见 issues/malformed_actions (业务回填前修复)")
    return res


def _collab_store() -> object:
    """懒建默认协同 store (data/collab/state.json, 缺目录自动建)。"""
    from src.agents.src.tools.collab_protocol import JsonFileCollabStore
    _sp = _collab_state_path()
    os.makedirs(os.path.dirname(_sp), exist_ok=True)
    return JsonFileCollabStore(_sp)


@router.get("/api/collab/verify")
def api_collab_verify() -> dict:
    """M5 协同正确性地基: 校验当前协同 state 的事件日志 + 锁态是否自洽。

    跑 collab_protocol.verify_event_log (纯函数, 机制层自主子集):
    ① 事件 seq 连续 (无跳号/重复/空洞)
    ② 事件字段完整 (type/actor/resource_id/seq)
    ③ 锁态与事件可回放对齐 (回放写持有者 == 持久写锁投影)

    返回 {valid, issues, replayed_write_holders, source}。缺文件 → 空 state,
    verify 仍诚实跑 (空事件/空锁 → valid=True, 零协同态), 标注 source="empty"。
    诚实边界: 这是**日志完整性校验机制**, 非「多机协同是否一致」— 真·在线协同
    (跨机 CRDT/OT) 待业务定协议, 本端点只验「本地持久层自身是否自洽」。"""
    from src.agents.src.tools.collab_protocol import (  # 懒
        JsonFileCollabStore, verify_event_log)

    store = JsonFileCollabStore(_collab_state_path())
    state = store.load()
    res = verify_event_log(state)
    res["source"] = "file" if state else "empty"
    res["note"] = ("本地协同持久层完整性校验 (机制层); 真·多机协同待业务定协议"
                   if res["valid"]
                   else "本地协同持久层自检未通过, 见 issues (修复策略由上层定)")
    return res


@router.get("/api/collab/waits-verify")
def api_collab_waits_verify() -> dict:
    """M5 协同 waits 字段完整性体检 (机制层自主子集, verify_event_log 的孪生)。

    背景: verify_event_log 已验「事件日志 seq 连续 + 锁态可回放对齐」, 但
    state["waits"] (等待边) 本身与 locks 的一致性无人校验 — 而
    check_deadlock_from_state 直接消费 waits 判环, 若 waits 有「指向不持锁
    holder 的幽灵等待边」, 死锁判定会建立在脏数据上误判。本端点补这层对账:
    ① 每条 wait 字段完整 (requester + holder 非 None)
    ② wait 指向的 holder 须 ∈ 当前写锁持有者集合 (否则幽灵等待边)
    ③ 幂等无重复 (record_wait 应保证同边不重, 重复即脏)

    纯机制层: 只判「waits 数据自身是否自洽」, **不判**「谁该持哪把锁」的业务值
    (M5 权限矩阵, 仍占位待业务回填)。返回 {valid, issues, ghost_holders, source}。"""
    from src.agents.src.tools.collab_protocol import verify_waits_consistency  # 懒

    store = _collab_store()
    state = store.load()
    res = verify_waits_consistency(state)
    res["source"] = "file" if state else "empty"
    res["note"] = ("本地协同 waits 字段完整性体检 (机制层, 不判业务锁归属); "
                   "幽灵等待边/缺字段/重复边 在此失步可见"
                   if res["valid"]
                   else "本地协同 waits 自检未通过, 见 issues (修复策略由上层定)")
    return res


class CollabLockReq(BaseModel):
    designer: str
    resource_id: str
    mode: str = "write"  # write / read (read 不互斥, 总是成功)


@router.post("/api/collab/acquire")
def api_collab_acquire(req: CollabLockReq) -> dict:
    """本地取锁演示通路: persistent_acquire (load→acquire_lock→追加 lock 事件→save)。

    返回 {acquired, resource_id, designer, mode, reason, write_holders}。
    被他人写锁占用 → acquired=false + reason (诚实, 不崩)。
    诚实标注: 本地单进程, 无跨设计师同步 — 真·在线协同待业务定协议后再接。"""
    from src.agents.src.tools.collab_protocol import persistent_acquire, make_snapshot
    import time
    store = _collab_store()
    ok, state, reason = persistent_acquire(
        store, req.resource_id, req.designer, req.mode, now=time.time())
    snap = make_snapshot(store, designer=req.designer)
    snap.update({
        "acquired": ok,
        "resource_id": req.resource_id,
        "designer": req.designer,
        "mode": req.mode,
        "reason": reason,
        "note": "本地锁演示 (单进程, 无跨设计师同步; 真·在线协同待业务定协议)",
    })
    return snap


class CollabReleaseReq(BaseModel):
    designer: str
    resource_id: str


@router.post("/api/collab/release")
def api_collab_release(req: CollabReleaseReq) -> dict:
    """本地放锁演示通路: persistent_release (load→release_lock→追加 unlock 事件→save)。

    返回 {released, resource_id, designer, write_holders}。释放后该写锁消失
    (幂等: 无对应锁也返回 200, released=false 诚实标注)。"""
    from src.agents.src.tools.collab_protocol import persistent_release, make_snapshot
    store = _collab_store()
    before = store.load()
    held = any(l.get("resource_id") == req.resource_id and l.get("holder") == req.designer
               and l.get("mode") == "write" for l in before.get("locks", []))
    persistent_release(store, req.resource_id, req.designer)
    snap = make_snapshot(store, designer=req.designer)
    snap.update({
        "released": held,  # 确有该写锁被放掉才 true; 无锁释放 (幂等) → false
        "resource_id": req.resource_id,
        "designer": req.designer,
        "note": "本地锁演示 (单进程, 无跨设计师同步; 真·在线协同待业务定协议)",
    })
    return snap


class CollabDeadlockReq(BaseModel):
    wait_edges: dict  # {持有者: 其正在等待的持有者}


@router.post("/api/collab/deadlock-check")
def api_collab_deadlock_check(req: CollabDeadlockReq) -> dict:
    """M5 死锁环检测 (机制层): 提交等待图 {持有者: 其等待的持有者}, 检出等待环。

    跑 permission_model.detect_deadlock (纯函数, 机制层自主子集):
    返回 {wait_edges, deadlocked: bool, cycle}。无环 → deadlocked=false, cycle=[]。

    诚实边界: 这是「给定等待图能否检出环」的纯判定, **不**记录/裁决真实协同的
    等待意图 (那是上层在取锁被拒时记录 wait-edge 的事); 真·多机协同待业务定协议。
    输入校验: wait_edges 须是 dict[str, str], 非 dict → 400 (系统边界, 不静默)。"""
    from src.agents.src.tools.permission_model import detect_deadlock  # 懒
    if not isinstance(req.wait_edges, dict):
        raise HTTPException(400, "wait_edges 须为对象 {持有者: 等待对象}")
    for holder, target in req.wait_edges.items():
        if not isinstance(holder, str) or not isinstance(target, str):
            raise HTTPException(400, "wait_edges 键值须为字符串 (持有者/等待对象)")
    cycle = detect_deadlock(req.wait_edges)
    return {
        "wait_edges": req.wait_edges,
        "deadlocked": bool(cycle),
        "cycle": cycle,
        "note": "死锁环检测 (机制层纯判定); 等待图由上层取锁被拒时构建",
    }


@router.get("/api/collab/deadlock")
def api_collab_deadlock() -> dict:
    """M5 死锁检测 (真实锁流程版): 读本地协同 state 的 wait-edges 判环。

    与 /api/collab/deadlock-check (提交任意等待图) 不同, 本端点跑的是
    persistent_acquire/release **真实采集**的等待意图 — 取锁被拒记 wait-edge、
    成功/放锁清 wait-edge, 落 state.json 的 waits 字段。端到端闭环:
    设计师交叉取锁 → 记真实等待 → 本端点检出环。

    返回 {source, deadlocked, cycle, wait_edges}。缺 state → 空态, deadlocked=false,
    诚实标 source="empty"。"""
    from src.agents.src.tools.collab_protocol import (  # 懒
        JsonFileCollabStore, check_deadlock_from_state)
    store = JsonFileCollabStore(_collab_state_path())
    state = store.load()
    res = check_deadlock_from_state(state)
    res["source"] = "file" if state else "empty"
    res["note"] = ("本地锁流程真实 wait-edges 死锁检测 (机制层); 真·多机协同待业务定协议"
                   if res["deadlocked"]
                   else "本地锁流程无等待环 (waits 空或无回边)")
    return res


@router.get("/api/collab/elements")
def api_collab_elements(sample: str = "residential_100sqm.json") -> dict:
    """M5 协同 + duplicate 联动: 列出 sample 的「可锁资源」元素清单 + 重复标记。

    把协同面板硬编码的资源下拉 (sheet-a/sheet-b) 换成**真实 CAD 元素 id**,
    并在取锁前标出哪些是「同坐标不同 id 的疑似重复」— 设计师锁元素前先看
    「这个元素疑似跟另一个 id 画在同一位置, 要不要先核对再锁」。

    返回 {sample, resources: [{id, category, duplicate_of, coord}],
          duplicate_count, note}。
      - resources: 该 sample 全部带 id 元素 ( doors/outlets/pipes/... 各 id)
      - duplicate_of: 若该 id 与另一 id 同坐标, 记重复对端 id (无重复 null)
      - duplicate_count: 同坐标不同 id 的组数 (几何等价类维度, M5)

    诚实边界 (不虚标): 只报「几何重复」线索, **不**判业务上是否允许同坐标 —
    取锁前的提示是「建议先核对」, 不是「禁止锁」。资源清单来自真实 sample 元素,
    缺元素键优雅跳过。懒 import: conflict_detection 纯函数库。"""
    from src.agents.src.tools.conflict_detection import (  # 懒
        detect_duplicate_elements)

    # 协同元素清单要全量元素 id (不只 6 个 clash 键), 直接读 sample 顶层,
    # 不复用 _load_sample_raw (它按 _CLASH_SAMPLE_KEYS 截断, 会漏 doors/walls 等)。
    p = os.path.join(ROOT, "data", "sample", sample)
    if not os.path.exists(p):
        raise HTTPException(404, f"样本不存在: {sample}")
    with open(p, encoding="utf-8") as fh:
        full = json.load(fh)
    raw = {k: v for k, v in full.items() if isinstance(v, list)}
    # 全量元素 id 清单 (带坐标类: 插座/管线/梁柱, 供协同面板选资源)
    resources: list[dict] = []
    for key, items in raw.items():
        for el in (items or []):
            if not isinstance(el, dict):
                continue  # 元素须是 dict (带 id); 纯标量/字符串跳过, 不崩
            eid = el.get("id")
            if eid is None:
                continue
            resources.append({"id": eid, "category": key,
                              "duplicate_of": None, "coord": None})
    # duplicate 维度: 同坐标不同 id → 标重复对端 (取锁前提示「疑似重复」)
    dupes = detect_duplicate_elements(raw, raw)  # 同稿自比, 只抓几何重复
    by_id: dict[str, dict] = {r["id"]: r for r in resources}
    duplicate_count = 0
    for d in dupes:
        duplicate_count += 1
        for eid, other in ((d["id_a"], d["id_b"]), (d["id_b"], d["id_a"])):
            if eid in by_id:
                by_id[eid]["duplicate_of"] = other
                if d.get("coord"):
                    by_id[eid]["coord"] = d["coord"]
    return {
        "sample": sample,
        "resources": resources,
        "duplicate_count": duplicate_count,
        "note": ("资源清单 = 真实 CAD 元素 id · 重复标记 = 同坐标不同 id "
                 "(几何等价类, 取锁前建议先核对; 不判业务归属)"),
    }
