"""
Agent 节点 — CAD执行 + 规则校验 + 成果输出
消费 raw_data 几何数据（zones/doors/windows），不再用硬编码坐标
"""
import os
import sys
from src.agents.src.tools.cad_tools import (
    DXFWriter, Wall, Door as CADDoor, Window as CADWindow, Point,
    Pipe as CADPipe, Beam as CADBeam, Column as CADColumn,
    Outlet as CADOutlet, Switch as CADSwitch,
    HvacDuct as CADHvacDuct, HvacUnit as CADHvacUnit, HvacGrille as CADHvacGrille,
)
from src.agents.src.tools.rag_tools import RAGKnowledgeBase
from src.agents.src.layout import layout_rooms, place_doors_on_walls, place_windows_on_walls, detect_opening_collisions
from src.agents.src.tools.clash_detection import detect_clashes, CLASH_KINDS
from src.agents.src.numbering import assign_door_numbers, assign_window_numbers
from src.agents.src.tools.wall_topology import partition_rooms
from src.rules.src.engine import get_engine


# ②段 (元素构造器/_ELEMENT_CHECKS 分发表/碰撞定位辅助) 已拆到 cad_clash_layout.py
# (破 882 行); re-export 兜住旧 import 路径 (全仓 bridge_* + 测试 0 改动, 兼容层, 2026-10-11)。
from src.agents.src.nodes.cad_clash_layout import (  # noqa: F401
    _dsl_rules_path, _ensure_dsl_rules_loaded,
    _build_door, _build_door_2, _build_window, _build_window_2, _build_room,
    _build_pipe, _build_outlet, _build_switch, _build_hvac_duct,
    _build_hvac_unit, _build_hvac_grille, _build_structural_beam,
    _build_structural_column, _ELEMENT_CHECKS, constructible_element_types,
    _collision_violation, _CLASH_KIND_CN, _clash_violation, _clash_point,
    _duplicate_point,
)




def _layout_from_state(state: dict) -> dict:
    """从 state 提取 zones/doors/windows，跑布局引擎，返回坐标。
    有 wall_segments（真实 DWG 墙线）→ 走 partition_rooms 真实拓扑；
    没有 → fallback layout_rooms 贪心网格（现状不变，回归安全）。"""
    raw = state.get("raw_data", {}) or {}
    zones = raw.get("zones", []) or state.get("project_structure", {}).get("zones", [])
    doors = raw.get("doors", [])
    windows = raw.get("windows", [])
    wall_segs = raw.get("wall_segments") or state.get("wall_segments") or []

    if wall_segs:
        topo = partition_rooms(wall_segs)
        # 真实拓扑的 polygon → 用 bbox 桥接成 rooms {x,y,w,h}，下游 place_*/_outer_walls 不改
        rooms = _polygons_to_rooms(topo["rooms"])
        if rooms:
            door_pos = place_doors_on_walls(doors, rooms)
            window_pos = place_windows_on_walls(windows, rooms)
            return {"rooms": rooms, "doors": door_pos, "windows": window_pos,
                    "zones": zones, "topology": "real"}
        # 真实拓扑解析失败/无有效房间 → 落回贪心网格（兜底）

    rooms = layout_rooms(zones)
    door_pos = place_doors_on_walls(doors, rooms)
    window_pos = place_windows_on_walls(windows, rooms)
    return {"rooms": rooms, "doors": door_pos, "windows": window_pos, "zones": zones,
            "topology": "grid"}


def _polygons_to_rooms(polys: list) -> list:
    """把真实拓扑的 polygon 用 bbox 桥接成 rooms {x,y,w,h}（下游接口不变）。
    每个封闭面都当房间保留（含 L 形主厅，is_outer 已废弃恒 False）。"""
    out = []
    for i, p in enumerate(polys):
        x0, y0, x1, y1 = p["bbox"]
        out.append({
            "id": f"r{i}",
            "name": p.get("name", ""),
            "type": p.get("type", ""),
            "x": x0,
            "y": y0,
            "w": x1 - x0,
            "h": y1 - y0,
            "area": p["area"],
            "polygon": p["polygon"],
        })
    return out


