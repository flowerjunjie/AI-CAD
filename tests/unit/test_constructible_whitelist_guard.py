"""
注解派生类白名单完整性护栏 (M1 机制层自主子集, 防搬家丢类)

病根: constructible_element_types() 靠 typing.get_type_hints 取各 _build_* 的
返回注解 (-> Door 等) 派生「主链路可喂类名白名单」。这类「靠反射取注解」的
代码是**搬家高危点** — 函数搬到新模块后注解在**新模块作用域**解析, 若某
_build_* 的注解类没跟 import 一起搬, get_type_hints 会静默取不到 (except 吞),
白名单**静默少一个类**而全量测试照绿 (test_dispatch_coverage 锁的是「规则
命中 dispatch」侧, 感知不到白名单少类)。

本护栏锁「白名单本身完整」— 把 11 个专业的元素类名钉死, 防未来再次搬
_build_* 或加专业时注解链断掉。跟 test_dispatch_coverage 正交 (那条管规则侧)。
__main__ 直跑护栏: 纯函数 + import, 无 fixture, ASCII print。
范式照 test_dispatch_coverage.py / test_intent_structure_guard.py。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

# 11 个专业的元素类名 (各 _build_* 的返回注解)。新增专业 = 加 _ELEMENT_CHECKS
# 表项, 白名单自动跟上 (constructible_element_types 随表派生), 本护栏同步加类名。
_EXPECTED_TYPES = {
    "Door", "Window", "Room",
    "PlumbingPipe",
    "ElectricalOutlet", "ElectricalSwitch",
    "HvacDuct", "HvacUnit", "HvacGrille",
    "StructuralBeam", "StructuralColumn",
}


def test_constructible_whitelist_complete():
    """constructible_element_types 必含 11 个专业类 (防搬家/加专业丢注解)。"""
    from src.agents.src.nodes.cad_rule_export import constructible_element_types
    types = constructible_element_types()
    missing = _EXPECTED_TYPES - types
    assert not missing, \
        f"注解派生白名单丢了 {sorted(missing)} — 检查对应 _build_* 的返回注解 " \
        f"是否跟 import 一起搬齐 (get_type_hints 取不到会静默丢类)"


def test_constructible_whitelist_module_source_stable():
    """11 类白名单须来自 _ELEMENT_CHECKS 的 build 注解, 且分发表未退化。

    反转假设护栏: 若有人把 _ELEMENT_CHECKS 清空/删 build 键, constructible
    会返回空集 — 本测试比 test_constructible_whitelist_complete 更严, 还锁
    分发表本身没退化 (build 键非空)。"""
    from src.agents.src.nodes.cad_rule_export import (
        _ELEMENT_CHECKS, constructible_element_types,
    )
    # 分发表必须非空且每项 build 键在 (注解来源)
    assert _ELEMENT_CHECKS, "_ELEMENT_CHECKS 分发表不可为空 (机制退化)"
    assert all(e.get("build") is not None for e in _ELEMENT_CHECKS), \
        "每个分发表项须有 build (annotation 白名单来源), 空 build 项会丢类"
    # 白名单非空且 ≥ 11 类 (允许未来加专业扩多, 不许缩)
    assert len(constructible_element_types()) >= len(_EXPECTED_TYPES), \
        "constructible 白名单缩到 11 类以下 — 分发表或注解链断了"


if __name__ == "__main__":
    fns = [
        test_constructible_whitelist_complete,
        test_constructible_whitelist_module_source_stable,
    ]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"__main__ {len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
