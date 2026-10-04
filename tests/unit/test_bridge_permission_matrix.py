"""
M5 权限矩阵端点测试 — bridge /api/permission/matrix (角色→权限 + 结构自洽校验)

验证 permission_model.validate_permissions_matrix 经桥透出: 默认矩阵结构合法,
业务回填畸形矩阵时端点如实报 issues/malformed_actions (而非线上静默全拒绝)。
红线二: 校验的是矩阵「结构」(命名/类型/重复), 不断言「谁到底能干什么」的业务值。
__main__ 直跑护栏: 只列无 fixture 子集 (monkeypatch 的 case 仅 pytest 跑), ASCII print。
"""
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from fastapi.testclient import TestClient

import src.gui.bridge as bridge
from src.gui.bridge import app


def test_permission_matrix_default_valid():
    """默认 DEFAULT_PERMISSIONS 结构自洽 → valid=true, issues 空。"""
    with TestClient(app) as client:
        resp = client.get("/api/permission/matrix")
    assert resp.status_code == 200, f"应 200, 实际 {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["valid"] is True, f"默认矩阵应结构自洽, 得 {body['issues']}"
    assert body["issues"] == [] and body["malformed_actions"] == []
    # 透出角色→权限 (list 形态, 非 tuple, 便于前端消费)
    assert "designer" in body["roles"]
    assert "design.read" in body["roles"]["designer"]
    assert "note" in body
    print("PASS test_permission_matrix_default_valid")


def test_permission_matrix_flags_malformed(monkeypatch):
    """业务回填畸形矩阵 (design..write 双点 + 重复动作) → 端点如实报 issues。

    这是「矩阵结构自洽校验」的核心价值: 手滑写错动作串不再线上静默全拒绝,
    而是端点前置报 malformed_actions, 可查可修。"""
    import src.agents.src.tools.permission_model as pm
    monkeypatch.setattr(
        pm, "DEFAULT_PERMISSIONS",
        {"designer": ("design.read", "design..write", "design.read")},
        raising=False)
    # bridge 懒 import 的是 permission_model 模块属性, monkeypatch 该属性即可生效
    with TestClient(app) as client:
        resp = client.get("/api/permission/matrix")
    body = resp.json()
    assert resp.status_code == 200
    assert body["valid"] is False, "畸形矩阵应报 invalid"
    assert "design..write" in body["malformed_actions"], "双点畸形动作应入 malformed"
    assert any("重复" in it for it in body["issues"]), "重复动作应报结构异味"
    assert any("命名不合规" in it for it in body["issues"])
    print("PASS test_permission_matrix_flags_malformed")


if __name__ == "__main__":
    test_permission_matrix_default_valid()
    # 注: test_permission_matrix_flags_malformed 需 monkeypatch fixture, 仅 pytest 全量跑。
    print("OK: all permission matrix endpoint tests passed")
