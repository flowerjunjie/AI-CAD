"""
intent_structure 机制层护栏测试 (M1 机制已通部分, 无需外部专家)

锁定三条机制不变量:
  1. LLM JSON 畸形 → 无声降级 (log warning, 不崩, 落住宅默认)
  2. 计数透传六键契约: raw_data.X 有值 → task_list 必含对应任务
  3. 默认分区生成: zones 空时用内置 5 房分区

范式照 test_clash_detection.py 纯函数 + 独立 _import 边界。
__main__ 只列无 fixture 子集, 不 print 中文/emoji (Windows GBK 终端)。
"""
import json
import logging
import os
import sys
from unittest import mock

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _import():
    from src.agents.src.nodes import intent_structure as isd
    return isd


# ── 1. LLM 解析失败护栏: JSON 畸形 → 静默降级 + warning 日志, 不崩 ──────────────

def test_llm_malformed_json_falls_back_to_default():
    """LLM 回非 JSON 文本 → 落住宅默认 (不崩), 且记 warning。"""
    isd = _import()

    with mock.patch.object(isd, "_get_llm") as m_llm:
        m_llm.return_value = mock.Mock()
        m_llm.return_value.chat.return_value = mock.Mock(text="{not valid json")
        result = isd.intent_understanding_node({"project_input": "随便说点啥"})

    # 降级到默认住宅, 字段齐全
    assert result["project_type"] == "住宅"
    assert result["disciplines"] == ["建筑"]
    assert result["project_structure"]["zones"] == []


def test_llm_malformed_json_logs_warning():
    """降级路径必须留痕 (warning), 不许无声吞。"""
    isd = _import()

    with mock.patch.object(isd, "_get_llm") as m_llm:
        m_llm.return_value = mock.Mock()
        m_llm.return_value.chat.return_value = mock.Mock(text="{broken")
        with mock.patch.object(isd.logger, "warning") as m_warn:
            isd.intent_understanding_node({"project_input": "x"})

    m_warn.assert_called_once()


def test_llm_absent_falls_back_to_default():
    """无 LLM (没配 key) → 同样落住宅默认, 不崩。"""
    isd = _import()
    with mock.patch.object(isd, "_get_llm", return_value=None):
        result = isd.intent_understanding_node({"project_input": "x"})
    assert result["project_type"] == "住宅"


def test_llm_valid_json_parsed():
    """LLM 回合法 JSON → 正常解析字段, 不降级。"""
    isd = _import()
    payload = json.dumps({
        "project_type": "公建", "disciplines": ["建筑", "电气"],
        "building_area": 500, "floors": 2, "zones": [{"name": "会议室", "area": 40}],
    })
    with mock.patch.object(isd, "_get_llm") as m_llm:
        m_llm.return_value = mock.Mock()
        m_llm.return_value.chat.return_value = mock.Mock(text=payload)
        result = isd.intent_understanding_node({"project_input": "x"})
    assert result["project_type"] == "公建"
    assert result["disciplines"] == ["建筑", "电气"]
    assert result["project_structure"]["building_area"] == 500


# ── 2. 计数透传六键契约: raw_data.X 有值 → task_list 必含对应任务 ─────────────

def _ids(structure):
    isd = _import()
    return [t["id"] for t in isd._generate_task_list(structure)]


def test_task_list_baseline_no_count_keys():
    """无任何专业计数 → 只有基线 6 任务 (墙/门/窗/标注)。"""
    ids = _ids({"zones": []})
    for expected in ["wall-outer", "wall-inner", "door-entrance",
                     "window-all", "dim-axis", "dim-opening"]:
        assert expected in ids
    # 专业任务一个都不该出现
    for absent in ["pipe-plumbing", "beam-structural", "column-structural",
                   "outlet-elec", "switch-elec", "hvac-system"]:
        assert absent not in ids


def test_pipe_count_drives_pipe_task():
    assert "pipe-plumbing" in _ids({"zones": [], "pipe_count": 3})


