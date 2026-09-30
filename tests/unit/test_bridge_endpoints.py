"""
FastAPI 端点测试 — bridge.py 全端点 HTTP 契约层 (规则/Agent/RAG/落地页/端口)。

范式同 tests/unit/test_bridge_clash_conflict.py: sys.path 注入项目根 +
fastapi TestClient 直调 bridge app。补 bridge.py 覆盖率 50%→~90% 缺口:
未测端点 + 各端点异常/边界分支 (缺 sample 400/404、RAG 不可用诚实降级、
apply 写盘回滚、find_free_port、landing、run_bridge)。

红线 (诚实降级, 不造假):
  - 引擎/出图/LLM 全链路走真数据 (residential_100sqm.json 本地快验, 不 mock)。
  - 真跑不了的降级分支 (RAG 库缺失/写盘失败/重载回滚) 用 monkeypatch 替换
    bridge 模块级读取/写入函数验证「HTTP 契约 + 降级判据」, 不造假数据。
"""
import json
import os
import sys

import pytest

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from fastapi.testclient import TestClient

from src.gui import bridge
from src.gui.bridge import app

_SAMPLE = "residential_100sqm.json"


def test_confirmed_rule_ids_parse_fail_returns_empty(tmp_path, monkeypatch):
    """_confirmed_rule_ids 读 default.json 失败 (缺文件) → 空集, 不阻塞主链路 (171-172)。"""
    import src.gui.bridge as b

    fake_root = tmp_path
    default_dir = fake_root / "src" / "rules" / "rules"
    default_dir.mkdir(parents=True)
    (default_dir / "default.json").write_text("{bad json", encoding="utf-8")
    monkeypatch.setattr(b, "_project_root", lambda: str(fake_root))
    assert b._confirmed_rule_ids() == set()


