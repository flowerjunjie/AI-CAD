"""
护栏测试：固化「测试文件可直接 python 直跑」这一能力。

背景：前几轮反复踩的坑 — 测试文件的 __main__ 块里 print 中文/emoji 在
Windows GBK 终端崩, 或某处断言依赖别的测试文件先填充全局引擎, 导致
`pytest` 全绿但 `python 文件` 直跑炸。此前全靠人肉手动逐个直跑验证。
本测试把该能力固化: 每个可直跑的 unit 测试文件 subprocess 起来, 断言 exit 0。

不测 integration/ (test_agent_graph/test_end_to_end 依赖真实 LLM/DWG, 直跑
本就不该 exit 0, 不在护栏范围内)。
"""
import glob
import os
import subprocess
import sys

import pytest

# 本文件在 tests/unit/ 下 — 3 层 dirname 回项目根 (unit→tests→AI-CAD)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _direct_run_candidates() -> list[str]:
    """只挑「带 __main__ 块、且在 tests/unit 下」的文件 — 可被 python 直跑。"""
    pattern = os.path.join(PROJECT_ROOT, "tests", "unit", "test_*.py")
    out = []
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as fh:
            if 'if __name__ == "__main__"' in fh.read():
                out.append(path)
    return out


def test_all_unit_test_files_direct_run_exit_0():
    """每个可直跑的 unit 测试文件, 独立 subprocess 跑起来 exit 必须为 0。

    这是把「直跑不炸」固化成回归: 任何人改了某个文件的 __main__ 块
    (比如 print 了 emoji / 断言依赖全局引擎填充), pytest 会在这里先炸,
    而不是等到有人手动 python 那个文件才暴露。
    """
    cands = _direct_run_candidates()
    assert cands, "没找到可直跑的 unit 测试文件 — 护栏本身坏了"
    failures = []
    for path in cands:
        # 从项目根起, 隔离 subprocess 的 CWD; PYTHONPATH 保证 import src.* 通
        env = dict(os.environ, PYTHONPATH=PROJECT_ROOT)
        r = subprocess.run([sys.executable, path],
                           capture_output=True, text=True, env=env,
                           cwd=PROJECT_ROOT, timeout=120)
        if r.returncode != 0:
            failures.append(f"{os.path.basename(path)} (exit {r.returncode}):\n{r.stderr[-800:]}")
    assert not failures, "以下测试文件直跑失败:\n" + "\n\n".join(failures)
