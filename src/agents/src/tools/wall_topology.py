"""
墙线拓扑解析 — 从 WALL 图层线段解析真实房间轮廓

算法：shapely.planar polygonize
  1. 端点吸附(snap)抗浮点误差
  2. 所有墙段 union 成几何集合
  3. shapely.ops.polygonize 自动切出闭合面（房间 + 外轮廓）
  4. 面积最大者 = 外轮廓(is_outer)，其余 = 房间；面积过小者 = 阳台/薄壁碎片过滤

脏数据不崩：异常返回 {rooms:[], diagnostics:{...}}，让上游 fallback。
"""
from collections import defaultdict

_TOL_DEFAULT = 1e-3
_SHAPLEY_CACHE = {}


def _shapely():
    """惰性加载 shapely（C 扩展冷启动 ~5s），进程内缓存，避免重复加载。"""
    if not _SHAPLEY_CACHE:
        import shapely.geometry
        import shapely.ops
        _SHAPLEY_CACHE["geometry"] = shapely.geometry
        _SHAPLEY_CACHE["ops"] = shapely.ops
    return _SHAPLEY_CACHE


def snap_point(p: tuple, tol: float = _TOL_DEFAULT) -> tuple:
    """端点吸附到 tol 网格，抗 CAD 浮点误差。"""
    return (round(p[0] / tol) * tol, round(p[1] / tol) * tol)


def snap_key(p: tuple, tol: float = _TOL_DEFAULT) -> tuple:
    return snap_point(p, tol)


def build_adjacency(segs: list, tol: float = _TOL_DEFAULT) -> dict:
    """保留：端点键 -> 邻接信息（诊断/门洞补边用）。"""
    adj: dict = defaultdict(list)
    for sid, (a, b) in enumerate(segs):
        ka = snap_key(a, tol)
        kb = snap_key(b, tol)
        adj[ka].append({"to": kb, "id": sid})
        adj[kb].append({"to": ka, "id": sid})
    return adj


def _signed_area(poly: list) -> float:
    s = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return s / 2.0


def _bbox(poly: list) -> tuple:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def partition_rooms(segs: list, tol: float = _TOL_DEFAULT, min_room_area: float = 0.5) -> dict:
    """
    墙线段 -> 房间列表（shapely polygonize）。
    返回 {"rooms": [ {polygon, area, bbox, is_outer} ], "diagnostics": {...}}
    - 端点吸附后 unary_union + polygonize 自动切出所有封闭面
    - 每个封闭面都是"房间/空间"(含 L 形主厅), 一律保留 (is_outer 恒 False)
    - 面积 < min_room_area 视为阳台/薄壁碎片丢弃
    - 脏数据不崩：异常返回空 rooms + diagnostics.error
    """
    diagnostics = {"closed_faces": 0, "dropped_small": 0, "error": None}
    try:
        _shp = _shapely()
        shapely_geometry = _shp["geometry"]
        shapely_ops = _shp["ops"]

        # 端点吸附 + 过滤退化段
        snapped = []
        for a, b in segs:
            sa = snap_point(a, tol)
            sb = snap_point(b, tol)
            if sa != sb:
                snapped.append((sa, sb))
        if not snapped:
            return {"rooms": [], "diagnostics": diagnostics}

        lines = [shapely_geometry.LineString([a, b]) for a, b in snapped]
        union = shapely_ops.unary_union(lines)
        faces = list(shapely_ops.polygonize(union))
        diagnostics["closed_faces"] = len(faces)

        polys = []
        for p in faces:
            if p.geom_type != "Polygon" or p.is_empty:
                continue
            coords = list(p.exterior.coords)
            area = p.area
            if area < min_room_area:
                diagnostics["dropped_small"] += 1
                continue
            polys.append({
                "polygon": [tuple(c[:2]) for c in coords],
                "area": area,
                "bbox": _bbox(coords),
                "is_outer": False,
            })

        # 说明: 每个 polygonize 出的最小封闭面都是"房间/空间", 一律保留。
        # 之前用 is_outer 剔除"最大面"是错的 — L 形户型里最大的面(主厅)
        # 被误当外轮廓剔掉。真实拓扑里"封闭空间 = 房间", 不单独存在外轮廓面
        # (unary_union 把外框边合并进最小面了)。is_outer 字段保留供兼容, 恒为 False。

        return {"rooms": polys, "diagnostics": diagnostics}
    except Exception as e:  # 脏数据/缺 shapely 都兜底，不打崩上游
        diagnostics["error"] = f"{type(e).__name__}: {e}"
        return {"rooms": [], "diagnostics": diagnostics}


def add_door_bridge_edges(segs: list, door_segs: list, tol: float = _TOL_DEFAULT) -> list:
    """门洞虚拟边：把断墙（门处缺口）补成闭合面。返回 segs + door_segs 合并。"""
    return list(segs) + list(door_segs)