def _outer_walls(rooms: list[dict], thickness: float) -> list[Wall]:
    """外墙：取所有房间的最小 x/y 和最大 x/y 画外轮廓矩形。"""
    if not rooms:
        return []
    x0 = min(r["x"] for r in rooms)
    y0 = min(r["y"] for r in rooms)
    x1 = max(r["x"] + r["w"] for r in rooms)
    y1 = max(r["y"] + r["h"] for r in rooms)
    return [
        Wall(start=Point(x0, y0), end=Point(x1, y0), thickness=thickness),
        Wall(start=Point(x1, y0), end=Point(x1, y1), thickness=thickness),
        Wall(start=Point(x1, y1), end=Point(x0, y1), thickness=thickness),
        Wall(start=Point(x0, y1), end=Point(x0, y0), thickness=thickness),
    ]


def _inner_walls(rooms: list[dict], thickness: float) -> list[Wall]:
    """内墙：相邻房间共享边画线（MVP 简化：每对水平相邻画竖直墙）。"""
    walls: list[Wall] = []
    if not rooms:
        return walls
    for i, r in enumerate(rooms):
        for j in range(i + 1, len(rooms)):
            s = rooms[j]
            # 水平相邻：y 区间重叠且 x 边贴边
            if (r["y"] < s["y"] + s["h"] and s["y"] < r["y"] + r["h"]
                    and abs(r["x"] + r["w"] - s["x"]) < 1e-6):
                lo = max(r["y"], s["y"])
                hi = min(r["y"] + r["h"], s["y"] + s["h"])
                walls.append(Wall(start=Point(s["x"], lo), end=Point(s["x"], hi),
                                   thickness=thickness))
    return walls


