"""
src 带 __main__ Demo 段文件的 import 路径完整性护栏 (机制层自主子集)

背景 (doors.py:105 隐患固化): src/rules/src/residential/doors.py 的 __main__
Demo 段写 `from src.rules.engine import get_engine` (少 .src), 同文件 L6 却是
`src.rules.src.engine` — 一跑 Demo 就 ImportError。它没暴露是因为 test_direct_run
只扫 tests/ 下的文件, 从不直跑 src 里带 __main__ 的模块。本护栏把「src 里带
__main__ 段的文件, 其 demo 段 import 路径能真解析」锁死, 防下次再写错 import。

判据: 找 src/** 里含 `if __name__ == "__main__"` 的 .py, 取其 __main__ 段内所有
`from X import ...` / `import X`, 逐个 assert 该模块路径能被 importlib 解析到
(真在 sys.path 里), 不存在的静默 import 直接 FAIL。
纯 AST + importlib.util.find_spec, 无 pytest fixture, 可直跑。ASCII print。
范式照 test_bare_except_pass_lint.py (扫 src/ 做护栏)。
"""
import ast
import glob
import importlib.util
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

_SUBTREES = ["src/agents", "src/gui", "src/rules"]


def _main_block_imports(src):
    """取 __main__ 段内的 from/import 目标模块名列表。"""
    tree = ast.parse(src)
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and "__name__" in ast.unparse(node.test):
            for st in node.body:
                if isinstance(st, ast.ImportFrom) and st.module:
                    mods.append(st.module)
                elif isinstance(st, ast.Import):
                    mods.extend(a.name for a in st.names)
    return mods


def find_broken_main_imports():
    """扫 3 子树, 返回 [(file, module, lineno)] — __main__ 段里解析不到的 import。

    空 = 全仓 Demo 段 import 路径干净 (当前基线)。"""
    offenders = []
    for sub in _SUBTREES:
        for path in glob.glob(os.path.join(project_root, sub, "**", "*.py"),
                               recursive=True):
            if "__pycache__" in path:
                continue
            src = open(path, encoding="utf-8").read()
            if "__main__" not in src:
                continue
            rel = os.path.relpath(path, project_root)
            for mod in _main_block_imports(src):
                if importlib.util.find_spec(mod) is None:
                    offenders.append((rel, mod))
    return sorted(offenders)


def test_no_broken_main_block_imports_in_src():
    """全仓 3 子树 __main__ 段的 import 路径必须能真解析 (doors.py:105 型隐患锁死)。"""
    offenders = find_broken_main_imports()
    if offenders:
        detail = "\n".join(f"  {f}: import {m}" for f, m in offenders)
        assert not offenders, \
            "src 里 __main__ Demo 段有解析不到的 import (doors.py:105 型), 需修正:\n" \
            + detail
    print("PASS test_no_broken_main_block_imports_in_src (全仓 Demo 段 import 0 断链)")


def test_main_block_import_scanner_flags_broken():
    """判据自测: 造一个 __main__ 段 import 不存在模块的文件, 扫得到; 正常文件扫不到。"""
    import tempfile
    tmp = tempfile.mkdtemp()
    bad = os.path.join(tmp, "bad.py")
    good = os.path.join(tmp, "good.py")
    with open(bad, "w", encoding="utf-8") as f:
        f.write('if __name__ == "__main__":\n'
                '    from src.rules.engine import get_engine  # 故意断链\n')
    with open(good, "w", encoding="utf-8") as f:
        f.write('if __name__ == "__main__":\n'
                '    import sys\n    print(sys.argv)\n')
    import test_broken_main_import_guard as _self
    orig = _self._SUBTREES[:]
    _self._SUBTREES = [tmp]
    try:
        offs = [m for _, m in _self.find_broken_main_imports()]
    finally:
        _self._SUBTREES = orig
    # bad 的断链模块 (src.rules.engine, 少 .src) 应被抓; good 的 sys 不应
    assert "src.rules.engine" in offs, "断链的 __main__ import 应被抓"
    assert "sys" not in offs, "合法 import (sys) 不应误伤"


if __name__ == "__main__":
    test_no_broken_main_block_imports_in_src()
    test_main_block_import_scanner_flags_broken()
    print("OK: broken __main__ import guardrail tests passed")