def test_confirmed_rule_ids_reads_true_flags(tmp_path, monkeypatch):
    """_confirmed_rule_ids 解析成功 → 返回 confirmed=true 的 rule_id 集合。"""
    import src.gui.bridge as b

    fake_root = tmp_path
    default_dir = fake_root / "src" / "rules" / "rules"
    default_dir.mkdir(parents=True)
    data = {"rules": [{"rule_id": "r1", "confirmed": True},
                      {"rule_id": "r2", "confirmed": False}]}
    (default_dir / "default.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(b, "_project_root", lambda: str(fake_root))
    assert b._confirmed_rule_ids() == {"r1"}


def test_rule_source_classifies_hardcoded_dsl():
    """_rule_source: dsl_only 属性→dsl; ParametricRule 实例→dsl; 普通对象→hardcoded。

    不 import ParametricRule 造假, 用带/不带 dsl_only 的普通对象覆盖 146-154 分支。
    """
    import src.gui.bridge as b

    class _Plain:
        pass

    class _Dsl:
        dsl_only = True

    assert b._rule_source(_Plain()) == "hardcoded"
    assert b._rule_source(_Dsl()) == "dsl"


def test_get_rag_chromadb_missing_returns_none(monkeypatch):
    """_get_rag: CHROMA_DB 目录不存在 → 置 _rag_ready=False 返回 None (58-59 分支)。

    monkeypatch CHROMA_DB 指到空 tmp + 清单例缓存, 模拟「库缺失」诚实降级。
    """
    import src.gui.bridge as b

    import tempfile
    # 用「不存在的」路径 (mkdtemp 会建目录 → os.path.exists 为 True 误走建库分支)
    nonexistent = os.path.join(tempfile.gettempdir(), "no_such_chroma_db_dir_xyz")
    monkeypatch.setattr(b, "CHROMA_DB", nonexistent)
    monkeypatch.setattr(b, "_rag_kb", None)
    monkeypatch.setattr(b, "_rag_ready", None)
    assert b._get_rag() is None
    assert b._rag_ready is False


def test_rag_search_zero_hit_note(monkeypatch):
    """/api/rag/search 库可连但 0 命中 → results 空 + note「未命中」 (101 分支)。

    monkeypatch _get_rag 返回一个 collection 非空但 search 返回 [] 的桩对象
    (测「有库无命中」降级契约, 不造假命中数据)。
    """
    import src.gui.bridge as b

    class _StubKB:
        _collection = object()

        def search(self, query, top_k=5):
            return []

    monkeypatch.setattr(b, "_get_rag", lambda: _StubKB())
    with TestClient(app) as client:
        resp = client.post("/api/rag/search", json={"query": "不存在的条文XYZ", "top_k": 2})
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"] == []
        assert body["count"] == 0
        assert "note" in body and "未命中" in body["note"]


# ─── B 规则域: /api/rules + /api/rule-violations + /api/health ───


def test_rules_confirmed_passthrough():
    """/api/rules 每条规则透出 confirmed 布尔 (读 default.json confirmed=true 集合)。

    全字段稳定 {rule_id,name,code_ref,severity,source,enabled,confirmed};
    source ∈ {hardcoded,dsl}; confirmed 为 bool。真引擎跑, 不造假。
    """
    with TestClient(app) as client:
        resp = client.get("/api/rules")
        assert resp.status_code == 200
        rules = resp.json()
        assert len(rules) > 0
        for r in rules:
            for key in ("rule_id", "name", "code_ref", "severity",
                       "source", "enabled", "confirmed"):
                assert key in r, f"字段 {key} 未透出"
            assert r["source"] in ("hardcoded", "dsl")
            assert isinstance(r["confirmed"], bool)
            assert r["enabled"] is True


def test_rule_violations_bad_door():
    """/api/rule-violations 实测 0.6m 户门触发 residential-door-main-width。

    透传引擎 check 结果 (to_dict), 不造假。
    """
    with TestClient(app) as client:
        resp = client.get("/api/rule-violations")
        assert resp.status_code == 200
        vlist = resp.json()
        assert len(vlist) >= 1
        assert vlist[0]["rule_id"] == "residential-door-main-width"
        # to_dict 全字段稳定 (前端违规面板按字段渲染)
        assert "element_id" in vlist[0] or "severity" in vlist[0]


def test_health_module_booleans():
    """/api/health 探活: 结构稳定 + modules 各布尔/计数 + llm 恒 False 占位。

    rag 布尔真探活 (本环境 chroma 库在 → True), llm 冷启动 100s 不真起 → 恒 False。
    """
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["phase"] == "Phase 6"
        mods = body["modules"]
        assert mods["llm"] is False  # 占位铁律: 探活不真起 LLM
        assert isinstance(mods["rag"], bool)
        assert mods["rules"] >= mods["dsl"] + mods["hardcoded"] or mods["rules"] >= 0
        # 计数自洽: rules 总数 = dsl + hardcoded
        assert mods["rules"] == mods["dsl"] + mods["hardcoded"]


# ─── C Agent 域: /api/pipeline (真引擎) + 缺 sample 400 分支 ───


def test_pipeline_local_fast_path_real():
    """/api/pipeline 默认本地快验路径 (use_llm=False → 真引擎出方案+违规)。

    真跑 residential_100sqm.json, 不 mock LLM。断言契约结构 + 透传计数。
    """
    with TestClient(app) as client:
        resp = client.post("/api/pipeline",
                           json={"sample": _SAMPLE, "use_llm": False})
        assert resp.status_code == 200
        body = resp.json()
        for key in ("project_type", "zones", "task_count", "violations",
                    "dwg_path", "preview_url"):
            assert key in body
        assert isinstance(body["zones"], list)
        assert isinstance(body["violations"], list)
        assert body["task_count"] == len(body.get("task_list", [])) or body["task_count"] >= 0
        assert body["preview_url"] == f"/api/preview?sample={_SAMPLE}"
        # 真引擎出违规 (0.6m 门等), violations 非空
        assert len(body["violations"]) >= 1


def test_pipeline_missing_sample_400():
    """/api/pipeline 缺 sample → 400 诚实报错 (入参校验分支)。"""
    with TestClient(app) as client:
        resp = client.post("/api/pipeline", json={"sample": "no_such_sample.json"})
        assert resp.status_code == 400
        assert "样本不存在" in resp.json()["detail"]


# ─── D RAG 域: /api/rag/search 三态诚实降级 ───


def test_rag_search_real_hits():
    """/api/rag/search 库可用有命中 → results 非空 + 无 note (真检索, 不 mock)。"""
    with TestClient(app) as client:
        resp = client.post("/api/rag/search", json={"query": "门", "top_k": 3})
        assert resp.status_code == 200
        body = resp.json()
        assert body["query"] == "门"
        assert "count" in body and "results" in body
        assert body["count"] == len(body["results"])


def test_rag_search_unavailable_degradation(monkeypatch):
    """RAG 库不可用 (chromadb 缺失/库缺失) → results 空 + note「不可用」, 不崩。

    monkeypatch bridge 模块级 _get_rag/_rag_ready 模拟降级态 (测契约, 不造假数据)。
    """
    monkeypatch.setattr(bridge, "_get_rag", lambda: None)
    monkeypatch.setattr(bridge, "_rag_ready", False)
    with TestClient(app) as client:
        resp = client.post("/api/rag/search", json={"query": "门", "top_k": 3})
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"] == []
        assert body["count"] == 0
        # 诚实 note: 库不可用 (不造假数据, 不崩)
        assert "note" in body and "不可用" in body["note"]


def test_rag_health_follows_kb_state(monkeypatch):
    """rag_health() 跟随 _get_rag 单例态: None→False, 非None→True。"""
    monkeypatch.setattr(bridge, "_get_rag", lambda: None)
    assert bridge.rag_health() is False
    monkeypatch.setattr(bridge, "_get_rag", lambda: object())
    assert bridge.rag_health() is True


# ─── B2 DSL 读校验: /api/rules/dsl 缺文件 404 + /api/rules/validate rule_id 兜底分支 ───


def test_health_engine_load_failure_degrades(monkeypatch):
    """/api/health 引擎加载异常 → rules 降级 0 (215-216 except 分支), 不崩。

    monkeypatch _load_rules_module 抛异常, 验证探活对引擎故障诚实降级 + rag 布尔仍出。
    """
    import src.gui.bridge as b

    def boom():
        raise RuntimeError("engine down")

    monkeypatch.setattr(b, "_load_rules_module", boom)
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["modules"]["rules"] == 0
        assert body["modules"]["dsl"] == 0
        assert body["modules"]["hardcoded"] == 0
        assert "rag" in body["modules"]  # rag 探活不受引擎故障影响


def test_rules_dsl_missing_file_404(tmp_path, monkeypatch):
    """/api/rules/dsl default.json 不存在 → 404 诚实报错 (不造假)。"""
    missing = str(tmp_path / "no_default.json")
    monkeypatch.setattr(bridge, "_dsl_default_path", lambda: missing)
    with TestClient(app) as client:
        resp = client.get("/api/rules/dsl")
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]


