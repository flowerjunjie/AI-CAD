"""
input_parser + wall_topology 纯函数边界单测 (补 60%→~90% / 72%→~90%)

仿 test_clash_detection.py 纯函数范式: 无 fixture、可 `python 文件` 直跑、
无中文/emoji print。覆盖缺口 (coverage -m 定位):
  input_parser.py:  168-268 parse_natural_language (mock LLM) / 279-282 parse_input
  wall_topology.py: 34 snap_key / 39-45 build_adjacency / 49-55 _signed_area /
                    97 非 Polygon face 分支 / 116-118 异常兜底 / 123 add_door_bridge_edges

注意: __main__ 块只调用 test_* 函数 (不 import 别的用例/全局引擎), 末尾 ASCII print,
以通过 tests/unit/test_direct_run.py 的「可直跑 exit 0」护栏。
"""
import json
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _import_parser():
    from src.agents.src.nodes import input_parser as ip
    return ip


def _import_topo():
    from src.agents.src.tools import wall_topology as wt
    return wt


# ── input_parser.parse_json_input 边界 ─────────────────────────────────────
def test_parse_json_input_empty_data():
    """完全空 JSON {}: 各列表缺失走默认, 仍出 dim-axis/dim-opening 标注任务。"""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8",
                                     delete=False) as f:
        json.dump({}, f)
        path = f.name
    try:
        ip = _import_parser()
        res = ip.parse_json_input(path)
        assert res["project_type"] == "住宅"          # 默认兜底
        assert res["disciplines"] == ["建筑"]          # 默认兜底
        assert res["project_structure"]["floors"] == 1
        assert res["project_structure"]["building_area"] == 0  # 无 zones
        ids = [t["id"] for t in res["task_list"]]
        assert "dim-axis" in ids and "dim-opening" in ids     # 标注恒出
        assert "wall-outer" not in ids                          # 无墙不出
    finally:
        os.unlink(path)


def test_parse_json_input_all_wall_and_door_types():
    """outer/inner 墙 + entrance/interior/bathroom 门 + windows 全命中分支。"""
    import tempfile
    data = {
        "walls": [
            {"id": "w1", "type": "outer", "thickness_m": 0.25},
            {"id": "w2", "type": "inner", "thickness_m": 0.1},
            {"id": "w3", "type": "other"},   # 未知 wall type 被过滤
        ],
        "doors": [
            {"id": "entr-1", "type": "entrance", "width_m": 1.2},
            {"id": "int-1", "type": "interior", "location": "主卧"},
            {"id": "bath-1", "type": "bathroom", "width_m": 0.8},
        ],
        "windows": [{"sill_height_m": 0.7}],
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8",
                                     delete=False) as f:
        json.dump(data, f)
        path = f.name
    try:
        ip = _import_parser()
        res = ip.parse_json_input(path)
        ids = [t["id"] for t in res["task_list"]]
        assert "wall-outer" in ids
        assert "wall-inner" in ids
        assert "entr-1" in ids            # 户门用真实 id
        assert "int-1" in ids            # 室内门用真实 id
        assert "bath-1" in ids           # 卫生间门用真实 id
        assert "window-all" in ids
    finally:
        os.unlink(path)


def test_parse_json_input_door_missing_id_fallback():
    """门缺 id → 兜底门牌号 (interior 走 door-room-N, entrance 走 door-entrance)。"""
    import tempfile
    data = {
        "doors": [
            {"type": "entrance"},                       # 缺 id + 缺 width
            {"type": "interior", "location": "次卧"},    # 缺 id + 缺 width
        ],
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8",
                                     delete=False) as f:
        json.dump(data, f)
        path = f.name
    try:
        ip = _import_parser()
        res = ip.parse_json_input(path)
        ids = [t["id"] for t in res["task_list"]]
        assert "door-entrance" in ids                       # 户门兜底
        assert any(i.startswith("door-room-") for i in ids)  # 室内门兜底
    finally:
        os.unlink(path)


