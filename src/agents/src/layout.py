"""
几何布局引擎 — zones/doors/windows → 2D 坐标（无 LLM 依赖）

MVP 级贪心排布：房间按面积降序网格排列，门窗放在精确的共享边/外侧墙上。
坐标单位：米，origin 在 (0,0)。
"""
from typing import Optional

_EPS = 1e-6


def _room_area(z: dict) -> float:
    return float(z.get("length", 0)) * float(z.get("width", 0))


def layout_rooms(zones: list[dict]) -> list[dict]:
    """
    按网格排列房间。
    贪心：按面积降序，逐行填充；行高 = 该行房间最大 width。
    返回每个房间的 absolute coords:
    [{id, name, type, x, y, w, h, area}]
    """
    if not zones:
        return []

    ordered = sorted(zones, key=_room_area, reverse=True)
    n = len(ordered)
    cols = 2 if n > 1 else 1
    rows = (n + cols - 1) // cols

    out: list[dict] = []
    row_heights: list[float] = []
    for r in range(rows):
        chunk = ordered[r * cols:(r + 1) * cols]
        row_heights.append(max(_room_w(z) for z in chunk) if chunk else 0.0)

    total_h = sum(row_heights)
    row_y_start: list[float] = []
    y_cursor = total_h
    for rh in row_heights:
        y_cursor -= rh
        row_y_start.append(y_cursor)

    for i, z in enumerate(ordered):
        r = i // cols
        c = i % cols
        w = float(z.get("length", 0))
        h = float(z.get("width", 0))
        x_cursor = 0.0
        for j in range(c):
            prev = ordered[r * cols + j]
            x_cursor += float(prev.get("length", 0))
        out.append({
            "id": z.get("id", f"z{i}"),
            "name": z.get("name", ""),
            "type": z.get("type", ""),
            "x": x_cursor,
            "y": row_y_start[r],
            "w": w,
            "h": h,
            "area": w * h,
        })

    return out


def _room_w(z: dict) -> float:
    return float(z.get("width", 0))


def _shared_edge(ra: dict, rb: dict) -> Optional[dict]:
    """
    判定两房间是否共边，返回共边几何信息（仅处理网格布局下贴边相邻）。
    返回 {orientation: 'v'|'h', x/y: 共边固定坐标, lo: 重叠区间起, hi: 重叠区间止}
    不共边返回 None。
    竖直共边：ra 右缘贴 rb 左缘（或反），y 区间有重叠。
    水平共边：ra 上缘贴 rb 下缘（或反），x 区间有重叠。
    """
    a_lo_x, a_hi_x = ra["x"], ra["x"] + ra["w"]
    a_lo_y, a_hi_y = ra["y"], ra["y"] + ra["h"]
    b_lo_x, b_hi_x = rb["x"], rb["x"] + rb["w"]
    b_lo_y, b_hi_y = rb["y"], rb["y"] + rb["h"]

    # 竖直共边（左右相邻）
    y_lo = max(a_lo_y, b_lo_y)
    y_hi = min(a_hi_y, b_hi_y)
    if abs(a_hi_x - b_lo_x) < _EPS and y_hi - y_lo > _EPS:
        return {"orientation": "v", "x": a_hi_x, "lo": y_lo, "hi": y_hi}
    if abs(b_hi_x - a_lo_x) < _EPS and y_hi - y_lo > _EPS:
        return {"orientation": "v", "x": b_hi_x, "lo": y_lo, "hi": y_hi}

    # 水平共边（上下相邻）
    x_lo = max(a_lo_x, b_lo_x)
    x_hi = min(a_hi_x, b_hi_x)
    if abs(a_hi_y - b_lo_y) < _EPS and x_hi - x_lo > _EPS:
        return {"orientation": "h", "y": a_hi_y, "lo": x_lo, "hi": x_hi}
    if abs(b_hi_y - a_lo_y) < _EPS and x_hi - x_lo > _EPS:
        return {"orientation": "h", "y": b_hi_y, "lo": x_lo, "hi": x_hi}

    return None


def _find_shared_edge(name_a: str, name_b: str, by_name: dict) -> Optional[dict]:
    """两房间间的共享边。a==b 或匹配不到 → None。"""
    if name_a not in by_name or name_b not in by_name:
        return None
    if name_a == name_b:
        return None
    return _shared_edge(by_name[name_a], by_name[name_b])


