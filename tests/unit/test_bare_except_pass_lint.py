"""
全仓「裸 except: pass」静默吞 lint 护栏

背景: input_parser 轮除根了"硬输入静默空跑"病根, 但要防**未来**有人再写
无意识裸 `except: pass`。本护栏把「全仓普查」固化成 CI 可跑的检查:
  - 用 AST 扫 src/ 全部 .py, 找 `except ... : pass` 且 pass 上方无注释的节点
  - 有注释背书的降级 (如 "# 单文件删失败不影响其余") 是设计契约, 放行
  - 一旦有人加了裸吞, 本测试红 — 逼着要么删要么补注释/日志

判据 (精确, 不误伤 35 处有注释契约):
  1. 必须是 Try 节点的 handler, body 恰为单个 ast.Pass
  2. 该 pass 语句的上一条行若有注释 (同一行行尾注释 / 上一行整行注释) → 放行
  3. 否则 (无注释) → offender

__main__ 直跑护栏: 纯 AST + 读文件, 无 pytest fixture, ASCII print。
范式照 test_doc_test_waterlevel.py (扫源码做护栏, 无 fixture)。
"""
import ast
import glob
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

# 扫描范围: 三个实现子树 (测试/脚本不在"生产静默吞"管辖内)
_SUBTREES = ["src/rules", "src/gui", "src/agents"]


def _iter_src_files():
    for sub in _SUBTREES:
        for path in glob.glob(os.path.join(project_root, sub, "**", "*.py"),
                               recursive=True):
            if "__pycache__" in path:
                continue
            yield path


def find_bare_except_pass(rel_root=None):
    """扫指定子树, 返回 [(file, line)] — 裸 except:pass 且无注释背书的节点。

    返回空列表 = 全仓干净 (当前基线)。CI 跑本函数断言空, 防未来回归。
    """
    root = rel_root or project_root
    offenders = []
    for path in _iter_src_files():
        rel = os.path.relpath(path, root)
        try:
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
        except UnicodeDecodeError:
            continue
        lines = src.split("\n")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                # 该 handler 的 body 恰为单个 ast.Pass
                if len(handler.body) != 1:
                    continue
                p = handler.body[0]
                if not isinstance(p, ast.Pass):
                    continue
                # pass 所在行 = p.lineno; 检查"紧邻注释背书":
                #   同行为注释尾 (x  # note) 或 上一行为整行注释
                pass_line = lines[p.lineno - 1]
                same_line_comment = "#" in pass_line[pass_line.index("pass"):]
                prev_line = lines[p.lineno - 2].strip() if p.lineno >= 2 else ""
                prev_is_comment = prev_line.startswith("#")
                # 有任一注释背书 → 设计降级, 放行
                if same_line_comment or prev_is_comment:
                    continue
                offenders.append((rel, p.lineno))
    return sorted(offenders)


def test_no_bare_except_pass_in_src():
    """全仓三子树无「裸 except: pass 且无注释」— 当前基线必须干净。

    未来谁加了裸吞: 本测试红, 逼其补注释(契约)或 logger(留痕)或删除。
    有注释背书的 35 处设计降级不在此列 (它们不是病根)。"""
    offenders = find_bare_except_pass()
    if offenders:
        detail = "\n".join(f"  {f}:{ln}" for f, ln in offenders)
        assert not offenders, \
            "发现裸 except:pass (无注释契约), 需补注释/logger 或删除:\n" + detail
    print("PASS test_no_bare_except_pass_in_src (全仓 3 子树 0 裸静默吞)")


def test_finder_flags_bare_pass_correctly():
    """lint 判据自测: 裸 pass 被抓, 有注释 pass 被放行 (锁死判据本身)。"""
    import tempfile
    import test_bare_except_pass_lint as _self  # 由 test_direct_run 直跑时可用
    # 临时目录放两个文件验判据
    tmp = tempfile.mkdtemp()
    bare = os.path.join(tmp, "bare.py")
    annotated = os.path.join(tmp, "ann.py")
    with open(bare, "w", encoding="utf-8") as f:
        f.write("try:\n    x()\nexcept Exception:\n    pass\n")
    with open(annotated, "w", encoding="utf-8") as f:
        f.write("try:\n    y()\nexcept Exception:\n    pass  # 设计降级, 契约\n")
    orig_subtrees = _self._SUBTREES[:]
    _self._SUBTREES = [tmp]
    try:
        offs = _self.find_bare_except_pass()
    finally:
        _self._SUBTREES = orig_subtrees
    files = [f.split(os.sep)[-1] for f, _ in offs]
    assert any("bare.py" in f for f in files), "裸 pass 应被抓"
    assert not any("ann.py" in f for f in files), "有注释 pass 应放行"


if __name__ == "__main__":
    test_no_bare_except_pass_in_src()
    test_finder_flags_bare_pass_correctly()
    print("OK: bare except:pass lint guardrail tests passed")
