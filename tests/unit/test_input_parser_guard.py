"""
input_parser 机制层护栏测试 (M1 机制层自主子集, 无需外部专家)

锁定两条解析路径的输入契约:
  路径A parse_json_input (文件): 坏 JSON → 响亮抛 ValueError (带文件名), 不静默空跑
  路径B parse_natural_language (LLM): 坏 JSON → 降级 task_list=[] + 留痕 (logger.warning)
范式照 test_intent_structure_guard.py 纯函数 + mock LLM 边界。
__main__ 只列无 fixture 子集, 不 print 中文/emoji (Windows GBK 终端)。
"""
import json
import logging
import os
import sys
import tempfile
from unittest import mock

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _import():
    from src.agents.src.nodes import input_parser as ip
    return ip


# ── 路径A: parse_json_input 坏 JSON → 响亮抛 ValueError, 不静默 ───────────────

def _write_tmp(content, suffix=".json"):
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def test_json_input_bad_json_raises_valueerror():
    """坏 JSON 文件 → 抛 ValueError 带文件名 (不裸抛 JSONDecodeError, 不静默)。"""
    ip = _import()
    path = _write_tmp("{broken json")
    try:
        try:
            ip.parse_json_input(path)
            assert False, "应当抛 ValueError"
        except ValueError as e:
            # 响亮: 异常消息带文件 basename, 让用户知道哪份输入坏了
            assert os.path.basename(path) in str(e)
    finally:
        os.unlink(path)


def test_json_input_logs_error_on_bad_json():
    """坏 JSON 路径必须留痕 (logger.error), 不许无声崩。"""
    ip = _import()
    path = _write_tmp("{broken")
    try:
        with mock.patch.object(ip.logger, "error") as m_err:
            try:
                ip.parse_json_input(path)
            except ValueError:
                pass
        m_err.assert_called_once()
    finally:
        os.unlink(path)


def test_json_input_valid_sample_parses():
    """合法 JSON → 正常解析出 zones + task_list (回归安全, 不破坏现有 4 处调用)。"""
    ip = _import()
    path = _write_tmp(json.dumps({
        "project_type": "住宅",
        "zones": [{"name": "客厅", "area": 20, "type": "living"}],
        "doors": [{"id": "d1", "type": "entrance", "width_m": 1.0}],
        "pipes": [1, 2],
    }))
    try:
        r = ip.parse_json_input(path)
        ids = [t["id"] for t in r["task_list"]]
        assert "door-entrance" in ids or "d1" in ids
        assert "pipe-plumbing" in ids          # pipes 键驱动
        assert r["project_structure"]["zones"][0]["name"] == "客厅"
    finally:
        os.unlink(path)


# ── 路径B: parse_natural_language LLM 坏 JSON → 降级留痕 ──────────────────────

def test_natural_language_bad_llm_json_degrades_with_log():
    """LLM 回坏 JSON → 降级 task_list=[] 且记 warning (不崩, 但留痕)。"""
    ip = _import()

    class _FakeResp:
        text = "{not valid json"

    fake_llm = mock.Mock()
    fake_llm.chat_with_retry.return_value = _FakeResp()

    with mock.patch("src.agents.src.tools.llm_adapter.LLMFactory") as m_fact:
        m_fact.from_env.return_value = fake_llm
        r = ip.parse_natural_language("三室一厅住宅")

    # 降级: 默认住宅, 空任务
    assert r["project_type"] == "住宅"
    assert r["task_list"] == []
    assert r["raw_data"] == {}


def test_natural_language_bad_llm_json_logs_warning():
    """降级路径必须留痕 (logger.warning), 不许无声空跑。"""
    ip = _import()

    class _FakeResp:
        text = "{broken"

    fake_llm = mock.Mock()
    fake_llm.chat_with_retry.return_value = _FakeResp()

    with mock.patch("src.agents.src.tools.llm_adapter.LLMFactory") as m_fact:
        m_fact.from_env.return_value = fake_llm
        with mock.patch.object(ip.logger, "warning") as m_warn:
            ip.parse_natural_language("x")
    m_warn.assert_called_once()


def test_natural_language_no_llm_response_degrades():
    """LLM 无响应 (text 空) → 降级默认, 不崩。"""
    ip = _import()

    class _FakeResp:
        text = ""

    fake_llm = mock.Mock()
    fake_llm.chat_with_retry.return_value = _FakeResp()

    with mock.patch("src.agents.src.tools.llm_adapter.LLMFactory") as m_fact:
        m_fact.from_env.return_value = fake_llm
        r = ip.parse_natural_language("x")
    assert r["project_type"] == "住宅"
    assert r["task_list"] == []


def test_natural_language_valid_llm_json_parses():
    """LLM 回合法 JSON → 正常解析, 不降级。"""
    ip = _import()

    payload = json.dumps({
        "project_type": "住宅", "building_area": 100,
        "zones": [{"name": "客厅", "area": 20, "type": "living"},
                  {"name": "主卧", "area": 12, "type": "bedroom"}],
        "door_count": 3, "window_count": 4,
    })

    class _FakeResp:
        text = payload

    fake_llm = mock.Mock()
    fake_llm.chat_with_retry.return_value = _FakeResp()

    with mock.patch("src.agents.src.tools.llm_adapter.LLMFactory") as m_fact:
        m_fact.from_env.return_value = fake_llm
        r = ip.parse_natural_language("x")
    assert r["project_structure"]["building_area"] == 100
    assert len(r["project_structure"]["zones"]) == 2
    # 有门/窗任务
    ids = [t["id"] for t in r["task_list"]]
    assert "door-entrance" in ids and "window-all" in ids


if __name__ == "__main__":
    fns = [
        test_json_input_bad_json_raises_valueerror,
        test_json_input_logs_error_on_bad_json,
        test_json_input_valid_sample_parses,
        test_natural_language_bad_llm_json_degrades_with_log,
        test_natural_language_bad_llm_json_logs_warning,
        test_natural_language_no_llm_response_degrades,
        test_natural_language_valid_llm_json_parses,
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
