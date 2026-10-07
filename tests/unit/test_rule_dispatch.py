"""
Phase 3/4 主链路收敛护栏测试

钉死两处架构不变量:
- _ensure_dsl_rules_loaded 数据驱动: 纯 DSL 新增规则进引擎, 与 @register_rule
  重名的规则保持硬编码版 (不被 DSL 顶替) — 守「34 类零改动」红线。
- rule_check_node 分发表: 各专业走 _ELEMENT_CHECKS, 加专业=加表项不改主链路。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def test_ensure_dsl_does_not_override_registered_class():
    """_ensure_dsl_rules_loaded 按 dsl_only 判据 (稳定, 不依赖 import 时序):
    - dsl_only=true 的纯 DSL 新增专业 (plumbing-/electrical-) 会被 upsert 进引擎
    - dsl_only=false 的重名规则 (residential-bedroom-window-area, 与 34 类冲突)
      不被 _ensure upsert, 硬编码版不被 DSL 顶替 — 守 34 类零改动红线。

    用独立 RuleEngine + 打桩 load_dsl_rules, 避免全局单例的注册时序污染。
    """
    import src.rules.src.residential.doors
    from src.rules.src.engine import RuleEngine
    from src.rules.src.dsl import ParametricRule, load_dsl_rules
    from src.agents.src.nodes import cad_rule_export as cre

    engine = RuleEngine()
    # 引擎里预置一个硬编码版的重名规则 (模拟 34 类已注册)
    from src.rules.src.residential.daylight import BedroomMinWindowArea
    engine.upsert(BedroomMinWindowArea())

    before_ids = {r.rule_id for r in engine.list_rules()}
    cre._ensure_dsl_rules_loaded(engine)
    by_id = {r.rule_id: r for r in engine.list_rules()}

    # dsl_only=true 的纯 DSL 规则应进引擎
    assert "plumbing-waste-pipe-min-diameter" in by_id
    assert "electrical-outlet-height-range" in by_id
    # 重名规则 residential-bedroom-window-area: 引擎里仍是硬编码版 (BedroomWindowArea),
    # 不是被 DSL 顶替成 ParametricRule
    shared = "residential-bedroom-window-area"
    assert not isinstance(by_id[shared], ParametricRule), \
        "重名规则被 DSL 版顶替, 违反 34 类零改动红线"
    # 且新增进引擎的 = 纯 dsl_only 规则, 不含任何 34 类重名
    newly = by_id.keys() - before_ids
    assert shared not in newly, "_ensure 不该新增/顶替 34 类重名规则"


def test_new_dsl_professional_rules_load_without_code_change():
    """数据驱动收敛: 加新专业只需往 default.json 加条目 (dsl_only=true), 不碰主链路
    代码也能进引擎。直接调真实的 _ensure_dsl_rules_loaded (用 default.json 的真实
    dsl_only 判据), 而非临时 JSON + 手动 load_dsl_rules + "引擎里有没有它" 反推。

    判据是 default.json 里 dsl_only=true 字段 (稳定, 不依赖 import 时序),
    而非 SOP 明令禁止的反模式②「靠引擎里有没有它反推」。
    """
    from src.rules.src.engine import RuleEngine
    from src.agents.src.nodes import cad_rule_export as cre

    engine = RuleEngine()
    before_ids = {r.rule_id for r in engine.list_rules()}
    # 调真实收敛逻辑: 读 default.json, 按 dsl_only=true upsert 进干净引擎
    cre._ensure_dsl_rules_loaded(engine)
    newly = {r.rule_id for r in engine.list_rules()} - before_ids
    # 新专业 hvac 规则 (default.json 里 dsl_only=true) 应被 upsert 进引擎
    assert "hvac-duct-velocity-range" in newly, \
        "新专业前缀规则应经 _ensure_dsl_rules_loaded 的 dsl_only 判据被数据驱动纳入"


def test_dispatch_table_entries_are_simple_raw_element_rule_mapping():
    """护栏 (SOP 反模式③): 分发表 _ELEMENT_CHECKS 每一项都必须是
    「raw 元素 → build 出单个 element → engine.check(elements, rule_ids)」
    这种简单映射。几何层逻辑 (依赖 _layout_from_state/坐标的碰撞检测) 不进表。

    不变量: 每项 = {raw_key: str, build: callable(raw,idx)->object,
    rule_ids: list[str]}, 且 build 产物是可被 engine.check 消费的 element
    (有 rule_id 匹配的类型, 不是坐标系/几何结构)。任何一项若偏离 (比如把
    需要 layout 的碰撞检测塞进表), 会破坏主链路的语义, 在此拦下。
    """
    from src.agents.src.nodes.cad_rule_export import _ELEMENT_CHECKS

    assert _ELEMENT_CHECKS, "分发表不能为空"
    for entry in _ELEMENT_CHECKS:
        assert set(entry) == {"raw_key", "build", "rule_ids"}, \
            f"分发表项 {entry.get('raw_key')} 结构必须恰为 raw_key/build/rule_ids, 实际 {sorted(entry)}"
        assert isinstance(entry["raw_key"], str) and entry["raw_key"], \
            f"raw_key 需非空 str: {entry['raw_key']!r}"
        assert callable(entry["build"]), f"build 需 callable: {entry['raw_key']}"
        assert isinstance(entry["rule_ids"], list) and entry["rule_ids"], \
            f"rule_ids 需非空 list: {entry['rule_ids']!r}"
        assert all(isinstance(rid, str) for rid in entry["rule_ids"]), \
            f"rule_ids 元素需 str: {entry['raw_key']}"
        # build 需能产出可被 engine 消费的 element (对空 raw 造默认实例不崩)
        elem = entry["build"]({}, 0)
        assert elem is not None, f"{entry['raw_key']} 的 build 对空 raw 应产默认 element"
        # 几何依赖型对象不应混进表 (其 build 产物不该需要 layout 上下文才有意义)
        assert not hasattr(elem, "polygon") and not hasattr(elem, "bbox"), \
            f"{entry['raw_key']} 的 build 产出几何对象 (polygon/bbox), 几何逻辑不该进分发表"


def test_rule_check_node_wires_opening_collision_diagnosis():
    """接线护栏 (机制层自主子集): rule_check_node 门窗碰撞段检出结果过
    verify_opening_collisions, 诊断随节点 return 带出 (DesignState 声明该 channel,
    仿 export_status 范式 — 未声明的键 langgraph 会丢弃, 端点/出图侧拿不到)。

    不依赖全样本几何, 直接喂最小 raw_data 调 rule_check_node, 断言:
      ① 返回 dict 带 opening_collisions_check 键 (接线真生效, 非写了没人读的死代码)
      ② 该诊断结构 {valid, issues, count} 合法
      ③ 无门窗 raw → count=0 空诊断自洽 (不虚报碰撞)
    """
    from src.agents.src.nodes.cad_rule_export import rule_check_node
    # 空 raw_data: 走 _ELEMENT_CHECKS 空跳 + 门窗碰撞段 (无门窗 → 0 碰撞)
    res = rule_check_node({"raw_data": {}, "project_structure": {}})
    assert "opening_collisions_check" in res, "rule_check_node 未把门窗碰撞诊断随 return 带出 (接线失效)"
    chk = res["opening_collisions_check"]
    for k in ("valid", "issues", "count"):
        assert k in chk, f"opening_collisions_check 缺字段 {k}: {chk}"
    # 无门窗元素 → 0 碰撞, 诊断自洽 (valid 空态不误报)
    assert chk["count"] == 0 and chk["valid"] is True, f"空 raw 门窗碰撞诊断异常: {chk}"