def cad_execute_node(state: dict) -> dict:
    """
    CAD执行 Agent：按 raw_data 几何出图，驱动 task_list 子任务
    """
    writer = DXFWriter()
    writer.new("AC1027")

    layout = _layout_from_state(state)
    rooms, door_pos, window_pos = layout["rooms"], layout["doors"], layout["windows"]
    # 门窗出图带编号: 对布局出的门窗列表按出现序编 M/C 号, 贯穿到图面 TEXT。
    # 与 door_by_id 共用同一编号空间 (id 与 number 对齐), 避免二次编号错位。
    door_pos = assign_door_numbers(door_pos)
    window_pos = assign_window_numbers(window_pos)

    tasks = state.get("task_list", [])
    results = []
    confirmations = {}
    _door_markers_done = False  # 门编号只画一次 (样本 task_list 含 7 个 door task, 逐个画会重复 49 条)

    for task in tasks:
        task_id = task.get("id", "unknown")
        task_type = task.get("type", "")
        params = task.get("params", {})

        try:
            if task_type == "wall":
                thickness = params.get("thickness", 0.24)
                if task_id == "wall-outer":
                    for w in _outer_walls(rooms, thickness):
                        writer.add_wall(w)
                        writer.add_wall_thickness(w)
                    count = len(_outer_walls(rooms, thickness))
                else:
                    inner = _inner_walls(rooms, thickness)
                    for w in inner:
                        writer.add_wall(w)
                        writer.add_wall_thickness(w)
                    count = len(inner)
                results.append({"task_id": task_id, "status": "completed", "count": count})

            elif task_type == "door":
                # 按门真实 id 匹配布局出的门（编号空间统一，不再用位置索引）
                door_by_id = {d["id"]: d for d in door_pos if d.get("id")}
                d = door_by_id.get(task_id)
                if d:
                    writer.add_door(CADDoor(
                        position=Point(d["position"][0], d["position"][1]),
                        width=d["width"],
                        rotation=d["rotation"],
                    ))
                results.append({"task_id": task_id, "status": "pending_confirm",
                                "description": task.get("description", "")})
                confirmations[task_id] = False
                # 编号文字: 遍历布局出的全部门画 M 号 (与窗分支同范式, 保证编号
                # 不随 task_id 是否匹配而丢)。task_id 与布局门 id 对齐时才命中
                # 单门几何; 编号按 door_pos 顺序补全。仅首个 door task 画, 避免
                # 样本 7 个 door task 重复画 49 条。
                if not _door_markers_done:
                    for dd in door_pos:
                        writer.add_opening_marker(
                            dd.get("number", dd.get("id", "")),
                            (dd["position"][0], dd["position"][1] - 0.3),
                        )
                    _door_markers_done = True

            elif task_type == "window":
                for wp in window_pos:
                    writer.add_window(CADWindow(
                        start=Point(wp["start"][0], wp["start"][1]),
                        end=Point(wp["end"][0], wp["end"][1]),
                        sill_height=wp["sill_height"],
                    ))
                    # 编号文字: 窗段中点旁画 C 号
                    cx = (wp["start"][0] + wp["end"][0]) / 2
                    cy = (wp["start"][1] + wp["end"][1]) / 2 + 0.3
                    writer.add_opening_marker(wp.get("number", task_id), (cx, cy))
                results.append({"task_id": task_id, "status": "completed",
                                "count": len(window_pos)})

            elif task_type == "pipe":
                # 给排水管段: 直接消费 raw_data 的 plumbing 线段 (不经布局引擎),
                # 每段调 add_pipe 画 PIPE 图层 LWPOLYLINE + PIPE_LABEL 层管径标注。
                # 与 wall/door/window 的区别: 管段坐标来自样本 pipes 键, 不走布局。
                raw_pipes = (state.get("raw_data", {}) or {}).get("pipes", [])
                for p in raw_pipes:
                    sx, sy = p.get("start", (0.0, 0.0))
                    ex, ey = p.get("end", (0.0, 0.0))
                    writer.add_pipe(CADPipe(
                        start=Point(float(sx), float(sy)),
                        end=Point(float(ex), float(ey)),
                        diameter_mm=int(p.get("diameter_mm", 50)),
                        layer=p.get("layer", "PIPE"),
                    ))
                results.append({"task_id": task_id, "status": "completed",
                                "count": len(raw_pipes)})

            elif task_type == "beam":
                # 结构梁段: 消费 raw_data 的 structural 梁 (对齐 _ELEMENT_CHECKS
                # structural_beams 键), 每段 add_beam 画 BEAM 层 LWPOLYLINE
                # + BEAM_LABEL 层 "宽x高" 截面标注。坐标来自样本, 不走布局。
                raw_beams = (state.get("raw_data", {}) or {}).get("structural_beams", [])
                for b in raw_beams:
                    sx, sy = b.get("start", (0.0, 0.0))
                    ex, ey = b.get("end", (0.0, 0.0))
                    writer.add_beam(CADBeam(
                        start=Point(float(sx), float(sy)),
                        end=Point(float(ex), float(ey)),
                        width_mm=int(b.get("width_mm", 300)),
                        depth_mm=int(b.get("depth_mm", 0)),
                        layer=b.get("layer", "BEAM"),
                        span_m=float(b.get("span_m", 0.0)),
                    ))
                results.append({"task_id": task_id, "status": "completed",
                                "count": len(raw_beams)})

            elif task_type == "column":
                # 结构柱: 消费 raw_data 的 structural 柱 (对齐 structural_columns 键),
                # 每柱 add_column 画 COLUMN 层截面矩形 + COLUMN_LABEL 层 "短边x短边"。
                raw_columns = (state.get("raw_data", {}) or {}).get("structural_columns", [])
                for c in raw_columns:
                    writer.add_column(CADColumn(
                        position=Point(float(c.get("x", 0.0)), float(c.get("y", 0.0))),
                        section_mm=int(c.get("section_mm", 400)),
                        layer=c.get("layer", "COLUMN"),
                    ))
                results.append({"task_id": task_id, "status": "completed",
                                "count": len(raw_columns)})

            elif task_type == "outlet":
                # 电气插座点位: 消费 raw_data 的 outlets 键 (对齐 _ELEMENT_CHECKS),
                # 每点 add_outlet 画 ELEC_OUTLET 正方形 + ELEC_LABEL 层 "H{高度}" 标注。
                # 坐标/高度来自样本, 不走布局（与 pipe/beam 同款点位范式）。
                raw_outlets = (state.get("raw_data", {}) or {}).get("outlets", [])
                for o in raw_outlets:
                    writer.add_outlet(CADOutlet(
                        position=Point(float(o.get("x", 0.0)), float(o.get("y", 0.0))),
                        height_m=float(o.get("height_m", 0.3)),
                        layer=o.get("layer", "ELEC_OUTLET"),
                    ))
                results.append({"task_id": task_id, "status": "completed",
                                "count": len(raw_outlets)})

            elif task_type == "switch":
                # 电气开关点位: 消费 raw_data 的 switches 键, 每点 add_switch 画
                # ELEC_SWITCH 正方形 + ELEC_LABEL 层 "H{高度}" 标注（照 outlet 范式）。
                raw_switches = (state.get("raw_data", {}) or {}).get("switches", [])
                for s in raw_switches:
                    writer.add_switch(CADSwitch(
                        position=Point(float(s.get("x", 0.0)), float(s.get("y", 0.0))),
                        height_m=float(s.get("height_m", 1.3)),
                        layer=s.get("layer", "ELEC_SWITCH"),
                    ))
                results.append({"task_id": task_id, "status": "completed",
                                "count": len(raw_switches)})

            elif task_type == "hvac":
                # 暖通三元素: 风管=线段 (照 add_pipe 范式), 机组/风口=点位
                # (照 add_column 范式)。消费 raw_data 的 hvac_ducts / hvac_units /
                # hvac_grilles 键 (对齐 _ELEMENT_CHECKS)。
                raw_data = state.get("raw_data", {}) or {}
                raw_ducts = raw_data.get("hvac_ducts", [])
                raw_units = raw_data.get("hvac_units", [])
                raw_grilles = raw_data.get("hvac_grilles", [])
                for d in raw_ducts:
                    sx, sy = d.get("start", (0.0, 0.0))
                    ex, ey = d.get("end", (0.0, 0.0))
                    writer.add_hvac_duct(CADHvacDuct(
                        start=Point(float(sx), float(sy)),
                        end=Point(float(ex), float(ey)),
                        diameter_mm=int(d.get("diameter_mm", 100)),
                        layer=d.get("layer", "HVAC_DUCT"),
                    ))
                for u in raw_units:
                    writer.add_hvac_unit(CADHvacUnit(
                        position=Point(float(u.get("x", 0.0)), float(u.get("y", 0.0))),
                        cooling_kw=float(u.get("cooling_kw", 0.0)),
                        layer=u.get("layer", "HVAC_UNIT"),
                    ))
                for g in raw_grilles:
                    writer.add_hvac_grille(CADHvacGrille(
                        position=Point(float(g.get("x", 0.0)), float(g.get("y", 0.0))),
                        height_m=float(g.get("height_m", 2.5)),
                        layer=g.get("layer", "HVAC_GRILLE"),
                    ))
                results.append({"task_id": task_id, "status": "completed",
                                "count": len(raw_ducts) + len(raw_units) + len(raw_grilles)})

            elif task_type == "clash":
                # M4 跨专业碰撞出图侧: 对 raw_data 跑 detect_clashes, 每个碰撞画
                # 红色警示圈 (CLASH/CLASH_LABEL 层)。碰撞点坐标取 kind 对应的
                # 线段中点或点位坐标 (见 _clash_point)。无碰撞 → 0 实体, 既有出图不变。
                # 容差同 rule_check_node 取值通道: state 级覆盖 > 几何默认 0.15。
                from src.agents.src.tools.clash_detection import (
                    detect_clashes, resolve_clash_tolerance)
                raw_data = state.get("raw_data", {}) or {}
                _clash_tol, _clash_tol_src = resolve_clash_tolerance(
                    default_m=0.15, params=state.get("clash_params"))
                clash_count = 0
                for c in detect_clashes(raw_data, tolerance_m=_clash_tol):
                    cx, cy = _clash_point(raw_data, c)
                    writer.add_clash_marker(cx, cy, c["kind"], label=c["kind"].upper())
                    clash_count += 1
                results.append({"task_id": task_id, "status": "completed",
                                "clashes": clash_count,
                                "tolerance_m": _clash_tol, "tolerance_source": _clash_tol_src})

            elif task_type == "conflict":
                # M5 两稿改动冲突检测 (可自主子集): 对 raw_data (稿A) 与
                # conflict_raw_b (稿B) 按元素 id 比对, 记冲突计数 + 几何等价类
                # (同坐标不同 id = 疑似重复) 画琥珀色 DUP 警示圈 (出图侧增量)。
                # 无第二稿 (state 未带 conflict_raw_b) → 0 冲突 0 出图 (no-op)。
                raw_data = state.get("raw_data", {}) or {}
                raw_b = state.get("conflict_raw_b")
                if raw_b is None:
                    conflict_count, dup_count = 0, 0
                else:
                    from src.agents.src.tools.conflict_detection import (
                        detect_conflicts, detect_duplicate_elements)
                    conflicts = detect_conflicts(raw_data, raw_b)
                    conflict_count = len(conflicts)
                    # 几何等价类维度出图: 同坐标不同 id 画 DUP 圈 (M5 增量, 无重复 0 实体)
                    dup_count = 0
                    for d in detect_duplicate_elements(raw_data, raw_b):
                        cx, cy = _duplicate_point(d)
                        writer.add_duplicate_marker(cx, cy, label="DUP")
                        dup_count += 1
                results.append({"task_id": task_id, "status": "completed",
                                "conflicts": conflict_count,
                                "duplicates_marked": dup_count})

            elif task_type == "dimension":
                axis_count = 0
                if rooms:
                    x0 = min(r["x"] for r in rooms)
                    y0 = min(r["y"] for r in rooms)
                    x1 = max(r["x"] + r["w"] for r in rooms)
                    y1 = max(r["y"] + r["h"] for r in rooms)
                    writer.add_dimension(
                        Point(x0, y0), Point(x1, y0), offset=0.5,
                        text=str(int((x1 - x0) * 1000)))
                    writer.add_dimension(
                        Point(x0, y0), Point(x0, y1), offset=-0.5,
                        text=str(int((y1 - y0) * 1000)))
                    # 轴线深化: 轴网点划线 (CENTERLINE) + 轴号 ①②③/A/B,
                    # 延伸出外轮廓 0.5m (示意性轴网, 不依赖外部轴网数据)
                    x_mid = (x0 + x1) / 2.0
                    pad = 0.5  # 轴线延伸出外轮廓的距离
                    x_axes = [
                        ("①", x0, y0 - pad, y1 + pad),
                        ("②", x_mid, y0 - pad, y1 + pad),
                        ("③", x1, y0 - pad, y1 + pad),
                    ]
                    y_axes = [
                        ("A", y0, x0 - pad, x1 + pad),
                        ("B", y1, x0 - pad, x1 + pad),
                    ]
                    axis_count = writer.add_axis_grid(x_axes, y_axes)
                # 洞口标注: 每门/窗 1 条宽度数字 (DIMENSION 层, 在洞口下方)
                opening_count = writer.add_opening_dimensions(door_pos, window_pos, offset=0.5)
                results.append({"task_id": task_id, "status": "completed",
                                "openings": opening_count,
                                "axes": axis_count})

        except Exception as e:
            results.append({"task_id": task_id, "status": "error", "error": str(e)})

    # 保存DWG
    output_path = state.get("output_path", "/tmp/ai_cad_result.dwg")
    saved = writer.save(output_path)

    return {
        "cad_results": results,
        "human_confirmations": confirmations,
        "cad_queue": [],
        "final_dwg_path": output_path if saved else None,
    }


