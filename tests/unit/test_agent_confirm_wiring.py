"""
人在回路确认闸 — bridge 层接线测试。

上一段 (test_agent_confirm_routes.py) 验的是「登记/语义」; 本文件验的是
_bridge._resume_agent_graph 是否真接上了 graph.run_agent_with_confirmation
(挂起→放行→resume 出终态), 即「确认闸从半残变真通」的那根线。

对 langgraph 环境鲁棒:
  - 已装 langgraph → confirmed=True 真 resume, resumed=True + 出终态摘要
    (rule_violation_count / final_dwg_path / export_status 字段齐)。
  - 未装 langgraph → 诚实降级 resumed=False + reason 说明图侧不可用。
两种都算「通路已接通、不造假」; 绝不再写死 resumed=False (那是占位语义)。

__main__ 直跑护栏: 只列无 fixture 子集, 用 ASCII print (Windows GBK 不崩)。
"""
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from fastapi.testclient import TestClient

from src.gui import bridge

HAS_LANGGRAPH = True
try:
    import langgraph  # noqa: F401
    from langgraph.checkpoint.memory import MemorySaver  # noqa: F401
except Exception:
    HAS_LANGGRAPH = False

app = bridge.app


def _register_run_and_task():
    """登记一个「正在等人确认」的 run + task, 供 confirm 端点操作。"""
    bridge._pending_agent_runs["wire-run-001"] = {"node": "awaiting_confirmation"}
    bridge._register_agent_task("wire-run-001", "door-9", "awaiting_confirmation")


def test_reject_stays_pending_and_no_resume():
    """confirmed=False → 登记为待确认, 不触发 resume (通路明确不走图侧)。"""
    _register_run_and_task()
    with TestClient(app) as client:
        resp = client.post(
            "/agent/confirm",
            json={"task_id": "door-9", "confirmed": False},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "pending_confirm"
        assert "resume" not in body  # 拒绝放行不 resume
        print("PASS test_reject_stays_pending_and_no_resume")


def test_confirm_wired_resume_returns_terminal_shape():
    """confirmed=True → resume 通路接通: 返回结构带 resumed + (终态摘要 或 诚实降级 reason)。"""
    _register_run_and_task()
    with TestClient(app) as client:
        resp = client.post(
            "/agent/confirm",
            json={"task_id": "door-9", "confirmed": True,
                  "modifications": {"door-9": {"width_m": 1.0}}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "confirmed"
        assert "resume" in body
        r = body["resume"]
        assert "resumed" in r
        if HAS_LANGGRAPH:
            # 框架可用 → 真 resume, 出终态摘要 (通路真通了, 不再 not_wired)
            assert r["resumed"] is True, f"expected real resume, got {r}"
            assert "rule_violation_count" in r
            assert "final_dwg_path" in r
            assert "export_status" in r
        else:
            # 框架不可用 → 诚实降级, reason 说明图侧不可用 (不造假终态)
            assert r["resumed"] is False
            assert "reason" in r
            assert "agent_graph_not_available" in r["reason"]
        print("PASS test_confirm_wired_resume_returns_terminal_shape")


if __name__ == "__main__":
    test_reject_stays_pending_and_no_resume()
    test_confirm_wired_resume_returns_terminal_shape()
    print("OK: bridge human-in-loop confirm wiring tests passed")


# ─── session 级人在回路 (bridge /agent/run 起真实挂起图 → /agent/confirm 真续跑) ───
# 依赖 langgraph (真起图); 无框架环境则整体跳过, 不影响上面演示级测试。
import pytest

if HAS_LANGGRAPH:
    def test_session_run_suspends_with_real_pending():
        """/agent/run 起一次真实 auto_mode=False 图, 应挂起在确认点 + 返回真实 pending。"""
        with TestClient(app) as client:
            resp = client.post("/agent/run", json={"sample": "residential_100sqm.json"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["node"] == "awaiting_confirmation"
            assert body["pending_task_count"] >= 1
            assert body["cad_result_count"] >= 1  # 挂起前 CAD 已出图
            thread_id = body["thread_id"]
            # 该 thread 有 session 存住 (续跑端点能认得它)
            assert thread_id in bridge._agent_sessions
            print("PASS test_session_run_suspends_with_real_pending")

    def test_session_confirm_resumes_same_thread():
        """/agent/confirm 对真实挂起 run 放行 → 走 session 级真续跑 (session=True 终态)。"""
        with TestClient(app) as client:
            run_body = client.post("/agent/run", json={"sample": "residential_100sqm.json"}).json()
            thread_id = run_body["thread_id"]
            tid = run_body["pending_task_ids"][0]
            resp = client.post("/agent/confirm", json={"task_id": tid, "confirmed": True})
            assert resp.status_code == 200
            r = resp.json()["resume"]
            assert r["resumed"] is True
            assert r["session"] is True, "应走 session 级真续跑 (同一 thread), 非演示回退"
            assert "rule_violation_count" in r
            assert "export_status" in r
            print("PASS test_session_confirm_resumes_same_thread")

    def test_session_reject_keeps_running():
        """对真实挂起 run confirmed=False → 不 resume, session 仍存活待下一批确认。"""
        with TestClient(app) as client:
            run_body = client.post("/agent/run", json={"sample": "residential_100sqm.json"}).json()
            thread_id = run_body["thread_id"]
            tid = run_body["pending_task_ids"][0]
            resp = client.post("/agent/confirm", json={"task_id": tid, "confirmed": False})
            assert resp.status_code == 200
            assert resp.json()["status"] == "pending_confirm"
            assert thread_id in bridge._agent_sessions  # session 未销毁, 可再确认
            print("PASS test_session_reject_keeps_running")
