"""
几何布局引擎 — zones/doors/windows → 2D 坐标（无 LLM 依赖）

MVP 级贪心排布：房间按面积降序网格排列，门窗放在房间外缘。
坐标单位：米，origin 在 (0,0)。
"""
from typing import Optional


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

    # 按面积降序
    ordered = sorted(zones, key=_room_area, reverse=True)

    # 简单分列：把房间排成 2 列（房间数多时更紧凑）
    n = len(ordered)
    cols = 2 if n > 1 else 1
    rows = (n + cols - 1) // cols

    out: list[dict] = []
    # 先算每行高度
    row_heights: list[float] = []
    for r in range(rows):
        chunk = ordered[r * cols:(r + 1) * cols]
        row_heights.append(max(_room_area_in_w(z) for z in chunk) if chunk else 0.0)

    # 累计每行起始 y（y 向下递减，第 0 行在最上）
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
        # x：列内累计宽度
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


def _room_area_in_w(z: dict) -> float:
    """行高取该房间的 width（深度方向）。"""
    return float(z.get("width", 0))


def place_doors_on_walls(doors: list[dict], rooms: list[dict]) -> list[dict]:
    """
    门放在相邻房间共享墙的中点。
    简化：按 door["location"] 字符串（如 "客厅→主卧"）匹配到两个房间，
    放在两房间边界中点。找不到匹配就放该门位置默认（房间外缘中点）。
    返回 [{position:(x,y), width, rotation, room_type, location, id}]
    """
    by_name = {r["name"]: r for r in rooms if r.get("name")}
    placed: list[dict] = []

    for d in doors:
        loc = d.get("location", "")
        width = float(d.get("width_m", 0.9))
        room_type = d.get("type", "interior")
        did = d.get("id", "")

        # 尝试解析 "A→B" 或 "A到B"
        a_name = b_name = None
        for sep in ("→", "->", "到"):
            if sep in loc:
                a_name, b_name = [s.strip() for s in loc.split(sep, 1)]
                break

        pos: Optional[tuple[float, float]] = None
        rotation = 90.0
        if a_name in by_name and b_name in by_name:
            ra, rb = by_name[a_name], by_name[b_name]
            # 找共享边中点（简化：取两房间中心连线中点）
            ca = (ra["x"] + ra["w"] / 2, ra["y"] + ra["h"] / 2)
            cb = (rb["x"] + rb["w"] / 2, rb["y"] + rb["h"] / 2)
            pos = ((ca[0] + cb[0]) / 2, (ca[1] + cb[1]) / 2)
            # 水平相邻 → 门朝水平开（rot 0），垂直相邻 → 朝竖直开（rot 90）
            if abs(ca[1] - cb[1]) < abs(ca[0] - cb[0]):
                rotation = 0.0

        if pos is None:
            # fallback：放该门所属房间外缘中点（取第一个匹配房间）
            target = _match_room(loc, by_name)
            if target:
                pos = (target["x"] + target["w"] / 2, target["y"])
            else:
                pos = (0.0, 0.0)

        placed.append({
            "id": did,
            "position": pos,
            "width": width,
            "rotation": rotation,
            "room_type": room_type,
            "location": loc,
        })

    return placed


def _match_room(location: str, by_name: dict) -> Optional[dict]:
    """从 location 字符串里匹配到一个已知房间名。"""
    for name in by_name:
        if name in location:
            return by_name[name]
    return None


def place_windows_on_walls(windows: list[dict], rooms: list[dict]) -> list[dict]:
    """
    窗放在每个有窗房间的外侧墙（最外沿）中段。
    简化：取房间上沿（y 最大那侧）中点，开一段长度 = 房间 width * 0.6。
    返回 [{start:(x,y), end:(x,y), sill_height, room, id}]
    """
    by_room = {}
    for r in rooms:
        key = r.get("name") or r.get("type")
        by_room.setdefault(key, r)

    placed: list[dict] = []
    for w in windows:
        room_name = w.get("room", "")
        sill = float(w.get("sill_height_m", 0.9))
        wid = w.get("id", "")

        target = by_room.get(room_name)
        if target is None:
            target = _match_room(room_name, {r.get("name"): r for r in rooms if r.get("name")})

        if target:
            x0 = target["x"] + target["w"] * 0.2
            x1 = target["x"] + target["w"] * 0.8
            y = target["y"] + target["h"]  # 上沿（外侧）
            placed.append({
                "id": wid,
                "start": (x0, y),
                "end": (x1, y),
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
