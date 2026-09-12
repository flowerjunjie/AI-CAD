#!/usr/bin/env python3
"""
AI-CAD CLI — 命令行交互接口
支持: 样本数据验证、规则查询、Agent演示
"""
import sys
import os
import json
import argparse

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def cmd_rules(args):
    """列出所有规则"""
    # Import all rule modules to trigger decorators
    import src.rules.src.residential.doors as _rd
    import src.rules.src.residential.windows as _rw
    import src.rules.src.residential.corridors as _rc
    import src.rules.src.residential.rooms as _rr
    import src.rules.src.residential.areas as _ra
    import src.rules.src.fire_safety.corridors as _fc
    import src.rules.src.accessibility.ramps as _ar

    from src.rules.src.engine import get_engine

    engine = get_engine()
    rules = engine.list_rules()

    print(f"\n{'='*60}")
    print(f"  AI-CAD 规范规则库 ({len(rules)} 条)")
    print(f"{'='*60}\n")

    for rule in rules:
        severity = rule.severity.value.upper()
        print(f"  [{severity:5}] {rule.rule_id}")
        print(f"         {rule.name}")
        print(f"         依据: {rule.code_ref}\n")


def cmd_sample(args):
    """运行样本数据测试"""
    import os
    os.environ.setdefault("AI_CAD_LLM_PROVIDER", "agnes")
    os.environ.setdefault("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    os.environ.setdefault("AGNES_MODEL", "agnes-2.0-flash")

    from src.agents.src.nodes.input_parser import parse_json_input
    from src.agents.src.graph import run_agent_demo

    sample_path = os.path.join(project_root, "data", "sample", "residential_100sqm.json")

    print(f"\n{'='*60}")
    print(f"  样本测试: {sample_path}")
    print(f"{'='*60}\n")

    # 解析样本
    parsed = parse_json_input(sample_path)
    print(f"项目类型: {parsed['project_type']}")
    print(f"功能区: {len(parsed['project_structure']['zones'])} 个")
    print(f"任务数: {len(parsed['task_list'])}\n")

    # 运行Agent
    print("运行 Agent 流程...")
    result = run_agent_demo()

    print(f"\n结果:")
    print(f"  DWG输出: {result.get('final_dwg_path')}")
    print(f"  规范违规: {len(result.get('rule_violations', []))} 条")
    for v in result.get('rule_violations', []):
        print(f"    - {v['rule_name']}: {v['description']}")

    print(f"\n材料表:")
    for table in result.get('material_tables', []):
        for category, items in table.items():
            if isinstance(items, list):
                for item in items:
                    print(f"  {category}: {item.get('type', '')} x{item.get('count', 0)}")

    print(f"\n{'='*60}")
    print(f"  测试完成!")
    print(f"{'='*60}\n")


def cmd_demo(args):
    """运行完整Demo"""
    os.environ.setdefault("AI_CAD_LLM_PROVIDER", "agnes")
    os.environ.setdefault("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    os.environ.setdefault("AGNES_MODEL", "agnes-2.0-flash")

    from src.agents.src.graph import run_agent_demo

    print(f"\n{'='*60}")
    print(f"  AI-CAD Agent Demo")
    print(f"{'='*60}\n")

    result = run_agent_demo()

    print(f"项目类型: {result.get('project_type')}")
    print(f"任务数: {len(result.get('task_list', []))}")
    print(f"规范违规: {len(result.get('rule_violations', []))} 条")
    print(f"DWG输出: {result.get('final_dwg_path')}")
    print()


def cmd_test(args):
    """运行测试套件"""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=project_root,
        capture_output=True,
        text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
    sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(
        prog="ai-cad",
        description="AI辅助施工图深化系统 CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # rules 命令
    rules_parser = subparsers.add_parser("rules", help="列出所有规范规则")

    # sample 命令
    sample_parser = subparsers.add_parser("sample", help="运行样本数据测试")

    # demo 命令
    demo_parser = subparsers.add_parser("demo", help="运行Agent演示")

    # test 命令
    test_parser = subparsers.add_parser("test", help="运行测试套件")

    args = parser.parse_args()

    if args.command == "rules":
        cmd_rules(args)
    elif args.command == "sample":
        cmd_sample(args)
    elif args.command == "demo":
        cmd_demo(args)
    elif args.command == "test":
        cmd_test(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