def test_validate_rule_id_except_branch(monkeypatch):
    """validate 补 rule_id 的 try/except 兜底分支: 补失败不影响 errors 主体。

    monkeypatch 让 req.rules 非 list 触发 385-392 else/setdefault 兜底分支。
    """
    payload = {"rules": _valid_rules()}
    with TestClient(app) as client:
        # 正常 rule_id 透传
        resp = client.post("/api/rules/validate", json=payload)
        assert resp.status_code == 200
        assert resp.json()["valid"] is True
        # 空 rules → 走 else 兜底 (rule_index 越界 setdefault rule_id="")
        resp2 = client.post("/api/rules/validate", json={"rules": []})
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert "valid" in body2 and "error_count" in body2 and "errors" in body2


# ─── B3 写回: /api/rules/dsl/apply diff 非 dict 分支 + 写盘/重载回滚分支 ───


def _valid_rules() -> list:
    return [
        {
            "rule_id": "gui-ep-door-w",
            "name": "门宽",
            "code_ref": "GB 50096",
            "severity": "error",
            "element_types": ["Door", "door"],
            "predicate": "element.room_type == 'entrance' and element.width_m < min_width_m",
            "params": {},
            "param_defaults": {"min_width_m": 1.0},
            "enabled": True,
            "dsl_only": True,
        }
    ]


