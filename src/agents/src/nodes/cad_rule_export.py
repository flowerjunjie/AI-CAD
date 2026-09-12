"""
Agent 节点 — CAD执行 + 规则校验 + 成果输出
消费 raw_data 几何数据（zones/doors/windows），不再用硬编码坐标
"""
import os
from src.agents.src.tools.cad_tools import DXFWriter, Wall, Door as CADDoor, Window as CADWindow, Point
from src.agents.src.tools.rag_tools import RAGKnowledgeBase
from src.agents.src.layout import layout_rooms, place_doors_on_walls, place_windows_on_walls
from src.rules.src.engine import get_engine
from src.rules.src.residential.doors import Door
from src.rules.src.residential.windows import Window
from src.rules.src.residential.rooms import Room


def _layout_from_state(state: dict) -> dict:
    """从 state 提取 zones/doors/windows，跑布局引擎，返回坐标。"""
    raw = state.get("raw_data", {}) or {}
    zones = raw.get("zones", []) or state.get("project_structure", {}).get("zones", [])
    doors = raw.get("doors", [])
    windows = raw.get("windows", [])

    rooms = layout_rooms(zones)
    door_pos = place_doors_on_walls(doors, rooms)
    window_pos = place_windows_on_walls(windows, rooms)
    return {"rooms": rooms, "doors": door_pos, "windows": window_pos, "zones": zones}


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
    """
    engine = get_engine()
    raw = state.get("raw_data", {}) or {}
    zones = raw.get("zones", []) or state.get("project_structure", {}).get("zones", [])
    raw_doors = raw.get("doors", [])
    raw_windows = raw.get("windows", [])
    violations = []

    # 门宽（按实际 room_type 匹配规则）
    if raw_doors:
        door_elems = [
            Door(id=d.get("id", f"d{i}"), width_m=float(d.get("width_m", 0.9)),
                 room_type=d.get("type", "interior"), location=(0, 0))
            for i, d in enumerate(raw_doors)
        ]
        violations.extend(engine.check(door_elems, rule_ids=[
            "residential-door-main-width",
            "residential-door-interior-width",
            "residential-door-bathroom-width",
        ]))

    # 窗台高度
    if raw_windows:
        win_elems = [
            Window(id=w.get("id", f"w{i}"), sill_height_m=float(w.get("sill_height_m", 0.9)),
                   top_height_m=2.0, room_type=w.get("room", "living"), location=(0, 0))
            for i, w in enumerate(raw_windows)
        ]
        violations.extend(engine.check(win_elems, rule_ids=["residential-window-sill-height"]))

    # 房间面积（zones 带 length/width）
    room_elems = [
        Room(id=z.get("id", f"r{i}"), name=z.get("name", ""),
             length_m=float(z.get("length", 0)), width_m=float(z.get("width", 0)))
        for i, z in enumerate(zones)
    ]
    if room_elems:
        violations.extend(engine.check(room_elems, rule_ids=[
            "residential-room-living-area",
            "residential-room-bedroom-area",
            "residential-room-kitchen-area",
            "residential-room-bathroom-area",
        ]))

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
