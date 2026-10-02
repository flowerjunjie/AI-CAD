"""
跨专业碰撞检测几何库 (M4)

纯函数、无 I/O、可单测 — 仿 detect_opening_collisions 范式
(layout.py:324): 输入 raw_data dict, 输出 [{a_id, b_id, kind, detail}]。
检测 管线/暖通 段 vs 结构梁 段, 以及 管线/电气/暖通 点位 vs 结构梁柱 的几何碰撞:
  ① 线段×线段: 管/风管 段 vs 梁 段        → pipe-beam / duct-beam
  ② 线段×点:   管/风管 段 vs 柱 中心点     → pipe-column / duct-column
  ③ 点位×线段: 插座/风口 点 vs 梁 段       → outlet-beam / grille-beam
  ④ 点位×点位: 插座/风口 点 vs 柱 中心点   → outlet-column / grille-column
柱画成小方块, 简化为「中心点 + 统一容差带」判定 (物理来源: 各元素截面半宽,
简化为 tolerance_m), 不建方块 polygon — 与「用半宽做容差带」的契约一致。

红线: 纯几何库, 不碰 ezdxf/langgraph; 只检测「不同专业」碰撞,
同类元素内部 (管 vs 管, 梁 vs 梁) 不算; 空键/缺失键优雅跳过。
"""
import math

_EPS = 1e-9


def seg_intersect(p1, p2, p3, p4, eps=1e-3) -> bool:
    """两条线段 p1-p2 / p3-p4 是否严格相交 (存在共同内部点)。

    语义: 两段**交叉或重叠**才算; 仅端点接触 (T 形顶到/共线端点相接) 不算 —
    「管端顶到梁面」是管线端部接至结构, 非穿梁, 不计入碰撞 (与
    detect_opening_collisions 的 overlap_m>0 严格重叠范式对齐)。

    cross product 法 (标准 2D 线段相交): 一般交叉 = 端点分居对方两侧;
    共线退化 (两线均平行) 用「端点落在另一线段内部」判断 (open 端点, 共享端点不算)。
    eps 容差吃浮点噪声, 防止共线误判。
    """
    a, b, c, d = p1, p2, p3, p4
    d1, d2 = _cross(c, d, a), _cross(c, d, b)
    d3, d4 = _cross(a, b, c), _cross(a, b, d)
    # 共线退化 (两线均平行): 端点落入对方内部 (非端点相接) 才算重叠。
    # 共线时四个叉积均为 0, 两个方向 (a-b 端点入 c-d / c-d 端点入 a-b) 须都查。
    if abs(d1) <= eps and abs(d2) <= eps and abs(d3) <= eps and abs(d4) <= eps:
        return (_inside_seg(c, d, a) or _inside_seg(c, d, b)
                or _inside_seg(a, b, c) or _inside_seg(a, b, d))
    # 一般相交: 两线不平行, 端点分居对方两侧 (叉积严格异号)
    return _strictly_opposite(d1, d2, eps) and _strictly_opposite(d3, d4, eps)


def _strictly_opposite(x: float, y: float, eps: float) -> bool:
    """两叉积严格异号 (号差 > eps 容差)。"""
    return (x > eps and y < -eps) or (x < -eps and y > eps)


def _inside_seg(a, b, p) -> bool:
    """点 p 是否严格在线段 a-b 内部 (不含端点, 假定 p 共线于该线)。

    沿「非退化坐标轴」判严格内部: 斜线段 x/y 单调性同向、轴对齐段退化轴恒等
    (lo==hi), 故任一非退化轴上严格内部即等价于「在线段内部」, 退化轴恒等不贡献
    判定 (lo+eps < lo < hi-eps 为 False, 天然不干扰)。
    """
    lo_x, hi_x = sorted((a[0], b[0]))
    lo_y, hi_y = sorted((a[1], b[1]))
    inside_x = lo_x + _EPS < p[0] < hi_x - _EPS
    inside_y = lo_y + _EPS < p[1] < hi_y - _EPS
    # 退化轴 (lo==hi) 上「严格内部」恒 False; 该轴恒等, 由另一非退化轴判定
    deg_x = hi_x - lo_x <= _EPS
    deg_y = hi_y - lo_y <= _EPS
    if deg_x and deg_y:
        return False  # a==b 退化点, 无内部
    if deg_x:
        return inside_y
    if deg_y:
        return inside_x
    return inside_x and inside_y


def _cross(op, ap, bp) -> float:
    """(op→ap) × (op→bp) 的 z 分量。"""
    return (ap[0] - op[0]) * (bp[1] - op[1]) - (ap[1] - op[1]) * (bp[0] - op[0])


def point_to_seg_dist(px, py, a, b) -> float:
    """点 (px,py) 到线段 a-b 的最近距离 (投影参数 t 沿 a→b, clamp [0,1])。

    a==b 退化线段: 返回到 a 点的欧氏距离。
    """
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    seg_sq = dx * dx + dy * dy
    if seg_sq <= _EPS:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _seg_geom(raw_item: dict):
    """从 raw 线段元素取 (start, end) 坐标对; 缺键返回 None (跳过)。"""
    s, e = raw_item.get("start"), raw_item.get("end")
    if s is None or e is None:
        return None
    return (float(s[0]), float(s[1])), (float(e[0]), float(e[1]))


def _pt_geom(raw_item: dict):
    """从 raw 点位元素取 (x, y); 缺键返回 None (跳过)。"""
    x, y = raw_item.get("x"), raw_item.get("y")
    if x is None or y is None:
        return None
    return float(x), float(y)


