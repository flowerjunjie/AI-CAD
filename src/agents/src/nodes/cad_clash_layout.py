"""
cad_rule_export 的「校验辅助段」— 元素构造器 + _ELEMENT_CHECKS 分发表 +
碰撞/重复点定位辅助 (从 cad_rule_export.py 拆出, 2026-10-11 文件健康轮, 破 882 红线)。

职责:
  - 各 _build_* 把 raw_data dict → residential 域元素类 (供 rule_check_node 喂 engine)
  - _ELEMENT_CHECKS 分发表: raw_key → 构造器 → rule_ids (加专业=加表项, 主链路零改动)
  - constructible_element_types(): 遍历分发表取 build 返回注解 → 类名白名单
  - _CLASH_KIND_CN / _clash_violation / _clash_point / _duplicate_point: 碰撞定位辅助

依赖: 各元素类 (residential/plumbing/electrical/hvac/structural) 顶部 import;
clash_detection.CLASH_KINDS 做加载期同源对账。ezdxf 无 (纯 dict → 类, 不出图)。
cad_rule_export.py 顶部 re-export 本模块全部符号, 旧 import 路径 0 改动 (兼容层)。

注意 (拆后验证点): constructible_element_types 用 typing.get_type_hints 取 build 返回
注解, 函数搬到本模块后注解在**本模块作用域**解析 — 须全量验证类名集合搬前后一致。
"""
import os
import sys

from src.agents.src.tools.clash_detection import CLASH_KINDS
from src.rules.src.dsl import load_dsl_rules
from src.rules.src.residential.doors import Door
from src.rules.src.residential.windows import Window
from src.rules.src.residential.rooms import Room
from src.rules.src.plumbing import PlumbingPipe
from src.rules.src.electrical import ElectricalOutlet, ElectricalSwitch
from src.rules.src.hvac import HvacDuct, HvacUnit, HvacGrille
from src.rules.src.structural import StructuralBeam, StructuralColumn


# ── DSL 规则加载 (default.json) ───────────────────────────────────────────────

def _dsl_rules_path() -> str:
    """default.json 绝对路径。

    打包态优先: PyInstaller 把 default.json 作为数据文件 --add-data 进 RESOURCE_ROOT
    (onedir=_internal), 落到 <RESOURCE_ROOT>/src/rules/rules/default.json; 这里先查它,
    命中即用。源码态 / 打包态但数据缺失时回退 __file__ 上溯到项目根。
    注: 本文件在 nodes/ 下 (与源 cad_rule_export.py 同层), __file__ 上溯 5 层同范式。
    """
    candidates = []
    # 打包态资源根 (onedir=_internal, onefile=临时解压目录); 源码态没有 _MEIPASS
    resource_root = getattr(sys, "_MEIPASS", None)
    if resource_root:
        candidates.append(os.path.join(resource_root, "src", "rules", "rules", "default.json"))
    # 源码态: __file__ = .../AI-CAD/src/agents/src/nodes/cad_clash_layout.py
    # 5 层 dirname 回项目根 (nodes→src→agents→src→AI-CAD)
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    candidates.append(os.path.join(root, "src", "rules", "rules", "default.json"))
    for c in candidates:
        if os.path.isfile(c):
            return c
    return candidates[-1]  # 都不在就回源码态路径 (调用方 _ensure 会 try/except 兜底)


def _ensure_dsl_rules_loaded(engine) -> None:
    """加载 default.json 的 DSL 规则, 只 upsert 标记 dsl_only=true 的纯新增专业规则。

    判据 (稳定, 不依赖 import 时序): 由 default.json 每条规则的 dsl_only 字段声明
    「这条是纯 DSL 新增专业」, 而非靠「引擎里有没有它」反推 (后者受调用方 import
    过哪些规则模块影响, 时序脆弱)。

    - 纯新增专业 (plumbing-/electrical-/未来 hvac-...) 在 default.json 里标
      "dsl_only": true → 主链路 upsert 进引擎。
    - 与 @register_rule 的硬编码类重名的「参数覆盖」规则保持 dsl_only 默认 false
      → 不 upsert, 硬编码版不动 (守硬编码类零改动红线, 以 git diff 0 行为准)。

    加新专业 = 往 default.json 加条目 + 标 dsl_only:true, 主链路零改动。
    JSON 只解析一次。
    """
    for rule in load_dsl_rules(_dsl_rules_path()):
        if getattr(rule, "dsl_only", False):
            engine.upsert(rule)


# ── 元素构造器: raw_data dict → residential 域元素类 ───────────────────────

def _build_door(raw: dict) -> Door:
    # type: "entrance"/"bathroom" 保留规范原值（各由专属规则管辖）；
    # 缺省/"interior" 才兜底成 "interior" 走户内门 0.9m 规则。
    # 样本 d5 (type=interior, location=厨房) 即由此走户内门规则被检出。
    rtype = raw.get("type", "interior")
    room_type = rtype if rtype in ("entrance", "bathroom") else "interior"
    return Door(id=raw.get("id", "d0"), width_m=float(raw.get("width_m", 0.9)),
                room_type=room_type, location=(0, 0))


