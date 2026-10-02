"""
M1 数值回填 CLI 单元测试 (scripts/backfill_rule_values.py)

仿 test_dwg_layer_scan 纯函数范式: 覆盖 ① 只读查看 ② 写盘回填 (confirmed/confidence/note/param)
③ 备份回滚 ④ 未找到规则报错 ⑤ 参数值解析 (数值/布尔/字符串)。
用 tmp_path 隔离写盘, 不污染真实 default.json。
__main__ 只列无 fixture 子集 (全部无 fixture, 可直跑)。
"""
import json
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "scripts"))

import backfill_rule_values as bfv


def _mk_default(tmp_path: str, rules: list) -> str:
    """造一份最小 default.json (放 tmp_path), 返回路径。"""
    path = os.path.join(tmp_path, "default.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"rules": rules}, fh, ensure_ascii=False, indent=2)
    return path


def test_show_rules_lists_all(tmp_path):
    """无 --rule → 只读查看, 列出全部规则 + confirmed 状态, 不写盘。"""
    path = _mk_default(tmp_path, [
        {"rule_id": "r1", "confirmed": True, "confidence": "high"},
        {"rule_id": "r2", "confirmed": False, "confidence": "low"},
    ])
    rc = bfv.show_rules(path)
    assert rc == 0
    # 只读不写: default.json 内容不变 (无 .bak 产生)
    assert not os.path.exists(path + ".bak"), "只读查看不该产生备份"
    print("PASS test_show_rules_lists_all")


def test_backfill_confirmed_writes_and_backs_up(tmp_path):
    """--confirmed true → 写盘 + 自动备份 (.bak 可回滚)。"""
    path = _mk_default(tmp_path, [
        {"rule_id": "r1", "confirmed": False, "confidence": "low"},
    ])
    rc = bfv.backfill(path, "r1", confirmed=True, confidence="high",
                      note="专家背书", params=None)
    assert rc == 0
    # 写盘验证
    with open(path, encoding="utf-8") as fh:
        rules = json.load(fh)["rules"]
    assert rules[0]["confirmed"] is True
    assert rules[0]["confidence"] == "high"
    assert rules[0]["confirm_note"] == "专家背书"
    # 备份存在 (可回滚)
    assert os.path.exists(path + ".bak"), "写盘前应自动备份"
    print("PASS test_backfill_confirmed_writes_and_backs_up")


def test_backfill_param_updates_defaults(tmp_path):
    """--param key=val → 改 param_defaults (数值/布尔解析, 零代码回填)。"""
    path = _mk_default(tmp_path, [
        {"rule_id": "r1", "param_defaults": {"x": 1}, "params": {"x": 1}},
    ])
    rc = bfv.backfill(path, "r1", confirmed=None, confidence=None,
                      note=None, params=[("x", "2.5"), ("flag", "true")])
    assert rc == 0
    with open(path, encoding="utf-8") as fh:
        r1 = json.load(fh)["rules"][0]
    assert r1["param_defaults"]["x"] == 2.5, f"应解析为 float, 实际 {r1['param_defaults']['x']}"
    assert r1["param_defaults"]["flag"] is True
    # params 同步 (同名键)
    assert r1["params"]["x"] == 2.5, "params 应同步 param_defaults"
    print("PASS test_backfill_param_updates_defaults")


def test_backfill_unknown_rule_returns_1(tmp_path):
    """未找到规则 → 返回 1 + stderr 列可用规则, 不写盘。"""
    path = _mk_default(tmp_path, [{"rule_id": "r1"}])
    rc = bfv.backfill(path, "no-such-rule", confirmed=True, confidence=None,
                      note=None, params=None)
    assert rc == 1, f"未找到规则应返回 1, 实际 {rc}"
    # 不写盘: 无 .bak
    assert not os.path.exists(path + ".bak")
    print("PASS test_backfill_unknown_rule_returns_1")


def test_parse_value_types():
    """_parse_value: true/false→bool, 数字→int/float, 其他→str。"""
    assert bfv._parse_value("true") is True
    assert bfv._parse_value("false") is False
    assert bfv._parse_value("42") == 42 and isinstance(bfv._parse_value("42"), int)
    assert bfv._parse_value("0.15") == 0.15 and isinstance(bfv._parse_value("0.15"), float)
    assert bfv._parse_value("GB 50010") == "GB 50010"  # 字符串兜底
    print("PASS test_parse_value_types")


def test_backfill_revert_from_bak(tmp_path):
    """备份回滚: 写盘后从 .bak 恢复 → 原 confirmed 值回到位。"""
    path = _mk_default(tmp_path, [
        {"rule_id": "r1", "confirmed": False, "confidence": "low"},
    ])
    bfv.backfill(path, "r1", confirmed=True, confidence="high", note=None, params=None)
    # 模拟回滚: 用 .bak 覆盖回
    with open(path + ".bak", encoding="utf-8") as fh:
        original = json.load(fh)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(original, fh, ensure_ascii=False, indent=2)
    with open(path, encoding="utf-8") as fh:
        assert json.load(fh)["rules"][0]["confirmed"] is False, "回滚后应回到 False"
    print("PASS test_backfill_revert_from_bak")


if __name__ == "__main__":
    # 无 fixture 子集: 每个子测独立临时目录 (避免 .bak 残留跨子测误判)
    import tempfile
    test_show_rules_lists_all(tempfile.mkdtemp(prefix="bfv-"))
    test_backfill_confirmed_writes_and_backs_up(tempfile.mkdtemp(prefix="bfv-"))
    test_backfill_param_updates_defaults(tempfile.mkdtemp(prefix="bfv-"))
    test_backfill_unknown_rule_returns_1(tempfile.mkdtemp(prefix="bfv-"))
    test_backfill_revert_from_bak(tempfile.mkdtemp(prefix="bfv-"))
    test_parse_value_types()
    print("OK: all backfill_rule_values CLI tests passed")