def _raw_id(items: list, idx: int) -> str:
    """raw 列表下标对应的 id (无 id 时退回下标), 用于结果 a_id/b_id。"""
    return items[idx].get("id", str(idx)) if 0 <= idx < len(items) else str(idx)


def _segs_of(raw: dict, key: str) -> list:
    """raw[key] 线段列表 → [(id, start, end), ...], 缺键跳过。"""
    out = []
    for item in raw.get(key, []):
        geom = _seg_geom(item)
        if geom is not None:
            out.append((item.get("id", ""), geom[0], geom[1]))
    return out


def _pts_of(raw: dict, key: str) -> list:
    """raw[key] 点位列表 → [(id, x, y), ...], 缺键跳过。"""
    out = []
    for item in raw.get(key, []):
        geom = _pt_geom(item)
        if geom is not None:
            out.append((item.get("id", ""), geom[0], geom[1]))
    return out


def resolve_clash_tolerance(default_m: float = 0.15,
                            dsl_rule: "object | None" = None,
                            params: "dict | None" = None) -> tuple[float, str]:
    """碰撞容差取值通道 (M4 ← default.json 回填, 同 M1 数值回填范式)。

    优先级 (高→低):
      ① params['clash_tolerance_m']   — 会话级参数覆盖 (引擎/前端透传)
      ② dsl_rule.clash_tolerance_m    — DSL 规则 params 里的显式覆盖
      ③ default_m                     — 几何默认 (0.15m, 与既有调用一致)
    返回 (容差米数, 来源标注 'param'|'dsl'|'default') — 来源供 GUI 透出, 不虚标。

    设计边界 (诚实): 不自动读 default.json 文件 — 由调用方把 dsl_rule/params 喂进来
    (主链路从 state, 桥端点从 query), 本函数只做「取值 + 标注来源」的纯判定。
    """
    if isinstance(params, dict):
        v = params.get("clash_tolerance_m")
        if isinstance(v, (int, float)) and v > 0:
            return float(v), "param"
    if dsl_rule is not None:
        v = getattr(dsl_rule, "clash_tolerance_m", None)
        if v is None and hasattr(dsl_rule, "params"):
            v = (getattr(dsl_rule, "params") or {}).get("clash_tolerance_m")
        if isinstance(v, (int, float)) and v > 0:
            return float(v), "dsl"
    return float(default_m), "default"


def detect_clashes(raw: dict, tolerance_m: float = 0.15) -> list[dict]:
    """跨专业碰撞检测。raw 是 raw_data dict (键缺失优雅跳过)。

    返回 [{a_id, b_id, kind, detail}], kind 清单见模块 docstring。
    规则:
      ① 管/风管 段 vs 梁 段: seg_intersect 命中
      ② 管/风管 段 vs 柱 点: 点到线段距离 ≤ tolerance_m (容差带)
      ③ 插座/风口 点 vs 梁 段: 点到线段距离 < tolerance_m
      ④ 插座/风口 点 vs 柱 点: 点间距离 < tolerance_m
    只检测不同专业; 同类元素内部不算; 无碰撞返回 []。
    """
    out: list[dict] = []
    beams = _segs_of(raw, "structural_beams")
    columns = _pts_of(raw, "structural_columns")

    # ① 线段×线段 + ② 线段×点: 管/风管 vs 梁/柱
    for segs, seg_key in ((_segs_of(raw, "pipes"), "pipe"),
                          (_segs_of(raw, "hvac_ducts"), "duct")):
        out.extend(_seg_vs_structure(segs, seg_key, beams, columns, tolerance_m))
    # ③ 点位×线段 + ④ 点位×点: 插座/风口 vs 梁/柱
    for pts, pt_key in ((_pts_of(raw, "outlets"), "outlet"),
                        (_pts_of(raw, "hvac_grilles"), "grille")):
        out.extend(_pt_vs_structure(pts, pt_key, beams, columns, tolerance_m))
    return out


def _seg_vs_structure(segs: list, seg_key: str, beams: list, columns: list,
                       tol: float) -> list[dict]:
    """规则①②: 一组线段 (管/风管) vs 梁段 (相交) + 柱点 (容差带)。"""
    hits: list[dict] = []
    for sid, s1, s2 in segs:
        for bid, b1, b2 in beams:
            if seg_intersect(s1, s2, b1, b2):
                hits.append({"a_id": sid, "b_id": bid, "kind": f"{seg_key}-beam",
                             "detail": "管段与梁段相交"})
        for cid, cx, cy in columns:
            if point_to_seg_dist(cx, cy, s1, s2) <= tol:
                hits.append({"a_id": sid, "b_id": cid, "kind": f"{seg_key}-column",
                             "detail": "管段距柱中心 ≤ 容差带"})
    return hits


def _pt_vs_structure(pts: list, pt_key: str, beams: list, columns: list,
                     tol: float) -> list[dict]:
    """规则③④: 一组点位 (插座/风口) vs 梁段 (容差带) + 柱点 (容差带)。"""
    hits: list[dict] = []
    for pid, px, py in pts:
        for bid, b1, b2 in beams:
            if point_to_seg_dist(px, py, b1, b2) < tol:
                hits.append({"a_id": pid, "b_id": bid, "kind": f"{pt_key}-beam",
                             "detail": "点位距梁 < 容差带"})
        for cid, cx, cy in columns:
            if math.hypot(px - cx, py - cy) < tol:
                hits.append({"a_id": pid, "b_id": cid, "kind": f"{pt_key}-column",
                             "detail": "点位距柱 < 容差带"})
    return hits
