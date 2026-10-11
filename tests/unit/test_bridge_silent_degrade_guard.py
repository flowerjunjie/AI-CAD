"""
bridge_dsl / bridge_rules 静默缺省值降级护栏测试 (M1 机制层自主子集)

input_parser 轮定下的标准: "缺省值降级必须留痕, 不许无声吞"。
本轮补的 2 处 (bridge_dsl._prune_dsl_backups / bridge_rules._confirmed_rule_ids)
把「读失败 → 返空缺省」从无声改成 logger.warning, 本测试锁死这条契约:
  ① 降级路径必须调用 logger.warning (不崩, 但留痕)
  ② 降级返回值语义不变 (返空 list / 空 set, 行为 0 破坏)
范式照 test_input_parser_guard.py: mock 外部边界 (os.listdir/open), 不碰真实文件。
__main__ 只列无 fixture 子集, 不 print 中文/emoji (Windows GBK 终端)。
"""
import os
import sys
from unittest import mock

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _import_dsl():
    from src.gui import bridge_dsl as bd
    return bd


def _import_rules():
    # 循环 import: bridge.py 顶部 import bridge_rules(挂 router), bridge_rules 顶部又
    # import bridge._project_root。直接 import bridge_rules 触发半初始化循环 — 先载
    # bridge 完成子模块注册, 再取 bridge_rules (与既有 test_bridge_* 的加载序对齐)。
    import src.gui.bridge  # noqa: F401  (先载主模块)
    from src.gui import bridge_rules as br
    return br


# ── bridge_dsl._prune_dsl_backups: listdir 失败 → 留痕 + 返 [] ─────────────────

def test_prune_backups_listdir_fail_logs_and_returns_empty():
    """os.listdir 抛 OSError → logger.warning 留痕 + 返 [] (行为不变, 加留痕)。"""
    bd = _import_dsl()
    with mock.patch("os.listdir", side_effect=OSError("no dir")):
        with mock.patch.object(bd.logger, "warning") as m_warn:
            out = bd._prune_dsl_backups("/some/main.json")
    assert out == []
    m_warn.assert_called_once()


def test_prune_backups_dir_missing_logs_not_silent():
    """留痕是硬契约: 降级路径绝不允许无声 (mock 捕获 warning 必被调用)。"""
    bd = _import_dsl()
    with mock.patch("os.listdir", side_effect=OSError):
        with mock.patch.object(bd.logger, "warning") as m_warn:
            bd._prune_dsl_backups("/nonexistent/x.json")
    assert m_warn.called, "listdir 失败降级必须 logger.warning, 不许无声"


# ── bridge_rules._confirmed_rule_ids: default.json 读失败 → 留痕 + 空集 ───────

def test_confirmed_ids_read_fail_logs_and_returns_empty():
    """default.json 读/解析失败 → logger.warning + 返空 set (行为不变, 加留痕)。"""
    br = _import_rules()
    # _confirmed_rule_ids 内部 `with open(p)...` → mock open 抛 OSError
    with mock.patch("builtins.open", side_effect=OSError("no file")):
        with mock.patch.object(br.logger, "warning") as m_warn:
            out = br._confirmed_rule_ids()
    assert out == set()
    m_warn.assert_called_once()


def test_confirmed_ids_success_not_logged():
    """读成功 → 正常返 confirmed 集, 且不触发 warning (留痕只在降级路径)。"""
    br = _import_rules()

    class _FakeFile:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self):
            return '{"rules": [{"rule_id": "r1", "confirmed": true}, ' \
                   '{"rule_id": "r2", "confirmed": false}]}'

    with mock.patch("builtins.open", return_value=_FakeFile()):
        import json
        # 内部走 json.load(fh), 需让 fh 可被 json.load — 用 fake 有 read() 不行,
        # json.load 需要 file-like with .read(); _FakeFile.read 够, 但 json.load 调 fh.read()
        with mock.patch.object(br.logger, "warning") as m_warn:
            out = br._confirmed_rule_ids()
    assert out == {"r1"}
    m_warn.assert_not_called()


if __name__ == "__main__":
    fns = [
        test_prune_backups_listdir_fail_logs_and_returns_empty,
        test_prune_backups_dir_missing_logs_not_silent,
        test_confirmed_ids_read_fail_logs_and_returns_empty,
        test_confirmed_ids_success_not_logged,
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
