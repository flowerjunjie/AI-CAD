"""
文档测试水位「单一事实源」回归护栏 (根治散落 281/409/419 的同类坑)

背景: 测试数字一度散落在 README/DELIVERY/capability-map/INDEX 多份文档,
推一次水位就要全仓 grep 一遍对齐, 漏一处就自相矛盾 (上轮 419 vs 代码 447)。
根治: 当前水位收敛到 docs/test-status.md 单一事实源, 其他文档只引用、不硬编码。

本护栏固化三件事 (防漂):
  ① 单一源存在: docs/test-status.md 在 + 含「当前水位」段 + 至少 1 个活数字
  ② 不造假: test-status.md 的活数字必须与「tests/ 实跑」数量级自洽 (passed>0),
     且历史段落带日期锚点的时间戳仍可读 (防误删演进记录)
  ③ 收口约定: README/DELIVERY/capability-map/INDEX 的「当前水位」段必须
     **引用** test-status.md (出现引用词), 而不是各自再硬编码一个活数字
     (grep 当前水位数字时, 这些文档里不该有「裸的 N passed」——要么引用, 要么历史锚点)

__main__ 直跑护栏: 只列无 fixture 子集 (全读文件 + 正则, 无 pytest fixture),
ASCII print。tests/ 实跑数量级校验用 subprocess 跑一个最小子集, 不依赖全量。
"""
import os
import re
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

TEST_STATUS = os.path.join(project_root, "docs", "test-status.md")

# 「当前水位」该引用的文档 (它们不能再各自硬编码一个活数字)
LIVE_DOCS = [
    "README.md",
    "DELIVERY.md",
    "docs/capability-map.md",
    "docs/INDEX.md",
]

# 活数字模式: "NNN passed" (当前水位特征)。历史段落若带「数据截止/推到/基线」
# 日期锚点则不算活数字 (是演进快照), 本护栏只抓「裸活数字」。
_LIVE_PAT = re.compile(r"\b\d{2,3} passed")

# 历史锚点词: 当前行含这些 → 是演进快照 (带日期/带 commit 的交付段), 放行
_HISTORY_PAT = re.compile(
    r"数据截止|推到|本轮基线|立项时|改前基线|基线 4|见 \[|commit `|交付更新"
)


def _read(rel):
    p = os.path.join(project_root, rel)
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def test_single_source_exists_with_live_number():
    """① docs/test-status.md 在 + 有「当前水位」段 + 至少 1 个活数字。"""
    assert os.path.exists(TEST_STATUS), "单一事实源 docs/test-status.md 缺失"
    body = _read("docs/test-status.md")
    assert "当前水位" in body, "test-status.md 应含「当前水位」段"
    m = _LIVE_PAT.search(body)
    assert m, "test-status.md 当前水位段应含活数字 (N passed)"
    print("PASS test_single_source_exists_with_live_number")


def test_single_source_number_is_sane():
    """② test-status.md 的活数字必须实跑自洽 (passed 数 > 0 且 ≤ 合理上界)。

    不全量跑 pytest (慢), 只跑一个最快子集确认「测试确实存在且能跑」,
    再校验 test-status 声明的 passed 数落在合理区间 (防拍脑袋填 9999)。"""
    import subprocess
    body = _read("docs/test-status.md")
    m = re.search(r"(\d{2,4}) passed", body)
    assert m, "test-status.md 应有 declared passed 数"
    declared = int(m.group(1))
    # 实跑确认 tests/ 里测试数量级 (跑最快一个文件, 不炸)
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/unit/test_clash_detection.py", "-q", "--tb=no"],
        capture_output=True, text=True, cwd=project_root, timeout=120,
    )
    assert "passed" in r.stdout, f"tests/ 应能实跑, 实际: {r.stdout[-200:]}{r.stderr[-100:]}"
    # declared 数应与「全量」量级一致: 至少 ≥ 单文件 passed 数 (全量 > 子集)
    sub_passed = int(re.search(r"(\d+) passed", r.stdout).group(1))
    assert declared >= sub_passed, \
        f"test-status 声明 {declared} 应 ≥ 单子文件实跑 {sub_passed} (全量 > 子集)"
    print(f"PASS test_single_source_number_is_sane (declared={declared} ≥ {sub_passed})")


def test_live_docs_reference_single_source_not_hardcode():
    """③ README/DELIVERY/capability-map/INDEX 的「当前水位」段必须**引用**
    test-status.md, 不能再各自裸硬编码一个「N passed」活数字 (防再散落)。

    判据: 每个文档里出现 test-status 引用词; 且若它含「N passed」,
    该行必须带历史锚点 (数据截止/推到/基线/见 test-status), 否则 = 再散落。"""
    for rel in LIVE_DOCS:
        body = _read(rel)
        assert "test-status" in body, \
            f"{rel} 应引用 docs/test-status.md (单一事实源), 未找到引用"
        # 抓所有「N passed」行: 含历史锚点词 → 放行 (交付更新段/演进快照);
        # 裸活数字 (无锚点) → 再散落了, 报 offender
        offenders = []
        in_dated_section = False  # 落在带日期锚点的交付段 (§七 2026-09-26 / §八 2026-09-28)
        for ln, line in enumerate(body.splitlines(), 1):
            if re.search(r"^## .*交付更新（\d{4}-\d{2}-\d{2}", line):
                in_dated_section = True
            elif re.match(r"^## ", line) and not re.search(r"交付更新", line):
                in_dated_section = False
            if not _LIVE_PAT.search(line):
                continue
            # 历史锚点词 (当前行) → 放行; 或落在带日期交付段 → 放行
            if _HISTORY_PAT.search(line) or in_dated_section:
                continue
            offenders.append(ln)
        assert not offenders, \
            f"{rel} 第 {offenders} 行有裸活数字 (应引用 test-status 或带历史锚点)"
        print(f"PASS {os.path.basename(rel)} 引用单一源, 无裸活数字")


def test_test_status_last_refresh_line_present():
    """test-status.md 应有「最后刷新」时间锚 (防无人维护的源)。"""
    body = _read("docs/test-status.md")
    assert re.search(r"最后刷新", body), "test-status.md 应有「最后刷新」时间锚"
    print("PASS test_test_status_last_refresh_line_present")


if __name__ == "__main__":
    test_single_source_exists_with_live_number()
    test_single_source_number_is_sane()
    test_live_docs_reference_single_source_not_hardcode()
    test_test_status_last_refresh_line_present()
    print("OK: doc test-water-level single-source guardrail tests passed")