def rule_check_node(state: dict) -> dict:
    """
    规则校验 Agent：按 raw_data 实际元素校验（不再硬编码）

    主体走 _ELEMENT_CHECKS 分发表（加专业=加表项，不改主链路逻辑）；
    几何碰撞检测依赖 _layout_from_state/layout，非简单 raw→element 映射，
    故留在循环外单独跑。
    """
    engine = get_engine()
    raw = state.get("raw_data", {}) or {}
    zones = raw.get("zones", []) or state.get("project_structure", {}).get("zones", [])
    raw_doors = raw.get("doors", [])
    raw_windows = raw.get("windows", [])

    # DSL 规则（plumbing-/electrical-）不在全局引擎，加载后 upsert 一次（幂等）
    _ensure_dsl_rules_loaded(engine)

    # raw_key → raw 数据（zones 走 raw→project_structure 兜底；其余直接 raw.get）
    def _raw_items(raw_key: str) -> list:
        if raw_key == "zones":
            return zones
        return raw.get(raw_key, [])

    violations = []
    for entry in _ELEMENT_CHECKS:
        raw_items = _raw_items(entry["raw_key"])
        if not raw_items:
            continue
        elems = [entry["build"](item, i) for i, item in enumerate(raw_items)]
        violations.extend(engine.check(elems, rule_ids=entry["rule_ids"]))

    # 门窗碰撞：同一面墙上 门/窗 重叠（几何层规则，非规范条文）
    rooms = _layout_from_state(state)["rooms"]
    door_layout = place_doors_on_walls(raw_doors, rooms)
    win_layout = place_windows_on_walls(raw_windows, rooms)
    opening_collisions = detect_opening_collisions(door_layout, win_layout)
    for c in opening_collisions:
        violations.append(_collision_violation(c))
    # 门窗碰撞结果自洽诊断 (仿 M4 clash 侧 verify_clashes 范式): 检出结果过
    # verify_opening_collisions, 脏 a_id/b_id / 非法 kind / 非正 overlap 会被如实
    # 标出 (不静默穿透)。诊断随节点 return 带出 (langgraph 只有节点返回 dict 的键
    # 才进最终 state, 端点/出图侧才拿得到), 主链路 violations 追加逻辑 0 改动。
    from src.agents.src.layout import verify_opening_collisions
    opening_check = verify_opening_collisions(door_layout, win_layout, opening_collisions)

    # 多专业碰撞：管线/电气/暖通 段与点位 vs 结构梁/柱 (几何层, 非规范条文)
    # 只追加, 不改既有 _ELEMENT_CHECKS / 门窗碰撞逻辑; 无碰撞样本零新增。
    # M4 容差取值通道: state.clash_tolerance_m (会话级覆盖) > default.json 规则参数
    # (由前端/引擎透传, 本链路未接入时保持 0.15 默认, 来源标注 honest) > 几何默认。
    from src.agents.src.tools.clash_detection import resolve_clash_tolerance
    _clash_rule = None
    try:
        _clash_rule = engine.get_rule("clash-tolerance-range")  # 若 DSL 有该规则
    except Exception:
        _clash_rule = None  # 契约: DSL 无该规则/取不到 → 走几何默认 (resolve 兜 0.15), 非吞错
    _tol, _ = resolve_clash_tolerance(
        default_m=0.15,
        dsl_rule=_clash_rule,
        params=state.get("clash_params"),
    )
    for c in detect_clashes(raw, tolerance_m=_tol):
        violations.append(_clash_violation(c))

    # M5 两稿改动冲突：仅当 state 提供第二稿 (conflict_raw_b) 时比对, 记一条汇总
    # 违规。无第二稿 → 0 新增, 默认样本 (仅 raw_data) 零影响。
    raw_b = state.get("conflict_raw_b")
    if raw_b is not None:
        from src.agents.src.tools import conflict_detection as cf
        conflicts = cf.detect_conflicts(raw, raw_b)
        s = cf.summarize_conflicts(conflicts)
        if s["total"]:
            from src.rules.src.engine import RuleViolation, ViolationSeverity
            violations.append(RuleViolation(
                rule_id="conflict-two-drafts",
                rule_name="两稿改动冲突检查",
                severity=ViolationSeverity.ERROR,
                description=(f"两稿 {s['total']} 处改动冲突 "
                             f"(值 {s['value_conflicts']} / 新增 {s['added']} / "
                             f"删除 {s['removed']})"),
                element_id="draft-a×draft-b",
                code_ref="团队协作（两稿按元素 id 比对, 同 id 不同字段值=冲突）",
            ))

    return {
        "rule_violations": [
            {
                "rule_id": v.rule_id,
                "rule_name": v.rule_name,
                "severity": v.severity.value,
                "description": v.description,
                "element_id": v.element_id,
                "code_ref": v.code_ref,
            }
            for v in violations
        ],
        "rule_check_passed": len(violations) == 0,
        # 门窗碰撞自洽诊断 (机制层, 仿 M4 verify_clashes 范式): 随节点 return 带出,
        # 端点/出图侧拿得到。valid=False 时 issues 逐条定位脏 a_id/b_id / 非法 kind。
        "opening_collisions_check": opening_check,
    }


