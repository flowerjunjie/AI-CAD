"""
Agent 节点 — 意图理解 + 方案结构化
接入 LLM 和 RAG 知识库
"""
from typing import Any
import json
import os

# Import rule modules to register rules
import src.rules.src.residential.doors as _doors
import src.rules.src.residential.windows as _windows
import src.rules.src.residential.corridors as _corridors
import src.rules.src.residential.rooms as _rooms

from src.agents.src.tools.llm_adapter import LLMFactory, ChatMessage, BaseLLMAdapter
from src.agents.src.tools.rag_tools import RAGKnowledgeBase
from src.rules.src.engine import get_engine


def _get_llm() -> BaseLLMAdapter | None:
    """获取 LLM 实例（从环境变量或配置）"""
    try:
        provider = os.getenv("AI_CAD_LLM_PROVIDER", "minimax")
        api_key = os.getenv(f"{provider.upper()}_API_KEY", "")
        if api_key:
            return LLMFactory.create(provider, api_key=api_key)
    except Exception:
        pass
    return None


def _call_llm(messages: list[ChatMessage], system_prompt: str, max_retries: int = 2) -> str:
    """调用 LLM 并返回文本结果"""
    llm = _get_llm()
    if not llm:
        return ""

    full_messages = [ChatMessage(role="system", content=system_prompt)] + messages
    for attempt in range(max_retries):
        response = llm.chat(full_messages)
        if response.text:
            return response.text
    return ""


def intent_understanding_node(state: dict) -> dict:
    """
    意图理解 Agent：解析设计师输入，确定项目类型和专业需求

    输入: project_input (str) - 自然语言描述
    输出: project_type, disciplines, project_structure (partial)
    """
    system_prompt = """你是AI-CAD系统的意图理解专家。
你的任务是从设计师的自然语言输入中提取关键项目信息。
输出必须是JSON格式，包含以下字段：
- project_type: 项目类型（住宅/公建/商业/工业）
- disciplines: 需要处理的专业列表（建筑/结构/给排水/电气/暖通）
- building_area: 预估建筑面积（平方米）
- floors: 层数
- zones: 功能分区列表（每个包含name和area）
- special_requirements: 特殊要求（如有）

只输出JSON，不要其他内容。"""

    user_message = ChatMessage(
        role="user",
        content=f"请分析以下设计方案并提取关键信息：\n{state.get('project_input', '')}"
    )

    result = _call_llm([user_message], system_prompt)
    if result:
        try:
            parsed = json.loads(result)
            return {
                "project_type": parsed.get("project_type", "住宅"),
                "disciplines": parsed.get("disciplines", ["建筑"]),
                "project_structure": {
                    "building_area": parsed.get("building_area", 0),
                    "floors": parsed.get("floors", 1),
                    "zones": parsed.get("zones", []),
                    "special_requirements": parsed.get("special_requirements", []),
                },
            }
        except json.JSONDecodeError:
            pass

    # Fallback: 默认住宅建筑
    return {
        "project_type": "住宅",
        "disciplines": ["建筑"],
        "project_structure": {"building_area": 0, "floors": 1, "zones": []},
    }


def structure_design_node(state: dict) -> dict:
    """
    方案结构化 Agent：基于LLM解析结果，结合RAG规范库，
    生成分层详细的结构化设计方案
    """
    rag = RAGKnowledgeBase()
    rag.initialize()

    # 查询相关规范
    project_type = state.get("project_type", "住宅")
    queries = {
        "住宅": ["住宅设计规范 门宽", "住宅设计规范 窗台高度", "住宅设计规范 走廊宽度"],
        "公建": ["公共建筑节能设计标准", "建筑设计防火规范"],
    }
    relevant_codes = []
    for query in queries.get(project_type, queries["住宅"]):
        results = rag.search(query, top_k=2)
        relevant_codes.extend(results)

    # 去重
    seen = set()
    unique_codes = []
    for r in relevant_codes:
        if r["id"] not in seen:
            seen.add(r["id"])
            unique_codes.append(r)

    # 构建结构化方案
    base_structure = state.get("project_structure", {})
    zones = base_structure.get("zones", [])

    # 如果没有LLM解析的分区，使用默认分区
    if not zones:
        zones = [
            {"name": "客厅", "area": 20, "type": "living"},
            {"name": "卧室1", "area": 12, "type": "bedroom"},
            {"name": "卧室2", "area": 10, "type": "bedroom"},
            {"name": "厨房", "area": 6, "type": "kitchen"},
            {"name": "卫生间", "area": 4, "type": "bathroom"},
        ]

    structured = {
        "project_type": project_type,
        "disciplines": state.get("disciplines", ["建筑"]),
        "building_area": sum(z.get("area", 0) for z in zones),
        "floors": base_structure.get("floors", 1),
        "zones": zones,
        "applicable_codes": unique_codes[:5],  # 最多5条相关规范
    }

    return {
        "project_structure": structured,
        "task_list": _generate_task_list(structured),
    }


def _generate_task_list(structure: dict) -> list[dict]:
    """根据结构化方案生成CAD操作任务列表"""
    tasks = []
    zones = structure.get("zones", [])

    # 外墙任务
    tasks.append({
        "id": "wall-outer",
        "type": "wall",
        "category": "structural",
        "params": {"thickness": 0.24, "material": "承重墙"},
        "description": "绘制外墙",
    })

    # 内墙任务
    tasks.append({
        "id": "wall-inner",
        "type": "wall",
        "category": "structural",
        "params": {"thickness": 0.12, "material": "隔墙"},
        "description": "绘制内墙",
    })

    # 门窗任务
    door_count = len(zones) + 1  # 每个房间一个门 + 一个户门
    tasks.append({
        "id": "door-entrance",
        "type": "door",
        "category": "opening",
        "params": {"width": 1.0, "type": "entrance"},
        "description": "插入户门",
    })
    for i, zone in enumerate(zones):
        tasks.append({
            "id": f"door-room-{i}",
            "type": "door",
            "category": "opening",
            "params": {"width": 0.9, "type": zone.get("type", "interior")},
            "description": f"插入{zone.get('name', '房间')}门",
        })

    # 窗户任务
    tasks.append({
        "id": "window-all",
        "type": "window",
        "category": "opening",
        "params": {"sill_height": 0.9},
        "description": "插入窗户",
    })

    # 标注任务
    tasks.append({
        "id": "dim-axis",
        "type": "dimension",
        "category": "annotation",
        "params": {"style": "axis"},
        "description": "轴线标注",
    })
    tasks.append({
        "id": "dim-opening",
        "type": "dimension",
        "category": "annotation",
        "params": {"style": "opening"},
        "description": "洞口标注",
    })

    return tasks