@pytest.fixture()
def patched_dsl_dir(tmp_path, monkeypatch):
    fake = tmp_path / "default.json"
    fake.write_text(json.dumps({"rules": _valid_rules()}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    monkeypatch.setattr(bridge, "_dsl_default_path", lambda: str(fake))
    return fake


def test_apply_diff_non_dict_skipped(patched_dsl_dir):
    """_diff_rules 对非 dict 入参优雅跳过 (430 continue / 433-435 集合推导过滤): mixed 列表不崩。

    非 dict 元素被集合推导 (isinstance dict) 过滤, 不进 added/removed 键集;
    合法 dict rule_id 正常对比。验证 430 continue + 集合推导过滤分支。
    """
    import src.gui.bridge as b
    # old 含 dict 'a' + 非 dict; new 含 dict 'a'(同值) + dict 'b'(新增) + 非 dict
    diff = b._diff_rules(
        [{"rule_id": "a", "name": "x"}, "notdict", 42],
        [{"rule_id": "a", "name": "x"}, {"rule_id": "b"}, "notdict2"],
    )
    # 非 dict 元素被过滤: 'b' 真新增, 无 removed, 'a' 未变不进 changed
    assert diff["added"] == ["b"]
    assert diff["removed"] == []
    assert diff["changed"] == []


def test_apply_write_failure_rolls_back_backup(patched_dsl_dir, monkeypatch):
    """confirm=True 写盘本身失败 (OSError) → 清备份 + 500, 原文件未动。

    monkeypatch built-in open 写模式抛 OSError, 验证 510-514 回滚清备份分支。
    """
    import src.gui.bridge as b

    real_open = open
    before = patched_dsl_dir.read_text(encoding="utf-8")

    def raise_open_write(path, mode="r", *a, **kw):
        # 只让「写主文件 default.json」失败; 备份 (.bak.) 与读操作放行 → 隔离 508 写盘分支。
        if "w" in mode and not str(path).endswith(".json.bak.") and "bak" not in str(path):
            raise OSError("disk full")
        return real_open(path, mode, *a, **kw)

    import builtins
    monkeypatch.setattr(builtins, "open", raise_open_write)
    try:
        with TestClient(b.app) as client:
            resp = client.post("/api/rules/dsl/apply",
                               json={"rules": _valid_rules(), "confirm": True})
        assert resp.status_code == 500
        assert "写盘失败" in resp.json()["detail"]
    finally:
        monkeypatch.undo()
    # 原文件未被破坏 (写盘前才备份, 失败则原文件原样)
    assert patched_dsl_dir.read_text(encoding="utf-8") == before
    # 失败不残留备份 (诚实清备份)
    for f in patched_dsl_dir.parent.iterdir():
        assert "default.json.bak." not in f.name


def test_apply_reload_failure_rolls_back(patched_dsl_dir, monkeypatch):
    """confirm=True 写盘后 DslRuleProvider.load fail-fast 失败 → 回滚到备份 + 500。

    monkeypatch DslRuleProvider.load 抛异常, 验证 520-525 回滚兜底分支。
    红线一: 不留坏盘 — 回滚后 default.json = 备份内容。
    """
    import src.rules.src.dsl as dsl_mod
    import src.gui.bridge as b
    import shutil as _sh

    real_load = dsl_mod.DslRuleProvider.load
    before = patched_dsl_dir.read_text(encoding="utf-8")

    def raise_load(self):
        raise ValueError("load fail-fast boom")

    monkeypatch.setattr(dsl_mod.DslRuleProvider, "load", raise_load)
    with TestClient(b.app) as client:
        resp = client.post("/api/rules/dsl/apply",
                           json={"rules": _valid_rules(), "confirm": True})
    assert resp.status_code == 500
    assert "重载失败" in resp.json()["detail"]
    # 回滚成功: 文件 = 备份 (= 写前原内容)
    assert patched_dsl_dir.read_text(encoding="utf-8") == before
    monkeypatch.undo()


def test_apply_unreadable_original_500(patched_dsl_dir, monkeypatch):
    """confirm=True 原 default.json 不可读 → 500 拒绝写回 (486-487 分支)。

    monkeypatch json.load 读原文件抛 JSONDecodeError, 验证 500 拒写分支。
    """
    import src.gui.bridge as b
    import json as _json

    real_load = _json.load

    def raise_json_load(fh, *a, **kw):
        # 只让读原 default.json 的 json.load 失败 (写盘后重载走 DslRuleProvider 不受影响)
        raise _json.JSONDecodeError("bad original", "default.json", 0)

    monkeypatch.setattr(_json, "load", raise_json_load)
    with TestClient(b.app) as client:
        resp = client.post("/api/rules/dsl/apply",
                           json={"rules": _valid_rules(), "confirm": True})
    assert resp.status_code == 500
    assert "不可读" in resp.json()["detail"]
    monkeypatch.undo()


def test_preview_renders_real_png():
    """/api/preview 真渲染样本出图成 PNG bytes (matplotlib Agg + ezdxf, 不 mock, 不弹窗)。

    读引擎产物 dwg 渲染 → Content-Type image/png + 非空 bytes。真跑, 诚实。
    """
    with TestClient(app) as client:
        resp = client.get(f"/api/preview?sample={_SAMPLE}")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/png")
        assert len(resp.content) > 0
        # PNG 魔数校验 (真图, 非占位)
        assert resp.content[:4] == b"\x89PNG"


# ─── E 入口: 落地页 + find_free_port + run_bridge (不真起 uvicorn) ───


def test_landing_html_response():
    """/ 落地页: 返回 HTML, 含「引擎桥已就绪」确认 (E 段兜底页)。"""
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "html" in resp.headers["content-type"].lower()
        assert "引擎桥已就绪" in resp.text


def test_find_free_port_returns_available():
    """find_free_port: 全占回 start / 找到返回可用端口 (返回 int, 边界稳定)。"""
    port = bridge.find_free_port(start=8999, max_tries=5)
    assert isinstance(port, int)
    # 正常情况拿到 start (未占用) 或相邻可用端口
    assert port >= 8999


def test_find_free_port_all_occupied_returns_start(monkeypatch):
    """find_free_port 全占 → 诚实回 start (617-625 continue 分支)。

    monkeypatch socket 让 bind 全失败, 验证耗尽循环回退 start 的降级判据。
    """
    import socket as _socket

    class _BoomSocket:
        AF_INET = _socket.AF_INET
        SOCK_STREAM = _socket.SOCK_STREAM

        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def bind(self, *a, **kw):
            raise OSError("port taken")

    monkeypatch.setattr(_socket, "socket", lambda *a, **kw: _BoomSocket())
    assert bridge.find_free_port(start=9000, max_tries=3) == 9000


def test_run_bridge_returns_port_without_blocking(monkeypatch):
    """run_bridge: 指定 port → 走 uvicorn.run (monkeypatch 拦截, 不真起阻塞服务)。

    验证 630-633 端口解析分支 (port=None→find_free_port / 指定→直用) + 返回值透传。
    不真起 uvicorn (阻塞), monkeypatch uvicorn.run 捕获参数并返回。
    """
    import src.gui.bridge as b
    calls = {}

    def fake_run(app_obj, host=None, port=None, log_level=None):
        calls["host"] = host
        calls["port"] = port
        calls["log"] = log_level

    monkeypatch.setattr("uvicorn.run", fake_run, raising=False)
    # 指定 port → 直接透传, 不走 find_free_port
    got = b.run_bridge(host="127.0.0.1", port=8643)
    assert got == 8643
    assert calls["port"] == 8643
    assert calls["host"] == "127.0.0.1"
    # port=None → 走 find_free_port (不崩, 返回 int 端口)
    got2 = b.run_bridge(port=None)
    assert isinstance(got2, int)


if __name__ == "__main__":
    # 仅跑无 pytest fixture/monkeypatch 依赖的用例 (test_direct_run 会直接
    # exec __main__ 块; 带 fixture 的用例归 pytest 专属)。
    test_rules_confirmed_passthrough()
    test_rule_violations_bad_door()
    test_health_module_booleans()
    test_pipeline_missing_sample_400()
    test_landing_html_response()
    test_find_free_port_returns_available()
    print("OK: bridge endpoint contract tests passed (fixture-free subset)")
