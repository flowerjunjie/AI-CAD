#!/usr/bin/env python
"""
M1 数值回填 CLI — 把「专家定值 → default.json → 点亮占位卡」做成一行命令。

用法:
  # 查看当前所有 confirmed 状态 (默认, 不写盘)
  python scripts/backfill_rule_values.py

  # 回填某条规则的 confirmed=true + confidence + 备注 (写盘, 带备份)
  python scripts/backfill_rule_values.py --rule structural-beam-min-height \
      --confirmed true --confidence high --note "结构专家背书: 梁高下限 300mm (GB 50010 构造要求)"

  # 回填参数值 (改 param_defaults, 零代码, 专家改 JSON 即可)
  python scripts/backfill_rule_values.py --rule clash-tolerance-range \
      --param clash_tolerance_m=0.25 --confirmed true

诚实边界 (不虚标, 呼应 CLAUDE.md):
  - 写盘前自动备份 default.json → default.json.bak (可回滚)
  - 未指定 --rule → 只读查看, 不写盘
  - 写盘后提示「跑 bridge /api/rules 验证点亮」, 不冒称已点亮 (点亮是前端按 confirmed 判定的)
  - 参数值必须能 JSON 序列化 (数值/字符串/布尔), 非法值拒绝写盘
"""
import argparse
import json
import os
import shutil
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_JSON = os.path.join(project_root, "src", "rules", "rules", "default.json")


def _parse_value(s: str):
    """把 CLI 字符串解析成 JSON 可序列化值 (数值/布尔/字符串)。"""
    if s in ("true", "false"):
        return s == "true"
    for cast in (int, float):
        try:
            return cast(s)
        except ValueError:
            pass
    return s  # 兜底字符串


def show_rules(path: str) -> int:
    """只读: 列出所有规则 + confirmed 状态 + param_defaults。"""
    with open(path, encoding="utf-8") as fh:
        rules = json.load(fh)["rules"]
    print(f"{'rule_id':<44} {'confirmed':<10} {'confidence':<10} param_defaults")
    print("-" * 100)
    for r in rules:
        pd = r.get("param_defaults", {})
        pd_str = ", ".join(f"{k}={v}" for k, v in pd.items()) if pd else "-"
        print(f"{r['rule_id']:<44} {str(r.get('confirmed', False)):<10} "
              f"{str(r.get('confidence', '-')):<10} {pd_str}")
    return 0


def backfill(path: str, rule_id: str, confirmed: bool | None,
             confidence: str | None, note: str | None,
             params: list[tuple[str, str]] | None) -> int:
    """写盘回填: 改 specified rule 的 confirmed/confidence/confirm_note/param_defaults。"""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    rule = next((r for r in data["rules"] if r.get("rule_id") == rule_id), None)
    if rule is None:
        print(f"未找到规则: {rule_id}", file=sys.stderr)
        print("可用规则:", file=sys.stderr)
        for r in data["rules"]:
            print(f"  {r['rule_id']}", file=sys.stderr)
        return 1

    # 备份 (可回滚)
    bak = path + ".bak"
    shutil.copy(path, bak)
    print(f"备份: {bak}")

    if confirmed is not None:
        rule["confirmed"] = confirmed
    if confidence is not None:
        rule["confidence"] = confidence
    if note is not None:
        rule["confirm_note"] = note
    if params:
        pd = rule.setdefault("param_defaults", {})
        for key, raw_val in params:
            val = _parse_value(raw_val)
            pd[key] = val
            # 同步 params (若存在同名键) — 保持 params 与 param_defaults 一致
            if key in rule.get("params", {}):
                rule["params"][key] = val

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"已回填: {rule_id}")
    print(f"  confirmed={rule.get('confirmed')} confidence={rule.get('confidence')}")
    if "param_defaults" in rule:
        print(f"  param_defaults={rule['param_defaults']}")
    print(f"\n下一步: 起桥 curl /api/rules 验证点亮 (前端按 confirmed 判定占位卡)")
    print(f"  python start_gui.py && curl http://127.0.0.1:<port>/api/rules")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="M1 数值回填 CLI: 专家定值 → default.json → 点亮占位卡 (一行命令)")
    parser.add_argument("--rule", "-r", help="要回填的 rule_id (缺省 = 只读查看)")
    parser.add_argument("--confirmed", choices=["true", "false"],
                        help="回填 confirmed 标志 (true=已确认, false=占位)")
    parser.add_argument("--confidence", choices=["low", "medium", "high"],
                        help="回填 confidence (不虚标: 几何默认=medium, 专家背书=high)")
    parser.add_argument("--note", help="回填 confirm_note (专家备注, 写明依据条文)")
    parser.add_argument("--param", action="append", default=[],
                        metavar="KEY=VALUE",
                        help="回填 param_defaults (可多次, 如 --param clash_tolerance_m=0.25)")
    parser.add_argument("--path", default=DEFAULT_JSON,
                        help=f"default.json 路径 (默认 {DEFAULT_JSON})")
    args = parser.parse_args()

    if not args.rule:
        return show_rules(args.path)
    return backfill(args.path, args.rule,
                    args.confirmed == "true" if args.confirmed else None,
                    args.confidence, args.note,
                    [tuple(p.split("=", 1)) for p in args.param] if args.param else None)


if __name__ == "__main__":
    sys.exit(main())
