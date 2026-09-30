"""
FastAPI 端点测试 — Agent 人工确认（人在回路）步进/确认接口
仿项目现有测试范式（tests/unit 下、sys.path 注入项目根、即时通过不依赖 langgraph）。
"""
import sys
import os

# Add project root to path（与 tests/unit/*、tests/integration/* 一致）
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from fastapi.testclient import TestClient

from src.gui import bridge

# 确认闸端点已并入 src/gui/bridge.py (原 src/server routes.py 收敛掉, 单套后端)。
app = bridge.app

# 模块级 fixture：登记一个「正在等人确认」的 run + task。
# run 挂在 awaiting_confirmation 节点（内存态），door-3 是它待确认的 task，
# 让 /agent/confirm + /agent/status 有真实对象可操作（不依赖 graph.py 的 resume API）。
bridge._pending_agent_runs["demo-run-001"] = {"node": "awaiting_confirmation"}
bridge._register_agent_task("demo-run-001", "door-3", "awaiting_confirmation")


def test_agent_status_lists_pending_confirmation():
    """status 报出停在哪个节点 + 待确认 task 列表。"""
    with TestClient(app) as client:
        resp = client.get("/agent/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["current_node"] == "awaiting_confirmation"
        assert body["is_running"] is True
        ids = [t["task_id"] for t in body["awaiting_confirmation"]]
        assert "door-3" in ids
        assert body["pending_task_count"] >= 1
        print("PASS test_agent_status_lists_pending_confirmation")


def test_agent_confirm_unknown_task_404():
    """未知 task_id → 404（错误处理与 routes.py 现有端点一致）。"""
    with TestClient(app) as client:
        resp = client.post(
            "/agent/confirm",
            json={"task_id": "does-not-exist", "confirmed": True},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Task not found"
        print("PASS test_agent_confirm_unknown_task_404")


def test_agent_confirm_rejects_missing_fields():
    """缺必填字段 → 422（pydantic 校验）。"""
    with TestClient(app) as client:
        resp = client.post("/agent/confirm", json={"confirmed": True})
        assert resp.status_code == 422
        print("PASS test_agent_confirm_rejects_missing_fields")


def test_agent_confirm_records_decision_and_stays_pending_when_rejected():
    """confirmed=False → 登记为 pending_confirm，不触发 resume；task 仍在 status 列表里。"""
    with TestClient(app) as client:
        resp = client.post(
            "/agent/confirm",
            json={"task_id": "door-3", "confirmed": False},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["confirmed"] is False
        assert body["status"] == "pending_confirm"
        assert "resume" not in body  # 未放行不 resume
        # 仍停在待确认
        assert client.get("/agent/status").json()["pending_task_count"] >= 1
        print("PASS test_agent_confirm_records_decision_and_stays_pending_when_rejected")


def test_agent_confirm_approved_triggers_resume_hook():
    """confirmed=True → 触发 resume 对接点（当前是占位 _resume_agent_graph）。"""
    with TestClient(app) as client:
        resp = client.post(
            "/agent/confirm",
            json={"task_id": "door-3", "confirmed": True,
                  "modifications": {"door-3": {"width_m": 1.0}}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["confirmed"] is True
        assert body["status"] == "confirmed"
        assert body["modifications"] == {"door-3": {"width_m": 1.0}}
        # 当前 graph.py resume 尚未定死 → 占位 hook 报 not_wired（见 TODO）
        assert body["resume"]["resumed"] is False
        print("PASS test_agent_confirm_approved_triggers_resume_hook")


if __name__ == "__main__":
    test_agent_status_lists_pending_confirmation()
    test_agent_confirm_unknown_task_404()
    test_agent_confirm_rejects_missing_fields()
    test_agent_confirm_records_decision_and_stays_pending_when_rejected()
    test_agent_confirm_approved_triggers_resume_hook()
    # ASCII print — Windows GBK 终端不能 print emoji (直跑护栏见 test_direct_run.py)
    print("OK: all agent-confirmation route tests passed")
