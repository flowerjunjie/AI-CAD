"""
全仓「静默缺省值降级」lint 护栏 (接 input_parser 轮 + 静默缺省值普查轮)

病根族: 异常被吞后不 raise 不留痕, 悄悄 return 一个「歧义缺省值」
(空 list / 空 set / 0 / None), 下游拿到以为正常, 实则上游炸了。
input_parser 轮除根了「输入层」, 本轮把判据固化成 CI, 守全仓。

判据 (一个 except->return 缺省值「安全」当且仅当满足其一):
  ① return 体含「失败信号」— ok:False / 错误列表 / issues / reason / error
     (调用方能从返回值本身判断出失败, 非歧义)
  ② 紧邻注释背书 — 上一行整行注释 或 当前 return 行尾注释 (契约写明降级理由)
  ③ handler 体含 logger.* 留痕 (降级但记了 warning/error, 看得见)
都不满足 + return 的是「歧义缺省值」(list/set/dict 字面空值 或 裸 0/0.0/None/True)
→ offender。

基线: 当前 7 处 (上轮人工裁定 5 + 本轮补 logger 2) 全被 ①/②/③ 放行,
     CI 断言 0 offender。未来谁写裸 `except: return []` 不带信号/注释/logger → 红。

__main__ 直跑护栏: 纯 AST + 读文件, 无 fixture, ASCII print。
范式照 test_bare_except_pass_lint.py (同骨架 _iter, 判据独立 — 单一职责)。
"""
import ast
import glob
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

_SUBTREES = ["src/rules", "src/gui", "src/agents"]

# ① 失败信号: return 体出现这些 → 调用方能判断失败, 非歧义缺省值
_FAIL_SIGNALS = [
    "False", "None", "error", "Error", "issue", "reason", "ok", "valid",
    "fail", "Fail", "consist", "DslJsonError", "HTTPException",
]


def _iter_src_files():
    for sub in _SUBTREES:
        for path in glob.glob(os.path.join(project_root, sub, "**", "*.py"),
                               recursive=True):
            if "__pycache__" in path:
                continue
            yield path


def _is_ambiguous_default(ret_val) -> bool:
    """return 体是否为「歧义缺省值」— 空容器字面量 或 裸标量默认。"""
    if ret_val is None:          # bare `return`
        return False             # bare return 不是 return 缺省值, 交给别判据
    # 空容器字面量: [] {} set()  (list/set/dict 无参)
    if isinstance(ret_val, ast.Dict) and not ret_val.keys:
        return True
    if isinstance(ret_val, ast.List) and not ret_val.elts:
        return True
    if isinstance(ret_val, ast.Set) and not ret_val.elts:
        return True
    # set() 无参调用
    if isinstance(ret_val, ast.Call) and isinstance(ret_val.func, ast.Name) \
            and ret_val.func.id in ("set", "list", "dict") and not ret_val.args:
        return True
    # 裸标量默认: 0 / 0.0 / True (常量) — 歧义: 0 可能"真 0"也可能"读失败兜底"
    if isinstance(ret_val, ast.Constant):
        return ret_val.value in (0, 0.0, True)
    return False


def _handler_has_log(handler) -> bool:
    """③ handler 体是否含 logger.* / logging.* 留痕调用。"""
    for node in ast.walk(handler):
        if isinstance(node, ast.Call):
            f = node.func
            # logger.warning(...) / logger.error(...) / logging.warning(...)
            if isinstance(f, ast.Attribute) and f.attr in (
                "warning", "error", "critical", "info", "debug", "exception"):
                return True
    return False


def _nearby_comment(lines, ret_line) -> bool:
    """② return 行尾注释 或 紧邻上一行为整行注释。"""
    same = lines[ret_line - 1]
    same_comment = "#" in same[same.find("return"):]
    prev = lines[ret_line - 2].strip() if ret_line >= 2 else ""
    return same_comment or prev.startswith("#")


def find_silent_default_returns() -> list:
    """扫 3 子树, 返回 [(file, line, snippet)] — 静默缺省值降级 offender。

    空 = 全仓干净 (当前基线)。CI 断言空, 防未来回归。"""
    offenders = []
    for path in _iter_src_files():
        rel = os.path.relpath(path, project_root)
        try:
            src = open(path, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
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
                if len(handler.body) != 1:
                    continue
                r = handler.body[0]
                if not isinstance(r, ast.Return):
                    continue
                if not _is_ambiguous_default(r.value):
                    continue
                # 放行条件 ①②③ 任一满足 → 安全
                ret_snippet = "\n".join(lines[max(0, r.lineno - 1): (r.end_lineno or r.lineno) + 1])
                has_signal = any(s in ret_snippet for s in _FAIL_SIGNALS)
                if has_signal or _nearby_comment(lines, r.lineno) or _handler_has_log(handler):
                    continue
                offenders.append((rel, r.lineno, ret_snippet.strip().split("\n")[0][:50]))
    return sorted(offenders)


def test_no_silent_default_return_in_src():
    """全仓 3 子树无「静默缺省值降级」— 当前基线必须 0 offender。

    未来谁写 `except: return []` 不带失败信号/注释/logger → 本测试红。"""
    offenders = find_silent_default_returns()
    if offenders:
        detail = "\n".join(f"  {f}:{ln}  {s}" for f, ln, s in offenders)
        assert not offenders, \
            "发现静默缺省值降级 (无信号/注释/logger), 需补其一:\n" + detail
    print("PASS test_no_silent_default_return_in_src (全仓 3 子树 0 静默缺省值)")


def test_finder_judges_bare_default_correctly():
    """判据自测: 裸 `except: return []` 被抓, 带 logger/注释/信号的放行。

    锁死判据本身 — 不写这测试, 判据误伤/漏网都发现不了。"""
    import tempfile
    tmp = tempfile.mkdtemp()
    cases = {
        # 裸缺省值 → 应被抓
        "bare.py": "def f():\n    try:\n        return load()\n    except Exception:\n        return []\n",
        # 有 logger → 放行
        "logged.py": "import logging\nlog=logging.getLogger('x')\n"
                     "def f():\n    try:\n        return load()\n"
                     "    except Exception:\n        log.warning('x')\n        return []\n",
        # 有注释背书 → 放行
        "commented.py": "def f():\n    try:\n        return load()\n"
                        "    except Exception:\n        # 无缓存=返空, 契约\n        return []\n",
        # 带失败信号 → 放行
        "signaled.py": "def f():\n    try:\n        return load()\n"
                       "    except Exception:\n        return {'ok': False, 'items': []}\n",
    }
    for name, body in cases.items():
        with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
            fh.write(body)
    # 临时把扫描骨架指向 tmp
    orig = _SUBTREES[:]
    _SUBTREES[:] = [tmp]
    try:
        offs = [f.split(os.sep)[-1] for f, _, _ in find_silent_default_returns()]
    finally:
        _SUBTREES[:] = orig
        for name in cases:
            os.unlink(os.path.join(tmp, name))
    assert "bare.py" in offs, "裸 except:return [] 应被抓"
    for ok in ("logged.py", "commented.py", "signaled.py"):
        assert ok not in offs, f"{ok} 有背书/信号应放行"


if __name__ == "__main__":
    test_no_silent_default_return_in_src()
    test_finder_judges_bare_default_correctly()
    print("OK: silent default-return lint guardrail tests passed")