def test_parse_json_input_numeric_coercion_and_unknown_keys():
    """width_m 传字符串 / 未知键被忽略 / building_area 缺省回退 sum(zones.area)。"""
    import tempfile
    data = {
        "zzz_unknown_key": "ignored",   # 未知键不炸
        "doors": [{"id": "d1", "type": "entrance", "width_m": "1.5"}],
        "zones": [{"name": "客厅", "area": 20, "type": "living"},
                  {"name": "主卧", "area": 12, "type": "bedroom"}],
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8",
                                     delete=False) as f:
        json.dump(data, f)
        path = f.name
    try:
        ip = _import_parser()
        res = ip.parse_json_input(path)
        # building_area 缺失 → 回退 sum(zones.area) = 32
        assert res["project_structure"]["building_area"] == 32
        assert len(res["project_structure"]["zones"]) == 2
        door = next(t for t in res["task_list"] if t["id"] == "d1")
        assert door["params"]["width"] == "1.5"  # 字符串照传 (不强转), 描述拼接安全
    finally:
        os.unlink(path)


def test_parse_json_input_building_area_explicit():
    """显式 building_area 优先于 zones 求和。"""
    import tempfile
    data = {"building_area": 88, "zones": [{"name": "a", "area": 50, "type": "living"}]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8",
                                     delete=False) as f:
        json.dump(data, f)
        path = f.name
    try:
        ip = _import_parser()
        res = ip.parse_json_input(path)
        assert res["project_structure"]["building_area"] == 88
    finally:
        os.unlink(path)


def test_parse_json_input_phase_keys_present():
    """pipes/beams/columns/outlets/switches/hvac_* 存在即出对应任务。"""
    import tempfile
    data = {
        "pipes": [{"id": "p1"}],
        "structural_beams": [{"id": "b1"}, {"id": "b2"}],
        "structural_columns": [{"id": "c1"}],
        "outlets": [{"id": "o1"}],
        "switches": [{"id": "s1"}],
        "hvac_ducts": [{"id": "d1"}],
        "hvac_units": [{"id": "u1"}],
        "hvac_grilles": [{"id": "g1"}, {"id": "g2"}],
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8",
                                     delete=False) as f:
        json.dump(data, f)
        path = f.name
    try:
        ip = _import_parser()
        res = ip.parse_json_input(path)
        ids = [t["id"] for t in res["task_list"]]
        assert "pipe-plumbing" in ids
        assert "beam-structural" in ids
        assert "column-structural" in ids
        assert "outlet-elec" in ids
        assert "switch-elec" in ids
        assert "hvac-system" in ids
        hvac = next(t for t in res["task_list"] if t["id"] == "hvac-system")
        assert hvac["params"] == {"ducts": 1, "units": 1, "grilles": 2}
    finally:
        os.unlink(path)


def test_parse_json_input_missing_phase_keys_no_task():
    """缺 Phase 键时对应任务不生成 (回归安全: 零改动)。"""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8",
                                     delete=False) as f:
        json.dump({"zones": [{"name": "a", "area": 10, "type": "living"}]}, f)
        path = f.name
    try:
        ip = _import_parser()
        res = ip.parse_json_input(path)
        ids = [t["id"] for t in res["task_list"]]
        for absent in ("pipe-plumbing", "beam-structural", "column-structural",
                       "outlet-elec", "switch-elec", "hvac-system", "window-all"):
            assert absent not in ids, f"{absent} 不应生成"
    finally:
        os.unlink(path)


# ── input_parser.parse_natural_language (mock LLM, 全分支) ────────────────
def _mock_llm_module(text, json_mode="plain"):
    """构造 mock 的 llm_adapter 模块, 让 parse_natural_language 的 import 命中。
    返回 (mock_module, monkeypatch-able 说明)。调用方用 sys.modules 注入。"""
    import types
    mod = types.ModuleType("src.agents.src.tools.llm_adapter")

    class _Resp:
        def __init__(self, t):
            self.text = t
            self.model = "mock"
            self.usage = {}
            self.error = None

    class _Adapter:
        def chat_with_retry(self, messages, **kw):
            return _Resp(text)

    class LLMFactory:
        @classmethod
        def from_env(cls):
            return _Adapter()

    class ChatMessage:
        def __init__(self, role="", content=""):
            self.role = role
            self.content = content

    mod.LLMFactory = LLMFactory
    mod.ChatMessage = ChatMessage
    return mod


