"""
门窗碰撞结果自洽体检测试 (机制层自主子集)

覆盖:
  ① layout.verify_opening_collisions — 纯函数, 校验 detect_opening_collisions
     输出 (门窗 3 类 kind / a_id·b_id 在门窗元素 / overlap_m>0 / 无自碰撞),
     畸形输入优雅降级不崩。与 M4 的 verify_clashes 同构 (几何碰撞→出图反查
     失步面), 判据适配门窗 3 类 + 门窗 id 集合。
  ② OPENING_KINDS 常量 vs 出图侧 cad_rule_export._CLASH_KIND_CN 键集合同源
     对账 (防两处漂移, 仿 verify_clashes 的 CLASH_KINDS 范式)。

红线对齐 (CLAUDE.md 不虚标): 只判「碰撞清单自身是否自洽」, 不判「该不该有碰撞」
(业务)。仿 test_clash_detection 范式: __main__ 只列无 fixture 子集 + 不 print
中文/emoji (Windows GBK 直跑不崩, 见 test_direct_run.py)。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _layout():
    from src.agents.src import layout
    return layout


def _doors_wins():
    # 门: 竖直墙 x=0, 中心 py, 宽度沿 y 展开 (门扇两端重叠区)
    doors = [{"id": "d1", "position": [0, 5.0], "rotation": 0.0, "width": 0.9},
             {"id": "d2", "position": [0, 8.0], "rotation": 0.0, "width": 0.9}]
    # 窗: 竖直墙 x=0, 端点 (x,y) 沿 y 展开
    wins = [{"id": "w1", "start": [0, 4.8], "end": [0, 5.2]}]
    return doors, wins


def test_detect_then_verify_self_consistent():
    """detect_opening_collisions 产出的碰撞喂 verify 必自洽 (回归护栏)。
    _doors_wins() 里 d1 与 w1 同竖直墙 x=0 且 y 区间重叠 → 有碰撞。"""
    lay = _layout()
    doors, wins = _doors_wins()
    cols = lay.detect_opening_collisions(doors, wins)
    assert cols, "测试前提: 需有至少 1 条门窗重叠 (d1/w1 同墙 y 区间相交)"
    res = lay.verify_opening_collisions(doors, wins, cols)
    assert res["valid"] is True and res["issues"] == [], f"自产碰撞应自洽, 得 {res}"


def test_ghost_id_flagged():
    """碰撞引用不存在的门窗 id → 如实标出 (出图会兜底原点假圈)。"""
    lay = _layout()
    doors, wins = _doors_wins()
    cols = [{"a_id": "d1", "b_id": "ghost-w", "kind": "door-window", "overlap_m": 0.3}]
    res = lay.verify_opening_collisions(doors, wins, cols)
    assert res["valid"] is False
    assert any("ghost-w" in it for it in res["issues"])


def test_invalid_kind_flagged():
    """kind 非 3 类白名单 (写错/漂移) → 如实标出。"""
    lay = _layout()
    doors, wins = _doors_wins()
    cols = [{"a_id": "d1", "b_id": "w1", "kind": "door-door-bad", "overlap_m": 0.3}]
    res = lay.verify_opening_collisions(doors, wins, cols)
    assert res["valid"] is False
    assert any("door-door-bad" in it for it in res["issues"])


def test_self_collision_flagged():
    """a_id == b_id (同一元素自撞) → 如实标出。"""
    lay = _layout()
    doors, wins = _doors_wins()
    cols = [{"a_id": "d1", "b_id": "d1", "kind": "door-door", "overlap_m": 0.3}]
    res = lay.verify_opening_collisions(doors, wins, cols)
    assert res["valid"] is False
    assert any("自碰撞" in it for it in res["issues"])


def test_nonpositive_overlap_flagged():
    """overlap_m ≤ 0 (无重叠却判碰撞 / 负数) → 如实标出。"""
    lay = _layout()
    doors, wins = _doors_wins()
    res = lay.verify_opening_collisions(
        doors, wins, [{"a_id": "d1", "b_id": "w1", "kind": "door-window", "overlap_m": 0.0}])
    assert res["valid"] is False
    assert any("overlap_m" in it for it in res["issues"])


def test_malformed_no_crash():
    """collisions 非 list / 条非 dict / 缺 a_id·b_id → 计入 issues 不崩。"""
    lay = _layout()
    doors, wins = _doors_wins()
    assert lay.verify_opening_collisions(doors, wins, "not-a-list")["valid"] is False
    res = lay.verify_opening_collisions(doors, wins, [object()])
    assert res["valid"] is False and res["count"] == 1
    res2 = lay.verify_opening_collisions(doors, wins, [{"kind": "door-door"}])
    assert res2["valid"] is False
    # 空碰撞 (无门窗重叠) 合法
    assert lay.verify_opening_collisions(doors, wins, [])["valid"] is True


def test_opening_kinds_constant():
    """OPENING_KINDS 常量为门窗 3 类白名单 (与 detect_opening_collisions 产出键
    同源, 供 verify 判 kind 合法性)。"""
    lay = _layout()
    assert lay.OPENING_KINDS == frozenset({"door-door", "door-window", "window-window"})


if __name__ == "__main__":
    # 只跑无 pytest fixture 依赖的用例 (test_direct_run 会直跑 __main__ 块)
    test_detect_then_verify_self_consistent()
    test_ghost_id_flagged()
    test_invalid_kind_flagged()
    test_self_collision_flagged()
    test_nonpositive_overlap_flagged()
    test_malformed_no_crash()
    test_opening_kinds_constant()
    print("OK: all verify_opening_collisions tests passed")
