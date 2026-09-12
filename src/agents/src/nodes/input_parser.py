"""
户型输入解析器 — 将设计输入转换为 Agent 任务
支持: 自然语言 → LLM结构化, JSON文件 → 直接解析
"""
import json
import os
from typing import Optional


def parse_json_input(file_path: str) -> dict:
    """从JSON文件解析户型数据"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    zones = data.get('zones', [])
    doors = data.get('doors', [])
    windows = data.get('windows', [])

    # 构建任务列表
    tasks = []

    # 1. 外墙任务
    outer_walls = [w for w in data.get('walls', []) if w.get('type') == 'outer']
    if outer_walls:
        tasks.append({
            'id': 'wall-outer',
            'type': 'wall',
            'category': 'structural',
            'params': {'thickness': outer_walls[0].get('thickness_m', 0.24), 'material': '承重墙'},
            'description': '绘制外墙',
        })

    # 2. 内墙任务
    inner_walls = [w for w in data.get('walls', []) if w.get('type') == 'inner']
    if inner_walls:
        tasks.append({
            'id': 'wall-inner',
            'type': 'wall',
            'category': 'structural',
            'params': {'thickness': inner_walls[0].get('thickness_m', 0.12), 'material': '隔墙'},
            'description': '绘制内墙',
        })

    # 3. 户门（用门真实 id，与 place_doors_on_walls 输出对齐）
    entrance_doors = [d for d in doors if d.get('type') == 'entrance']
    if entrance_doors:
        d = entrance_doors[0]
        tasks.append({
            'id': d.get('id', 'door-entrance'),
            'type': 'door',
            'category': 'opening',
            'params': {'width': d.get('width_m', 1.0), 'type': 'entrance'},
            'description': f"插入户门 (宽{d.get('width_m', 1.0)}m)",
        })

    # 4. 室内门（用门真实 id，与 place_doors_on_walls 输出对齐，避免序号错位）
    for door in doors:
        if door.get('type') in ('interior', 'bathroom'):
            tasks.append({
                'id': door.get('id', f"door-room-{len(tasks)}"),
                'type': 'door',
                'category': 'opening',
                'params': {'width': door.get('width_m', 0.9), 'type': door.get('type', 'interior')},
                'description': f"插入{door.get('location', '房间')}门 (宽{door.get('width_m', 0.9)}m)",
            })

    # 5. 窗户
    if windows:
        tasks.append({
            'id': 'window-all',
            'type': 'window',
            'category': 'opening',
            'params': {'sill_height': windows[0].get('sill_height_m', 0.9)},
            'description': f"插入窗户 (共{len(windows)}个)",
        })

    # 6. 标注
    tasks.append({'id': 'dim-axis', 'type': 'dimension', 'category': 'annotation',
                  'params': {'style': 'axis'}, 'description': '轴线标注'})
    tasks.append({'id': 'dim-opening', 'type': 'dimension', 'category': 'annotation',
                  'params': {'style': 'opening'}, 'description': '洞口标注'})

    return {
        'project_type': data.get('project_type', '住宅'),
        'disciplines': data.get('disciplines', ['建筑']),
        'project_structure': {
            'building_area': data.get('building_area', sum(z.get('area', 0) for z in zones)),
            'floors': data.get('floors', 1),
            'zones': [{'name': z['name'], 'area': z['area'], 'type': z['type']} for z in zones],
        },
        'task_list': tasks,
        'raw_data': data,
    }


def parse_natural_language(text: str) -> dict:
    """从自然语言解析户型（调用LLM）"""
    from src.agents.src.tools.llm_adapter import LLMFactory, ChatMessage

    system_prompt = """你是AI-CAD系统的设计输入解析专家。
从用户输入中提取以下信息，输出JSON：
{
  "project_type": "住宅",
  "disciplines": ["建筑"],
  "building_area": 100,
  "floors": 1,
  "zones": [
    {"name": "客厅", "area": 20, "type": "living"},
    {"name": "主卧", "area": 12, "type": "bedroom"}
  ],
  "door_count": 7,
  "window_count": 5
}
只输出JSON，不要其他内容。"""

    llm = LLMFactory.from_env()
    response = llm.chat_with_retry(
        [ChatMessage(role='user', content=text)],
        max_tokens=300,
    )

    if not response.text:
        # Fallback: 默认住宅
        return {
            'project_type': '住宅',
            'disciplines': ['建筑'],
            'project_structure': {'building_area': 0, 'floors': 1, 'zones': []},
            'task_list': [],
            'raw_data': {},
        }

    try:
        # 提取JSON部分
        text = response.text.strip()
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0].strip()
        elif '{' in text:
            text = text[text.find('{'):text.rfind('}')+1]

        parsed = json.loads(text)

        # 生成默认任务
        zones = parsed.get('zones', [])
        door_count = parsed.get('door_count', len(zones) + 1)
        window_count = parsed.get('window_count', max(1, len(zones) // 2))

        tasks = [
            {'id': 'wall-outer', 'type': 'wall', 'category': 'structural',
             'params': {'thickness': 0.24}, 'description': '绘制外墙'},
            {'id': 'wall-inner', 'type': 'wall', 'category': 'structural',
             'params': {'thickness': 0.12}, 'description': '绘制内墙'},
            {'id': 'door-entrance', 'type': 'door', 'category': 'opening',
             'params': {'width': 1.0, 'type': 'entrance'}, 'description': '插入户门'},
        ]

        for i in range(min(door_count - 1, len(zones) + 2)):
            tasks.append({
                'id': f'door-room-{i}',
                'type': 'door',
                'category': 'opening',
                'params': {'width': 0.9, 'type': 'interior'},
                'description': f'插入室内门{i+1}',
            })

        if window_count > 0:
            tasks.append({
                'id': 'window-all',
                'type': 'window',
                'category': 'opening',
                'params': {'sill_height': 0.9},
                'description': f'插入窗户 (共{window_count}个)',
            })

        tasks.extend([
            {'id': 'dim-axis', 'type': 'dimension', 'category': 'annotation',
             'params': {'style': 'axis'}, 'description': '轴线标注'},
            {'id': 'dim-opening', 'type': 'dimension', 'category': 'annotation',
             'params': {'style': 'opening'}, 'description': '洞口标注'},
        ])

        return {
            'project_type': parsed.get('project_type', '住宅'),
            'disciplines': parsed.get('disciplines', ['建筑']),
            'project_structure': {
                'building_area': parsed.get('building_area', 0),
                'floors': parsed.get('floors', 1),
                'zones': [
                    {'name': z.get('name', '房间'), 'area': z.get('area', 0), 'type': z.get('type', 'interior')}
                    for z in zones
                ],
            },
            'task_list': tasks,
            'raw_data': parsed,
        }
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[Parser] JSON parse failed: {e}")
        # Return fallback
        return {
            'project_type': '住宅',
            'disciplines': ['建筑'],
            'project_structure': {'building_area': 0, 'floors': 1, 'zones': []},
            'task_list': [],
            'raw_data': {},
        }


def parse_input(input_source: str, is_file: bool = False) -> dict:
    """统一输入解析入口"""
    if is_file:
        return parse_json_input(input_source)
    else:
        return parse_natural_language(input_source)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        result = parse_input(sys.argv[1], is_file=True)
    else:
        result = parse_input('三室一厅住宅，建筑面积约100平米')

    print(json.dumps(result, ensure_ascii=False, indent=2))