def test_parse_natural_language_plain_json():
    """纯 {...} JSON 文本 → 走 '{' 提取分支, 生成门/窗任务。"""
    ip = _import_parser()
    import types
    raw = json.dumps({
        "project_type": "办公", "disciplines": ["建筑", "结构"],
        "building_area": 60, "floors": 2,
        "zones": [{"name": "开放区", "area": 40, "type": "office"},
                  {"name": "会议室", "area": 15, "type": "meeting"}],
        "door_count": 3, "window_count": 2,
    })
    mock = _mock_llm_module(raw)
    _patch_llm(sys.modules, mock)
    try:
        res = ip.parse_natural_language("两间办公室60平")
        assert res["project_type"] == "办公"
        assert res["disciplines"] == ["建筑", "结构"]
        assert res["project_structure"]["floors"] == 2
        assert res["project_structure"]["building_area"] == 60
        assert len(res["project_structure"]["zones"]) == 2
        ids = [t["id"] for t in res["task_list"]]
        assert "door-entrance" in ids
        assert any(i.startswith("door-room-") for i in ids)  # door_count=3 → 2 间内门
        assert "window-all" in ids
    finally:
        _restore_llm()


def test_parse_natural_language_fenced_json_block():
    """```json ... ``` 代码块 → 走 split('```json') 提取分支。"""
    ip = _import_parser()
    raw = "```json\n" + json.dumps({"zones": [{"name": "a", "area": 5}],
                                    "door_count": 1, "window_count": 0}) + "\n```"
    mock = _mock_llm_module(raw)
    _patch_llm(sys.modules, mock)
    try:
        res = ip.parse_natural_language("一间房")
        assert len(res["project_structure"]["zones"]) == 1
        # window_count=0 → 不生成 window 任务
        ids = [t["id"] for t in res["task_list"]]
        assert "window-all" not in ids
        # door_count=1 → min(1-1, len(zones)+2)=0 间内门, 只有户门
        assert not any(i.startswith("door-room-") for i in ids)
    finally:
        _restore_llm()


def test_parse_natural_language_bad_json_fallback():
    """LLM 回非法 JSON → 走 JSONDecodeError 兜底 (空 task_list + 默认住宅)。"""
    ip = _import_parser()
    mock = _mock_llm_module("这不是JSON{只输出文字")
    _patch_llm(sys.modules, mock)
    try:
        res = ip.parse_natural_language("随便")
        assert res["project_type"] == "住宅"
        assert res["task_list"] == []
        assert res["raw_data"] == {}
    finally:
        _restore_llm()


def test_parse_natural_language_empty_text_fallback():
    """LLM 回空文本 → 默认住宅 fallback (无 LLM 分支)。"""
    ip = _import_parser()
    mock = _mock_llm_module("")
    _patch_llm(sys.modules, mock)
    try:
        res = ip.parse_natural_language("随便")
        assert res["project_type"] == "住宅"
        assert res["project_structure"]["zones"] == []
        assert res["task_list"] == []
    finally:
        _restore_llm()


def test_parse_natural_language_defaults_no_zone_counts():
    """LLM JSON 缺 door_count/window_count/zones → 走默认 (door=zones+1, window=max(1,0))。"""
    ip = _import_parser()
    raw = json.dumps({"zones": [], "door_count": None, "window_count": None})
    # 源码: door_count=parsed.get('door_count', len(zones)+1) — None 会取出 None
    # 改用完全缺键的 dict 触发默认
    raw = json.dumps({"zones": [{"name": "a", "area": 3}]})
    mock = _mock_llm_module(raw)
    _patch_llm(sys.modules, mock)
    try:
        res = ip.parse_natural_language("小房间")
        ps = res["project_structure"]
        # zones 缺 name/type 兜底
        assert ps["zones"][0]["name"] == "a"
        ids = [t["id"] for t in res["task_list"]]
        # door_count 默认 = len(zones)+1 = 2 → min(2-1, 1+2)=1 间内门
        assert any(i.startswith("door-room-") for i in ids)
        # window_count 默认 = max(1, 1//2)=1 → 出 window
        assert "window-all" in ids
    finally:
        _restore_llm()


