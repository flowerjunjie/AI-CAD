"""
DSL 备份轮转 (机制层自主子集) 测试

背景: /api/rules/dsl/apply 与 /api/rules/backfill 每写盘前 copy 出
default.json.bak.<ts> 但**从不删旧备份** (apply 仅写盘失败分支 unlink, 写成功
则备份永久留下; backfill 连失败分支都没清) — 全仓无 .bak. 清理逻辑, 每应用/
回填一次磁盘就多一个永不清理的文件。_prune_dsl_backups 抽成统一轮转: 保留最近
keep 个, 按文件名时间戳排序删旧的。防 .bak. 无界堆积, 同时不破坏「可回滚」护栏
(保留 N 个, 非删光)。

红线对齐 (CLAUDE.md 不虚标): 只清 default.json 的 .bak. 备份文件, 不碰 default.json
本体 / 不碰 M1 业务值。纯机制 (备份生命周期), 仿 test_bridge_rules_dsl_apply 范式:
__main__ 只列无 fixture 子集 + 不 print 中文/emoji (Windows GBK 直跑不崩)。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _prune(tmp, name):
    """造 name 个 default.json.bak.<ts> 备份 + 主文件, 跑轮转, 返回剩余备份数。"""
    from src.gui import bridge
    main = os.path.join(tmp, "default.json")
    with open(main, "w", encoding="utf-8") as fh:
        fh.write("{}")
    for i in range(name):
        with open(os.path.join(tmp, f"default.json.bak.2026010{i:06d}"),
                  "w", encoding="utf-8") as fh:
            fh.write("{}")
    removed = bridge._prune_dsl_backups(main, keep=_KEEP)
    left = [f for f in os.listdir(tmp) if f.startswith("default.json.bak.")]
    return len(left), len(removed), main


# 默认保留窗口 (与 bridge._DSL_BACKUP_KEEP 一致, 测试用较小值便于造样本)
_KEEP = 3


def test_prune_keeps_most_recent_n():
    """造 6 个备份, keep=3 → 只删 3 个旧的 (时间戳 00000-00002), 保留最新 3 个
    (00003-00005), 主文件 default.json 不被轮转误删。"""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        left, removed, main = _prune(tmp, 6)
        assert left == 3, f"keep=3 应保留 3 个, 得 {left}"
        assert removed == 3, f"应删 3 个旧的, 得 {removed}"
        # 主文件 default.json 不被轮转误删 (红线一: 不留坏盘护栏破了)
        assert os.path.exists(main), "轮转误删了主文件"
        # 保留的是时间戳最新的 3 个 (文件名降序, 删的是最小的 3 个)
        kept = sorted(f for f in os.listdir(tmp) if f.startswith("default.json.bak."))
        assert kept == [f"default.json.bak.2026010{n:06d}" for n in (3, 4, 5)], kept


def test_prune_within_keep_noop():
    """备份数 ≤ keep → 不删任何 (returned removed=0), 全保留。"""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        left, removed, _ = _prune(tmp, 2)
        assert left == 2 and removed == 0


def test_prune_no_backups_no_crash():
    """无任何备份 → 不崩, removed=0, 主文件仍在。"""
    import tempfile
    from src.gui import bridge
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "default.json")
        with open(main, "w", encoding="utf-8") as fh:
            fh.write("{}")
        assert bridge._prune_dsl_backups(main, _KEEP) == []
        assert os.path.exists(main)


def test_prune_ignores_non_bak_files():
    """同目录非 default.json.bak. 前缀的文件 (如 default.json.bak2 / 其他.json)
    不被轮转误删 — 只认 .bak. 严格前缀。"""
    import tempfile
    from src.gui import bridge
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "default.json")
        with open(main, "w", encoding="utf-8") as fh:
            fh.write("{}")
        # 干扰项: 前缀相似但不是 .bak. 备份 / 无关 json
        for n in ("default.json.bakX", "other.json", "default.json"):
            with open(os.path.join(tmp, n), "w", encoding="utf-8") as fh:
                fh.write("{}")
        # 造 5 个真备份, keep=2 → 只删 3 个真备份, 干扰项全留
        for i in range(5):
            with open(os.path.join(tmp, f"default.json.bak.{i:09d}"),
                      "w", encoding="utf-8") as fh:
                fh.write("{}")
        bridge._prune_dsl_backups(main, 2)
        assert os.path.exists(os.path.join(tmp, "default.json.bakX")), "误删了非备份文件"
        assert os.path.exists(os.path.join(tmp, "other.json"))
        left = [f for f in os.listdir(tmp) if f.startswith("default.json.bak.")]
        assert len(left) == 2, f"keep=2 应留 2 真备份, 得 {left}"


def test_prune_missing_dir_no_crash():
    """main_path 所在目录不存在 → 优雅降级 (返回 [] 不崩)。"""
    from src.gui import bridge
    assert bridge._prune_dsl_backups("/nonexistent/dir/default.json", _KEEP) == []


if __name__ == "__main__":
    # 只跑无 pytest fixture 依赖的用例 (test_direct_run 会直跑 __main__ 块)
    test_prune_keeps_most_recent_n()
    test_prune_within_keep_noop()
    test_prune_no_backups_no_crash()
    test_prune_ignores_non_bak_files()
    test_prune_missing_dir_no_crash()
    print("OK: all _prune_dsl_backups tests passed")