def _build_door_2(raw: dict, idx: int) -> Door:
    """_build_door 的两参壳（供 _ELEMENT_CHECKS build(item, i) 调用点复用）。

    带返回注解 -> Door：constructible_element_types() 靠各 build 的返回注解
    派生「主链路可喂类名白名单」，lambda 无注解会丢 Door/Window，故用具名壳。
    """
    return _build_door(raw)


def _build_window(raw: dict) -> Window:
    return Window(id=raw.get("id", "w0"), sill_height_m=float(raw.get("sill_height_m", 0.9)),
                 top_height_m=2.0, room_type=raw.get("room", "living"), location=(0, 0))


def _build_window_2(raw: dict, idx: int) -> Window:
    """_build_window 的两参壳（同 _build_door_2 的注解理由）。"""
    return _build_window(raw)


def _build_room(raw: dict, idx: int) -> Room:
    return Room(id=raw.get("id", f"r{idx}"), name=raw.get("name", ""),
                length_m=float(raw.get("length", 0)), width_m=float(raw.get("width", 0.0)))


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


def _build_hvac_duct(raw: dict, idx: int) -> HvacDuct:
    return HvacDuct(
        id=raw.get("id", f"hd{idx}"),
        duct_type=raw.get("duct_type", "supply"),
        diameter_mm=int(raw.get("diameter_mm", 100)),
        airflow_m3h=float(raw.get("airflow_m3h", 0.0)),
        velocity_ms=float(raw.get("velocity_ms", 0.0)),
    )


def _build_hvac_unit(raw: dict, idx: int) -> HvacUnit:
    return HvacUnit(
        id=raw.get("id", f"hu{idx}"),
        unit_type=raw.get("unit_type", "room"),
        cooling_kw=float(raw.get("cooling_kw", 0.0)),
        location_type=raw.get("location_type", "indoor"),
        x=float(raw.get("x", 0.0)),
        y=float(raw.get("y", 0.0)),
    )


def _build_hvac_grille(raw: dict, idx: int) -> HvacGrille:
    return HvacGrille(
        id=raw.get("id", f"hg{idx}"),
        grille_type=raw.get("grille_type", "supply"),
        height_m=float(raw.get("height_m", 2.5)),
        airflow_m3h=float(raw.get("airflow_m3h", 0.0)),
        room_type=raw.get("room_type", "living"),
        x=float(raw.get("x", 0.0)),
        y=float(raw.get("y", 0.0)),
    )


def _build_structural_beam(raw: dict, idx: int) -> StructuralBeam:
    return StructuralBeam(
        id=raw.get("id", f"sb{idx}"),
        beam_type=raw.get("beam_type", "main"),
        width_mm=int(raw.get("width_mm", 300)),
        depth_mm=int(raw.get("depth_mm", 0)),
        x=float(raw.get("x", 0.0)),
        y=float(raw.get("y", 0.0)),
        span_m=float(raw.get("span_m", 0.0)),
    )


def _build_structural_column(raw: dict, idx: int) -> StructuralColumn:
    return StructuralColumn(
        id=raw.get("id", f"sc{idx}"),
        column_type=raw.get("column_type", "frame"),
        section_mm=int(raw.get("section_mm", 0)),
        x=float(raw.get("x", 0.0)),
        y=float(raw.get("y", 0.0)),
    )