def test_parse_input_dispatcher_is_file():
    """parse_input: is_file=True 走 parse_json_input。"""
    import tempfile
    ip = _import_parser()
    data = {"zones": [{"name": "a", "area": 9, "type": "living"}]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8",
                                     delete=False) as f:
        json.dump(data, f)
        path = f.name
    try:
        res = ip.parse_input(path, is_file=True)
        assert res["raw_data"] == data
    finally:
        os.unlink(path)


def test_parse_input_dispatcher_text():
    """parse_input: is_file=False 走 parse_natural_language (mock LLM)。"""
    ip = _import_parser()
    raw = json.dumps({"zones": [], "door_count": 1, "window_count": 0})
    mock = _mock_llm_module(raw)
    _patch_llm(sys.modules, mock)
    try:
        res = ip.parse_input("一套房", is_file=False)
        # raw_data 为 mock 出的 parsed dict
        assert "zones" in res["raw_data"]
    finally:
        _restore_llm()


# 用 sys.modules 注入 mock LLM 模块 (parse_natural_language 在函数内 import)
def _patch_llm(modules, mock):
    modules["src.agents.src.tools.llm_adapter"] = mock


def _restore_llm():
    modules = sys.modules
    if "src.agents.src.tools.llm_adapter" in modules:
        del modules["src.agents.src.tools.llm_adapter"]


# ── wall_topology 纯函数边界 ──────────────────────────────────────────────
def test_snap_key_returns_snapped_grid():
    """snap_key == snap_point, 端点吸附到 tol 网格。"""
    wt = _import_topo()
    assert wt.snap_key((0.0004, 0.0004)) == (0.0, 0.0)
    assert wt.snap_key((4.0006, 3.9999)) == (4.001, 4.0)  # round(4000.6)=4001
    # 自定义 tol
    assert wt.snap_key((0.03, 0.03), tol=0.05) == (0.05, 0.05)


def test_build_adjacency_endpoints():
    """端点键 → 邻接 (to/id), 双向登记。"""
    wt = _import_topo()
    segs = [((0, 0), (4, 0)), ((4, 0), (4, 3))]
    adj = wt.build_adjacency(segs)
    # (0,0) 只连 1 段 → (4,0)
    assert {"to": (4, 0), "id": 0} in adj[(0, 0)]
    # (4,0) 是两段共享端点 → 2 个邻居
    assert len(adj[(4, 0)]) == 2, f"(4,0) 应有 2 邻, 实际 {adj[(4, 0)]}"
    assert {"to": (0, 0), "id": 0} in adj[(4, 0)]
    assert {"to": (4, 3), "id": 1} in adj[(4, 0)]


def test_signed_area_positive_and_negative():
    """_signed_area: CCW 正, CW 负, 面积绝对值一致。"""
    wt = _import_topo()
    ccw = [(0, 0), (2, 0), (2, 2), (0, 2)]   # 4x... 2x2 正方形, 逆时针
    cwn = [(0, 0), (0, 2), (2, 2), (2, 0)]   # 顺时针
    assert abs(wt._signed_area(ccw)) == 4.0
    assert wt._signed_area(ccw) > 0, "CCW 应为正"
    assert wt._signed_area(cwn) < 0, "CW 应为负"
    assert abs(wt._signed_area(ccw)) == abs(wt._signed_area(cwn))


def test_bbox_helper():
    """_bbox: 取 min/max x,y。"""
    wt = _import_topo()
    assert wt._bbox([(0, 0), (3, 5), (7, 1)]) == (0, 0, 7, 5)