def place_doors_on_walls(doors: list[dict], rooms: list[dict]) -> list[dict]:
    """
    门精确放在两房间共享边的几何中点（不再拍脑袋的中心连线中点）。
    - location "A→B" / "A到B"：A、B 共边 → 开在共边中点；不共边 → 退回 A 外侧边中点
    - location "外墙南侧" 等：开在建筑外围外墙中点
    - location 匹配到单个房间：开在该房间外侧边中点
    返回 [{id, position:(x,y), width, rotation, room_type, location, width_m}]
    width_m 透传样本门宽，供标注层画「洞口标注」(门宽数字) 复用，不重读样本。
    """
    by_name = {r["name"]: r for r in rooms if r.get("name")}
    placed: list[dict] = []

    for d in doors:
        loc = d.get("location", "")
        width = float(d.get("width_m", 0.9))
        room_type = d.get("type", "interior")
        did = d.get("id", "")

        pos: Optional[tuple[float, float]] = None
        rotation = 90.0  # 默认竖直墙开门

        # 解析 "A→B" 双向 location
        a_name = b_name = None
        for sep in ("→", "->", "到"):
            if sep in loc:
                a_name, b_name = [s.strip() for s in loc.split(sep, 1)]
                break

        if a_name and b_name:
            edge = _find_shared_edge(a_name, b_name, by_name)
            if edge is not None:
                if edge["orientation"] == "v":
                    pos = (edge["x"], (edge["lo"] + edge["hi"]) / 2)
                    rotation = 0.0  # 竖直墙 → 门扇水平开
                else:
                    pos = ((edge["lo"] + edge["hi"]) / 2, edge["y"])
                    rotation = 90.0  # 水平墙 → 门扇竖直开

        if pos is None:
            # fallback 1：单向 location 匹配到某个房间，放该房间外侧边中点
            target = _match_room(loc, by_name)
            if target is not None:
                outer = _outer_side_of_room(target, rooms)
                if outer["orientation"] == "v":
                    pos = (outer["x"], (outer["lo"] + outer["hi"]) / 2)
                    rotation = 0.0
                else:
                    pos = ((outer["lo"] + outer["hi"]) / 2, outer["y"])
                    rotation = 90.0
            # fallback 2：完全匹配不到 → 建筑外围外墙中点
            if pos is None:
                pos, rotation = _building_outer_midpoint(rooms)

        placed.append({
            "id": did,
            "position": pos,
            "width": width,
            "width_m": width,
            "rotation": rotation,
            "room_type": room_type,
            "location": loc,
        })

    return placed


def _building_outer_midpoint(rooms: list[dict]) -> tuple[tuple[float, float], float]:
    """建筑包围盒外围外墙中点（默认南侧，y 最小那侧）。"""
    if not rooms:
        return (0.0, 0.0), 90.0
    x_lo = min(r["x"] for r in rooms)
    x_hi = max(r["x"] + r["w"] for r in rooms)
    y_lo = min(r["y"] for r in rooms)
    return ((x_lo + x_hi) / 2, y_lo), 90.0


def _outer_side_of_room(room: dict, rooms: list[dict]) -> dict:
    """
    房间朝向建筑外围的外侧边。
    在房间四条边里，找与建筑包围盒边界重合的那条（即朝外的墙）。
    若房间被完全包围（不贴任何外围边界），退回取最长边。
    返回 {orientation:'v'|'h', x/y, lo, hi}
    """
    if not rooms:
        return {"orientation": "v", "x": room["x"], "lo": room["y"], "hi": room["y"] + room["h"]}

    x_lo = min(r["x"] for r in rooms)
    x_hi = max(r["x"] + r["w"] for r in rooms)
    y_lo = min(r["y"] for r in rooms)
    y_hi = max(r["y"] + r["h"] for r in rooms)

    rx, ry, rw, rh = room["x"], room["y"], room["w"], room["h"]
    candidates: list[dict] = []

    # 左缘贴建筑西外墙
    if abs(rx - x_lo) < _EPS:
        candidates.append({"orientation": "v", "x": rx, "lo": ry, "hi": ry + rh})
    # 右缘贴建筑东外墙
    if abs(rx + rw - x_hi) < _EPS:
        candidates.append({"orientation": "v", "x": rx + rw, "lo": ry, "hi": ry + rh})
    # 下缘贴建筑南外墙
    if abs(ry - y_lo) < _EPS:
        candidates.append({"orientation": "h", "y": ry, "lo": rx, "hi": rx + rw})
    # 上缘贴建筑北外墙
    if abs(ry + rh - y_hi) < _EPS:
        candidates.append({"orientation": "h", "y": ry + rh, "lo": rx, "hi": rx + rw})

    if not candidates:
        # 被完全包围：取最长边
        if rw >= rh:
            candidates.append({"orientation": "h", "y": ry, "lo": rx, "hi": rx + rw})
        else:
            candidates.append({"orientation": "v", "x": rx, "lo": ry, "hi": ry + rh})

    # 优先级：边长越长越优先（采光好），平手时按方位 南>北>西>东
    def _priority(c: dict) -> tuple:
        length = c["hi"] - c["lo"]
        if c["orientation"] == "v":
            compass = 0 if c["x"] == x_lo else 3  # 西=0, 东=3
        else:
            compass = 1 if c["y"] == y_lo else 2  # 南=1, 北=2
        return (-length, compass)

    return sorted(candidates, key=_priority)[0]