def export_node(state: dict) -> dict:
    """
    成果输出 Agent：生成DWG/PDF/材料表
    从CAD结果中统计真实材料用量
    """
    dwg_path = state.get("final_dwg_path", "/tmp/ai_cad_result.dwg")
    cad_results = state.get("cad_results", [])

    # 从CAD执行结果中统计材料
    door_count = sum(1 for r in cad_results if r.get("task_id", "").startswith("door"))
    window_count = sum(1 for r in cad_results if r.get("task_id") == "window-all")

    material_table = {
        "doors": [
            {"type": "户门", "width_m": 1.0, "count": 1, "spec": "防盗门"},
            {"type": "室内门", "width_m": 0.9, "count": max(0, door_count - 1), "spec": "木门"},
            {"type": "卫生间门", "width_m": 0.8, "count": 1, "spec": "铝镁合金门"},
        ],
        "windows": [
            {"type": "窗户", "sill_height_m": 0.9, "count": max(1, window_count), "spec": "断桥铝窗"},
        ],
        "walls": [
            {"type": "外墙", "thickness_m": 0.24, "length_m": 32, "spec": "混凝土砌块"},
            {"type": "内墙", "thickness_m": 0.12, "length_m": 18, "spec": "轻质隔墙"},
        ],
    }

    return {
        "final_dwg_path": dwg_path,
        "export_format": "DWG",
        "material_tables": [material_table],
        "export_status": "completed",
    }