def test_add_door_bridge_edges_merges():
    """门洞虚拟边: 返回 segs + door_segs 合并列表。"""
    wt = _import_topo()
    segs = [((0, 0), (4, 0))]
    doors = [((4, 0), (4, 3))]
    merged = wt.add_door_bridge_edges(segs, doors)
    assert merged == [((0, 0), (4, 0)), ((4, 0), (4, 3))]
    assert merged is not segs  # 新列表, 不突变入参
    assert segs == [((0, 0), (4, 0))]  # 入参不被修改


def test_partition_rooms_slanted_walls():
    """斜墙围成三角形房间 (非轴对齐) → polygonize 仍切出 1 面。"""
    wt = _import_topo()
    segs = [((0, 0), (6, 0)), ((6, 0), (3, 4)), ((3, 4), (0, 0))]
    res = wt.partition_rooms(segs)
    assert res["diagnostics"]["error"] is None
    assert len(res["rooms"]) == 1, f"斜墙三角形应切 1 面, 实际 {len(res['rooms'])}"
    assert abs(res["rooms"][0]["area"] - 12.0) < 1e-6  # 底6 高4 → 12㎡
    assert res["rooms"][0]["is_outer"] is False


def test_partition_rooms_single_segment_no_face():
    """单段 (不闭合) → 0 房间, 无 error。"""
    wt = _import_topo()
    res = wt.partition_rooms([((0, 0), (5, 0))])
    assert res["rooms"] == []
    assert res["diagnostics"]["closed_faces"] == 0
    assert res["diagnostics"]["error"] is None


def test_partition_rooms_overlapping_segments():
    """重叠共线墙段 (重复画) → 不崩, union 合并后仍切出正确房间。"""
    wt = _import_topo()
    segs = [
        ((0, 0), (4, 0)), ((4, 0), (4, 4)), ((4, 4), (0, 4)), ((0, 4), (0, 0)),
        ((0, 0), (4, 0)),   # 重复边
        ((2, 0), (2, 4)),   # 中间墙
    ]
    res = wt.partition_rooms(segs)
    assert res["diagnostics"]["error"] is None
    # 4x4 被中间墙分成 2 间, 各 4x2=8㎡
    rooms = res["rooms"]
    assert len(rooms) == 2, f"应 2 间, 实际 {len(rooms)}"
    for r in rooms:
        assert abs(r["area"] - 8.0) < 1e-6


def test_partition_rooms_degenerate_all_snapped_away():
    """所有段吸附后退化 (零长) → 提前返回空 rooms, error=None。"""
    wt = _import_topo()
    segs = [((0.0004, 0.0004), (0.0004, 0.0004))]  # 端点吸附后 sa==sb
    res = wt.partition_rooms(segs, tol=1e-3)
    assert res["rooms"] == []
    assert res["diagnostics"]["error"] is None
    assert res["diagnostics"]["closed_faces"] == 0


def test_partition_rooms_except_fallback():
    """_shapely 抛异常 → 走 except, 返回空 rooms + diagnostics.error。"""
    wt = _import_topo()
    orig = wt._shapely
    def _boom():
        raise RuntimeError("shapely unavailable")
    wt._shapely = _boom
    try:
        res = wt.partition_rooms([((0, 0), (4, 0)), ((4, 0), (4, 4))])
        assert res["rooms"] == []
        assert "RuntimeError" in res["diagnostics"]["error"]
    finally:
        wt._shapely = orig  # 还原, 不污染其它用例


def test_partition_rooms_non_polygon_face_dropped():
    """polygonize 输出含非 Polygon (LinearRing) 面 → 走 geom_type 分支跳过。"""
    wt = _import_topo()
    import shapely.geometry as sg
    import shapely.ops as so
    real_geom = sg
    real_ops = so

    # 造个 stub geometry: LineString 正常, 但 polygonize 混入一个 LinearRing
    class _Geom:
        LineString = sg.LineString
    # 需要 unary_union 正常 (真实 ops), polygonize 返回混入非 Polygon
    def _union(lines):
        return so.unary_union(lines)
    def _poly(geom):
        ring = sg.LinearRing([(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)])
        real = list(so.polygonize(geom))
        return [ring] + real  # 头部塞一个 LinearRing (geom_type != Polygon)
    stub_cache = {"geometry": _Geom, "ops": type("O", (), {
        "unary_union": staticmethod(_union),
        "polygonize": staticmethod(_poly),
    })}
    orig = wt._shapely
    wt._shapely = lambda: stub_cache
    try:
        segs = [((0, 0), (4, 0)), ((4, 0), (4, 4)), ((4, 4), (0, 4)), ((0, 4), (0, 0))]
        res = wt.partition_rooms(segs)
        assert res["diagnostics"]["error"] is None
        # LinearRing 被跳, 真实正方形 1 面保留
        assert len(res["rooms"]) == 1, f"LinearRing 应被跳, 实际 {len(res['rooms'])}"
        assert abs(res["rooms"][0]["area"] - 16.0) < 1e-6
    finally:
        wt._shapely = orig  # 还原