def _match_room(location: str, by_name: dict) -> Optional[dict]:
    """从 location 字符串里匹配到一个已知房间名（双向 "A→B" 取第一个 A）。"""
    for sep in ("→", "->", "到"):
        if sep in location:
            first = location.split(sep, 1)[0].strip()
            if first in by_name:
                return by_name[first]
    for name in by_name:
        if name in location:
            return by_name[name]
    return None


def place_windows_on_walls(windows: list[dict], rooms: list[dict]) -> list[dict]:
    """
    窗放在房间**外侧墙**（朝建筑外围的那条边）的几何中点。
    跨度取该边长度的 60%（原行为），居中于外侧边中点。
    返回 [{id, start:(x,y), end:(x,y), sill_height, room}]
    """
    by_name = {r["name"]: r for r in rooms if r.get("name")}
    placed: list[dict] = []

    for w in windows:
        room_name = w.get("room", "")
        sill = float(w.get("sill_height_m", 0.9))
        wid = w.get("id", "")

        target = by_name.get(room_name) or _match_room(room_name, by_name)

        if target:
            side = _outer_side_of_room(target, rooms)
            if side["orientation"] == "v":
                # 竖直外侧边（东/西外墙）：窗为竖直段
                y_mid = (side["lo"] + side["hi"]) / 2
                span = (side["hi"] - side["lo"]) * 0.3  # 各半 = 总 60%
                placed.append({
                    "id": wid,
                    "start": (side["x"], y_mid - span),
                    "end": (side["x"], y_mid + span),
                    "sill_height": sill,
                    "room": room_name,
                })
            else:
                # 水平外侧边（南/北外墙）：窗为水平段
                x_mid = (side["lo"] + side["hi"]) / 2
                span = (side["hi"] - side["lo"]) * 0.3
                placed.append({
                    "id": wid,
                    "start": (x_mid - span, side["y"]),
                    "end": (x_mid + span, side["y"]),
                    "sill_height": sill,
                    "room": room_name,
                })
        else:
            placed.append({
                "id": wid,
                "start": (0.0, 0.0),
                "end": (1.0, 0.0),
                "sill_height": sill,
                "room": room_name,
            })

    return placed


def _door_interval(d: dict) -> tuple:
    """门在墙上的占据区间（门宽沿墙中线展开），返回 (wall_key, lo, hi)。
    wall_key 标识门所在的墙（竖直墙 → ('v', x)，水平墙 → ('h', y)）。"""
    px, py = d["position"]
    if d["rotation"] == 0.0:
        # 竖直墙（门扇水平开）：门在 x=px，沿 y 展开
        return ("v", round(px, 6)), py - d["width"] / 2, py + d["width"] / 2
    # 水平墙（门扇竖直开）：门在 y=py，沿 x 展开
    return ("h", round(py, 6)), px - d["width"] / 2, px + d["width"] / 2


def _window_interval(w: dict) -> tuple:
    """窗在墙上的占据区间，返回 (wall_key, lo, hi)。"""
    (x0, y0), (x1, y1) = w["start"], w["end"]
    if abs(x0 - x1) < _EPS:
        lo, hi = sorted((y0, y1))
        return ("v", round(x0, 6)), lo, hi
    lo, hi = sorted((x0, x1))
    return ("h", round(y0, 6)), lo, hi