def test_beam_column_count_drives_structural_tasks():
    ids = _ids({"zones": [], "beam_count": 2, "column_count": 4})
    assert "beam-structural" in ids
    assert "column-structural" in ids


def test_outlet_switch_count_drives_elec_tasks():
    ids = _ids({"zones": [], "outlet_count": 5, "switch_count": 2})
    assert "outlet-elec" in ids
    assert "switch-elec" in ids


def test_hvac_any_count_drives_hvac_task():
    isd = _import()
    for key in ["hvac_duct_count", "hvac_unit_count", "hvac_grille_count"]:
        s = {"zones": []}
        s[key] = 1
        assert "hvac-system" in _ids(s), f"{key} 应驱动 hvac 任务"


def test_hvac_all_zero_no_task():
    """三键全 0 → 不该有 hvac 任务。"""
    assert "hvac-system" not in _ids({
        "zones": [], "hvac_duct_count": 0, "hvac_unit_count": 0, "hvac_grille_count": 0,
    })


def test_door_count_follows_zone_count():
    """每个 zone 一个门 + 1 个户门: 3 区 → 3 个 door-room + 1 door-entrance。"""
    isd = _import()
    tasks = isd._generate_task_list({"zones": [
        {"name": "客"}, {"name": "卧"}, {"name": "厨"},
    ]})
    room_doors = [t for t in tasks if t["id"].startswith("door-room-")]
    assert len(room_doors) == 3
    assert any(t["id"] == "door-entrance" for t in tasks)


# ── 3. 默认分区生成: zones 空 → 内置 5 房 ─────────────────────────────────────

def test_structure_design_default_zones_when_empty():
    """zones 空时 structure_design_node 用内置默认 5 房分区。"""
    isd = _import()
    with mock.patch.object(isd, "RAGKnowledgeBase") as m_rag:
        inst = m_rag.return_value
        inst.initialize.return_value = None
        inst.search.return_value = []  # 不给规范, 隔离 RAG
        out = isd.structure_design_node({
            "project_type": "住宅",
            "project_structure": {"zones": []},
            "raw_data": {},
        })
    zones = out["project_structure"]["zones"]
    names = [z["name"] for z in zones]
    # 内置 5 房: 客厅/卧室1/卧室2/厨房/卫生间
    assert len(zones) == 5
    assert "客厅" in names and "厨房" in names


def test_structure_design_passes_count_keys_through():
    """raw_data 有 pipes → structure_design 透传 pipe_count 进 project_structure。"""
    isd = _import()
    with mock.patch.object(isd, "RAGKnowledgeBase") as m_rag:
        inst = m_rag.return_value
        inst.initialize.return_value = None
        inst.search.return_value = []
        out = isd.structure_design_node({
            "project_type": "住宅",
            "project_structure": {"zones": [{"name": "客"}]},
            "raw_data": {"pipes": [1, 2, 3], "outlets": [1], "switches": []},
        })
    s = out["project_structure"]
    assert s["pipe_count"] == 3
    assert s["outlet_count"] == 1
    assert s["switch_count"] == 0


if __name__ == "__main__":
    failed = 0
    for fn in [
        test_llm_malformed_json_falls_back_to_default,
        test_llm_malformed_json_logs_warning,
        test_llm_absent_falls_back_to_default,
        test_llm_valid_json_parsed,
        test_task_list_baseline_no_count_keys,
        test_pipe_count_drives_pipe_task,
        test_beam_column_count_drives_structural_tasks,
        test_outlet_switch_count_drives_elec_tasks,
        test_hvac_any_count_drives_hvac_task,
        test_hvac_all_zero_no_task,
        test_door_count_follows_zone_count,
        test_structure_design_default_zones_when_empty,
        test_structure_design_passes_count_keys_through,
    ]:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"__main__ {13 - failed}/13 passed")
    sys.exit(1 if failed else 0)