def test_partition_rooms_empty_polygon_face():
    """空 Polygon 面 (is_empty) 被跳 — 用真实 shapely 塞入 EMPTY polygon 无法经
    polygonize 产生, 故走 stub 补一个 EmptyGeometry。"""
    wt = _import_topo()
    import shapely.geometry as sg
    import shapely.ops as so
    real_ops = so
    def _poly(geom):
        empty = sg.Polygon()  # 空 polygon, is_empty=True
        return [empty] + list(so.polygonize(geom))
    stub_cache = {"geometry": sg, "ops": type("O", (), {
        "unary_union": staticmethod(so.unary_union),
        "polygonize": staticmethod(_poly),
    })}
    wt._shapely = lambda: stub_cache
    orig = wt._shapely
    try:
        segs = [((0, 0), (4, 0)), ((4, 0), (4, 4)), ((4, 4), (0, 4)), ((0, 4), (0, 0))]
        res = wt.partition_rooms(segs)
        assert res["diagnostics"]["error"] is None
        assert len(res["rooms"]) == 1  # 空 polygon 被跳, 只留 1 面
    finally:
        wt._shapely = orig


def test_partition_rooms_min_area_boundary():
    """area 恰好 < min_room_area 被丢, == 保留 (边界)。"""
    wt = _import_topo()
    # 2x2=4㎡ 正方形
    segs = [((0, 0), (2, 0)), ((2, 0), (2, 2)), ((2, 2), (0, 2)), ((0, 2), (0, 0))]
    res = wt.partition_rooms(segs, min_room_area=4.0)
    assert len(res["rooms"]) == 1  # 4㎡ == min_room_area, 保留 (area < min 才丢)
    res2 = wt.partition_rooms(segs, min_room_area=4.0001)
    assert len(res2["rooms"]) == 0  # 4㎡ < 4.0001, 丢
    assert res2["diagnostics"]["dropped_small"] == 1


if __name__ == "__main__":
    test_parse_json_input_empty_data()
    test_parse_json_input_all_wall_and_door_types()
    test_parse_json_input_door_missing_id_fallback()
    test_parse_json_input_numeric_coercion_and_unknown_keys()
    test_parse_json_input_building_area_explicit()
    test_parse_json_input_phase_keys_present()
    test_parse_json_input_missing_phase_keys_no_task()
    test_parse_natural_language_plain_json()
    test_parse_natural_language_fenced_json_block()
    test_parse_natural_language_bad_json_fallback()
    test_parse_natural_language_empty_text_fallback()
    test_parse_natural_language_defaults_no_zone_counts()
    test_parse_input_dispatcher_is_file()
    test_parse_input_dispatcher_text()
    test_snap_key_returns_snapped_grid()
    test_build_adjacency_endpoints()
    test_signed_area_positive_and_negative()
    test_bbox_helper()
    test_add_door_bridge_edges_merges()
    test_partition_rooms_slanted_walls()
    test_partition_rooms_single_segment_no_face()
    test_partition_rooms_overlapping_segments()
    test_partition_rooms_degenerate_all_snapped_away()
    test_partition_rooms_except_fallback()
    test_partition_rooms_non_polygon_face_dropped()
    test_partition_rooms_empty_polygon_face()
    test_partition_rooms_min_area_boundary()
    print("OK: all input_parser + wall_topology tests passed")