def detect_opening_collisions(doors: list[dict], windows: list[dict]) -> list[dict]:
    """
    检测同一面墙上 门-门 / 门-窗 / 窗-窗 的重叠（碰撞）。
    返回 [{a_id, b_id, kind, overlap_m}]，kind ∈ {'door-door','door-window','window-window'}。
    纯函数，无 I/O，可单测。
    """
    def _overlap(lo1, hi1, lo2, hi2) -> float:
        return max(0.0, min(hi1, hi2) - max(lo1, lo2))

    # 收集所有"墙占据段"：(wall_key, kind, id, lo, hi)
    segs: list[tuple] = []
    for d in doors:
        key, lo, hi = _door_interval(d)
        segs.append((key, "door", d.get("id", ""), lo, hi))
    for w in windows:
        key, lo, hi = _window_interval(w)
        segs.append((key, "window", w.get("id", ""), lo, hi))

    collisions: list[dict] = []
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            ka, ta, ida, alo, ahi = segs[i]
            kb, tb, idb, blo, bhi = segs[j]
            if ka != kb:
                continue  # 不同墙
            ov = _overlap(alo, ahi, blo, bhi)
            if ov > _EPS:
                kind = "door-door" if (ta == "door" and tb == "door") else (
                    "door-window" if (ta != tb) else "window-window")
                collisions.append({
                    "a_id": ida, "b_id": idb, "kind": kind, "overlap_m": ov,
                })
    return collisions


# ─── 门窗碰撞结果自洽校验 (机制层自主子集, 纯函数) ─────────────
# 边界 (诚实, 呼应 CLAUDE.md「不虚标」): 这是「detect_opening_collisions 输出
# 自身是否自洽」的校验 — 供出图侧 (cad_rule_export L783 遍历结果画门窗重叠圈) 在
# 消费前对账, 防脏 a_id/b_id (元素已被上游删掉/写错) 静默穿透进 DWG 兜底原点假圈。
# 与 M4 的 verify_clashes 同构 (都是「几何碰撞检测 → 出图反查」失步面), 判据适配
# 门窗 3 类 kind + 门窗元素 id 集合。纯函数, 不修数据, 畸形输入优雅降级不崩。
# 不判「该不该有碰撞」(业务), 只判「这份碰撞清单自身是否自洽」。

# 合法门窗碰撞 kind (3 类, 与 detect_opening_collisions 产出的键集合同源)。
# 抽成可导出常量, 消除「出图侧 _CLASH_KIND_CN (L309 键集合)」与本库隐式白名单
# 两处漂移 (verify 据此校验, 消费侧可 import 同源)。
OPENING_KINDS: frozenset = frozenset({
    "door-door", "door-window", "window-window",
})


def _opening_ids(doors: list, windows: list) -> set:
    """门窗元素全量 id 集合 (a_id/b_id 反查依据), 缺 id 字段跳过不崩。"""
    ids: set = set()
    for items in (doors or [], windows or []):
        for it in items:
            if isinstance(it, dict) and it.get("id") is not None:
                ids.add(it.get("id"))
    return ids


def verify_opening_collisions(
    doors: list[dict],
    windows: list[dict],
    collisions: list[dict],
) -> dict:
    """校验门窗碰撞结果 (detect_opening_collisions 产物) 自身是否自洽。纯函数, 不崩。

    校验四条 (缺哪条报哪条, 全过 → valid=True, issues=[]):
      ① 无自碰撞: 每条 a_id != b_id (门窗碰撞必是两个不同元素)。
      ② kind 合法: kind ∈ OPENING_KINDS (3 类, 与本库产出同源, 消隐式白名单漂移)。
      ③ a_id/b_id 在门窗: 两端 id 真存在于 doors/windows (出图反查才不会兜底原点假圈)。
      ④ overlap_m 为正: 有碰撞必有正重叠 (overlap_m 须 > 0, 防零/负重叠误报)。
    畸形输入 (collisions 非 list / 条非 dict / 缺 a_id/b_id) → 计入 issues, 不崩。
    """
    collisions = collisions or []
    issues: list[str] = []
    known_ids = _opening_ids(doors, windows)

    for i, c in enumerate(collisions):
        if not isinstance(c, dict):
            issues.append(f"collisions[{i}] 非 dict")
            continue
        a, b, kind, ov = c.get("a_id"), c.get("b_id"), c.get("kind"), c.get("overlap_m")
        if a is None or b is None:
            issues.append(f"collisions[{i}] 缺 a_id/b_id (a={a!r}, b={b!r})")
            continue
        if a == b:
            issues.append(f"collisions[{i}] 自碰撞 (a_id==b_id=={a!r})")
        if kind not in OPENING_KINDS:
            issues.append(
                f"collisions[{i}].kind={kind!r} 非合法 3 类 {sorted(OPENING_KINDS)}")
        for tag, eid in (("a_id", a), ("b_id", b)):
            if eid not in known_ids:
                issues.append(f"collisions[{i}].{tag}={eid!r} 不在门窗元素 (出图会兜底原点假圈)")
        if not isinstance(ov, (int, float)) or ov <= 0:
            issues.append(f"collisions[{i}].overlap_m={ov!r} 非正数 (碰撞须有正重叠)")

    return {"valid": not issues, "issues": issues, "count": len(collisions)}
