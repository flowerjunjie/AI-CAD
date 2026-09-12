"""
集成测试 — 户型输入解析 + Agent 端到端流程
使用样本数据验证完整链路
"""
import sys
import os
import json

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def test_parse_json_input():
    """测试从JSON文件解析户型数据"""
    from src.agents.src.nodes.input_parser import parse_json_input

    sample_path = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    result = parse_json_input(sample_path)

    # 验证基本字段
    assert result["project_type"] == "住宅"
    assert "建筑" in result["disciplines"]
    assert result["project_structure"]["building_area"] > 0
    assert len(result["project_structure"]["zones"]) > 0
    assert len(result["task_list"]) > 0

    # 验证任务类型
    task_types = [t["type"] for t in result["task_list"]]
    assert "wall" in task_types
    assert "door" in task_types
    assert "window" in task_types
    assert "dimension" in task_types

    print("✅ test_parse_json_input")


def test_parse_natural_language():
    """测试从自然语言解析户型（LLM调用）"""
    # 需要配置 API（从 .env 读取，不硬编码密钥）
    os.environ.setdefault("AI_CAD_LLM_PROVIDER", "agnes")
    os.environ.setdefault("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    os.environ.setdefault("AGNES_MODEL", "agnes-2.0-flash")

    # 无 API Key 时跳过（不阻塞其他测试）
    if not os.environ.get("AGNES_API_KEY"):
        import pytest
        pytest.skip("AGNES_API_KEY 未配置，跳过 LLM 测试")

    from src.agents.src.nodes.input_parser import parse_natural_language

    result = parse_natural_language("三室一厅住宅，建筑面积约100平米")

    assert result["project_type"] == "住宅"
    assert isinstance(result["task_list"], list)
    print("✅ test_parse_natural_language")


def test_end_to_end_with_sample():
    """端到端测试：样本数据 → Agent执行 → DWG输出"""
    os.environ.setdefault("AI_CAD_LLM_PROVIDER", "agnes")
    os.environ.setdefault("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    os.environ.setdefault("AGNES_MODEL", "agnes-2.0-flash")

    from src.agents.src.graph import run_agent_demo
    from src.agents.src.nodes.input_parser import parse_json_input
    from src.rules.src.engine import get_engine
    from src.agents.src.tools.cad_tools import DXFWriter, Wall, Point

    # 1. 解析样本数据
    sample_path = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    parsed = parse_json_input(sample_path)
    assert len(parsed["task_list"]) > 0, "No tasks generated"

    # 2. 验证规则引擎
    engine = get_engine()
    rules = engine.list_rules()
    assert len(rules) >= 10, "Not enough rules registered"

    # 3. 验证CAD引擎
    writer = DXFWriter()
    writer.new()
    writer.add_wall(Wall(start=Point(0, 0), end=Point(10, 0)))
    assert writer.save("/tmp/e2e_test.dwg"), "DWG save failed"
    print("✅ test_end_to_end_with_sample")


if __name__ == "__main__":
    test_parse_json_input()
    test_parse_natural_language()
    test_end_to_end_with_sample()
    print("\n🎉 All integration tests passed!")