# 分发表：raw_key → 构造器 → 规则集。
# build 签名统一 build(raw_item, idx) → element（door/window 忽略 idx）。
# 新增专业 = 加一项表项 + 对应 DSL/类规则，不改 rule_check_node 主链路逻辑。
_ELEMENT_CHECKS: list[dict] = [
    {
        "raw_key": "doors",
        "build": _build_door_2,
        "rule_ids": [
            "residential-door-main-width",
            "residential-door-interior-width",
            "residential-door-bathroom-width",
        ],
    },
    {
        "raw_key": "windows",
        "build": _build_window_2,
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
    # 暖通（Phase 5）— 走 DSL hvac-* 规则（阈值占位 TBD，待业务确认）
    {
        "raw_key": "hvac_ducts",
        "build": _build_hvac_duct,
        "rule_ids": ["hvac-duct-velocity-range"],
    },
    {
        "raw_key": "hvac_units",
        "build": _build_hvac_unit,
        "rule_ids": ["hvac-unit-outdoor-placement"],
    },
    {
        "raw_key": "hvac_grilles",
        "build": _build_hvac_grille,
        "rule_ids": ["hvac-grille-height-range"],
    },
    # 结构（Phase 6）— 走 DSL structural-* 规则（阈值占位 TBD，待业务确认）
    {
        "raw_key": "structural_beams",
        "build": _build_structural_beam,
        "rule_ids": ["structural-beam-width-depth-ratio"],
    },
    {
        "raw_key": "structural_columns",
        "build": _build_structural_column,
        "rule_ids": ["structural-column-min-section"],
    },
]


def constructible_element_types() -> set[str]:
    """主链路可喂进 engine.check 的元素**类名**白名单（机制量，随 _ELEMENT_CHECKS 派生）。

    唯一权威源——遍历 _ELEMENT_CHECKS 各 build，取其**返回类型注解**（各 build
    已写 `-> Door` 等类型注解，本模块 return 语句与注解恒一致）。DSL 信任边界
    体检（bridge /api/rules/dsl-audit → dsl.audit_rule_elements）据此对账「规则
    声明 element_types 是否全部落空」。抽成 helper 而非在 bridge 硬编码副本，
    加专业 = 加 _ELEMENT_CHECKS 表项（build 带返回注解）即自动跟上，零手动同步。
    不判「类名该不该存在」，只报「主链路实际能喂哪些类」。
    """
    import typing
    types: set[str] = set()
    for entry in _ELEMENT_CHECKS:
        build = entry.get("build")
        if build is None:
            continue
        try:
            ret = typing.get_type_hints(build).get("return")
        except Exception:
            ret = None  # 契约: build 注解解析不了 → 该专业不贡献白名单 (design 降级, 非吞错)
        name = getattr(ret, "__name__", "")
        if name:
            types.add(name)
    return types


# ── 碰撞 / 重复 定位辅助 (机制层, 与 engine.check 同构) ───────────────────

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


# 跨专业碰撞 kind → 中文 (供 _clash_violation 描述可读)。
# 键集合必须与 clash_detection.CLASH_KINDS 同源 (模块加载即对账, 防两处漂移):
# 出图侧忘同步新增 kind 时, 该 kind 的中文 label 静默缺失 (兜底回英文 kind 不崩,
# 但描述会退化成裸 kind), 加载期对账把它变成可见断言而非线上静默。
_CLASH_KIND_CN = {
    "pipe-beam": "排水管穿梁", "pipe-column": "排水管撞柱",
    "duct-beam": "风管穿梁", "duct-column": "风管撞柱",
    "outlet-beam": "插座撞梁", "outlet-column": "插座撞柱",
    "grille-beam": "风口撞梁", "grille-column": "风口撞柱",
}
assert set(_CLASH_KIND_CN) == set(CLASH_KINDS), \
    f"出图侧 _CLASH_KIND_CN 与 clash_detection.CLASH_KINDS 漂移: 差集 " \
    f"{set(_CLASH_KIND_CN) ^ set(CLASH_KINDS)} (两侧碰撞 kind 须同源)"


def _clash_violation(c: dict):
    """把跨专业碰撞结果转成 RuleViolation (与 _collision_violation 同构)。
    rule_id = clash-<kind>, 管线/电气/暖通 不得穿结构梁柱。"""
    from src.rules.src.engine import RuleViolation, ViolationSeverity
    label = _CLASH_KIND_CN.get(c["kind"], c["kind"])
    return RuleViolation(
        rule_id=f"clash-{c['kind']}",
        rule_name="多专业碰撞检查",
        severity=ViolationSeverity.ERROR,
        description=f"{label}碰撞：{c['a_id']} × {c['b_id']} ({c.get('detail', '')})",
        element_id=f"{c['a_id']}×{c['b_id']}",
        code_ref="多专业碰撞检测（管线/电气/暖通 不得穿结构梁柱）",
    )


def _clash_point(raw: dict, c: dict) -> tuple[float, float]:
    """碰撞标记画在哪：取 kind 中「点位类」元素坐标，否则取线段类中点。
    无匹配元素 → (0,0) 兜底，不崩。kind 前缀对应 raw 键:
      pipe→pipes  duct→hvac_ducts  outlet→outlets  grille→hvac_grilles
      beam→structural_beams  column→structural_columns"""
    _KEY = {"pipe": "pipes", "duct": "hvac_ducts", "outlet": "outlets",
            "grille": "hvac_grilles", "beam": "structural_beams",
            "column": "structural_columns"}
    for prefix in c["kind"].split("-"):
        key = _KEY.get(prefix)
        if not key:
            continue
        for it in (raw.get(key) or []):
            eid = it.get("id")
            if eid in (c.get("a_id"), c.get("b_id")):
                if "x" in it and "y" in it:
                    return float(it["x"]), float(it["y"])
                s, e = it.get("start"), it.get("end")
                if s and e:
                    return (float(s[0]) + float(e[0])) / 2.0, (float(s[1]) + float(e[1])) / 2.0
    return 0.0, 0.0


def _duplicate_point(d: dict) -> tuple[float, float]:
    """重复元素标记画在哪: 取 detect_duplicate_elements 透出的 coord (已归一化)。
    coord 缺失 → (0,0) 兜底, 不崩。管线类 coord 是端点排序 4 元 → 取中点。"""
    ck = d.get("coord")
    if not ck:
        return 0.0, 0.0
    # 点位类 coord = [x, y]; 线段类 coord = [x1,y1,x2,y2] (端点排序)
    if len(ck) == 2:
        return float(ck[0]), float(ck[1])
    if len(ck) >= 4:
        return (float(ck[0]) + float(ck[2])) / 2.0, (float(ck[1]) + float(ck[3])) / 2.0
    return float(ck[0]), float(ck[1])
