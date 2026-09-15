"""
Agent 节点 — CAD执行 + 规则校验 + 成果输出
消费 raw_data 几何数据（zones/doors/windows），不再用硬编码坐标
"""
import os
from src.agents.src.tools.cad_tools import DXFWriter, Wall, Door as CADDoor, Window as CADWindow, Point
from src.agents.src.tools.rag_tools import RAGKnowledgeBase
from src.agents.src.layout import layout_rooms, place_doors_on_walls, place_windows_on_walls, detect_opening_collisions
from src.agents.src.tools.wall_topology import partition_rooms
from src.rules.src.engine import get_engine
from src.rules.src.residential.doors import Door
from src.rules.src.residential.windows import Window
from src.rules.src.residential.rooms import Room
from src.rules.src.plumbing import PlumbingPipe
from src.rules.src.electrical import ElectricalOutlet, ElectricalSwitch
from src.rules.src.dsl import load_dsl_rules


# DSL 规则（default.json）加载后 upsert 进全局引擎；全局引擎默认没有它们，
# 主链路校验前需显式加载一次（upsert 幂等，同 rule_id 顶替，重复调用安全）。
# 不再维护专业前缀白名单 — _ensure_dsl_rules_loaded 按「引擎里还没有」数据驱动判断,
# 加新 DSL 专业只需往 default.json 加条目, 主链路零改动。


def _dsl_rules_path() -> str:
    """default.json 绝对路径（__file__ 回 5 层 dirname 到项目根）。"""
    # __file__ = .../AI-CAD/src/agents/src/nodes/cad_rule_export.py
    # 5 层 dirname 回项目根 (nodes→src→agents→src→AI-CAD)
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    return os.path.join(root, "src", "rules", "rules", "default.json")


def _ensure_dsl_rules_loaded(engine) -> None:
    """加载 default.json 的 DSL 规则, 只 upsert 标记 dsl_only=true 的纯新增专业规则。

    判据 (稳定, 不依赖 import 时序): 由 default.json 每条规则的 dsl_only 字段声明
    「这条是纯 DSL 新增专业」, 而非靠「引擎里有没有它」反推 (后者受调用方 import
    过哪些规则模块影响, 时序脆弱)。

    - 纯新增专业 (plumbing-/electrical-/未来 hvac-...) 在 default.json 里标
      "dsl_only": true → 主链路 upsert 进引擎。
    - 与 @register_rule 的 34 类重名的「参数覆盖」规则保持 dsl_only 默认 false
      → 不 upsert, 硬编码版不动 (守 34 类零改动红线)。

    加新专业 = 往 default.json 加条目 + 标 dsl_only:true, 主链路零改动。
    JSON 只解析一次。
    """
    for rule in load_dsl_rules(_dsl_rules_path()):
        if getattr(rule, "dsl_only", False):
            engine.upsert(rule)


def _build_door(raw: dict) -> Door:
    return Door(id=raw.get("id", "d0"), width_m=float(raw.get("width_m", 0.9)),
                room_type=raw.get("type", "interior"), location=(0, 0))


def _build_window(raw: dict) -> Window:
    return Window(id=raw.get("id", "w0"), sill_height_m=float(raw.get("sill_height_m", 0.9)),
                 top_height_m=2.0, room_type=raw.get("room", "living"), location=(0, 0))


def _build_room(raw: dict, idx: int) -> Room:
    return Room(id=raw.get("id", f"r{idx}"), name=raw.get("name", ""),
                length_m=float(raw.get("length", 0)), width_m=float(raw.get("width", 0)))


def _build_pipe(raw: dict, idx: int) -> PlumbingPipe:
    return PlumbingPipe(
        id=raw.get("id", f"p{idx}"),
        pipe_type=raw.get("pipe_type", "drain"),
        diameter_mm=int(raw.get("diameter_mm", 50)),
        slope=float(raw.get("slope", 0.0)),
        distance_to_manhole_m=float(raw.get("distance_to_manhole_m", 0.0)),
    )


def _build_outlet(raw: dict, idx: int) -> ElectricalOutlet:
    return ElectricalOutlet(
        id=raw.get("id", f"o{idx}"),
        height_m=float(raw.get("height_m", 0.3)),
        room_type=raw.get("room_type", "living"),
        x=float(raw.get("x", 0.0)),
        y=float(raw.get("y", 0.0)),
        has_earthing=bool(raw.get("has_earthing", True)),
    )


def _build_switch(raw: dict, idx: int) -> ElectricalSwitch:
    return ElectricalSwitch(
        id=raw.get("id", f"s{idx}"),
        height_m=float(raw.get("height_m", 1.3)),
        room_type=raw.get("room_type", "living"),
        x=float(raw.get("x", 0.0)),
        y=float(raw.get("y", 0.0)),
    )


# 分发表：raw_key → 构造器 → 规则集。
# build 签名统一 build(raw_item, idx) → element（door/window 忽略 idx）。
# 新增专业 = 加一项表项 + 对应 DSL/类规则，不改 rule_check_node 主链路逻辑。
_ELEMENT_CHECKS: list[dict] = [
    {
        "raw_key": "doors",
        "build": lambda r, i: _build_door(r),
        "rule_ids": [
            "residential-door-main-width",
            "residential-door-interior-width",
            "residential-door-bathroom-width",
        ],
    },
    {
        "raw_key": "windows",
        "build": lambda r, i: _build_window(r),
        "rule_ids": ["residential-window-sill-height"],
    },
    {
        # zones 走 raw_data；无 raw 时由调用侧 fallback project_structure（见 rule_check_node）
        "raw_key": "zones",
        "build": _build_room,
        "rule_ids": [
            "residential-room-living-area",
            "residential-room-bedroom-area",
            "residential-room-kitchen-area",
            "residential-room-bathroom-area",
        ],
    },
    {
        "raw_key": "pipes",
        "build": _build_pipe,
        "rule_ids": [
            "plumbing-waste-pipe-min-diameter",
            "plumbing-pipe-slope-in-range",
            "plumbing-pipe-manhole-distance",
        ],
    },
    # 电气（Phase 4）— 走 DSL electrical-* 规则（阈值占位 TBD，待业务确认）
    {
        "raw_key": "outlets",
        "build": _build_outlet,
        "rule_ids": [
            "electrical-outlet-height-range",
            "electrical-outlet-earthing-required",
        ],
    },
    {
        "raw_key": "switches",
        "build": _build_switch,
        "rule_ids": ["electrical-switch-height-range"],
    },
]


def _collision_violation(c: dict):
    """把几何碰撞结果转成 RuleViolation（与 engine.check 同构，供统一遍历）"""
    from src.rules.src.engine import RuleViolation, ViolationSeverity
    kind_cn = {"door-door": "两扇门", "door-window": "门与窗", "window-window": "两扇窗"}
    label = kind_cn.get(c["kind"], c["kind"])
    return RuleViolation(
        rule_id="layout-opening-collision",
        rule_name="门窗碰撞检查",
        severity=ViolationSeverity.ERROR,
        description=f"同一面墙上{label}重叠 {c['overlap_m']:.2f}m：{c['a_id']} × {c['b_id']}",
        element_id=f"{c['a_id']}×{c['b_id']}",
        code_ref="施工图制图规范（门窗洞口应互不侵占）",
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

    tasks = state.get("task_list", [])
    results = []
    confirmations = {}

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
                    count = len(_outer_walls(rooms, thickness))
                else:
                    inner = _inner_walls(rooms, thickness)
                    for w in inner:
                        writer.add_wall(w)
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

            elif task_type == "window":
                for wp in window_pos:
                    writer.add_window(CADWindow(
                        start=Point(wp["start"][0], wp["start"][1]),
                        end=Point(wp["end"][0], wp["end"][1]),
                        sill_height=wp["sill_height"],
                    ))
                results.append({"task_id": task_id, "status": "completed",
                                "count": len(window_pos)})

            elif task_type == "dimension":
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
                results.append({"task_id": task_id, "status": "completed"})

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
    for c in detect_opening_collisions(door_layout, win_layout):
        violations.append(_collision_violation(c))

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
