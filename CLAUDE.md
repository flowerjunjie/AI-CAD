# AI-CAD · 项目级指令（Claude Code 会话自动加载）

> 全局 Ruflo 规则见 `E:\workspace0525\CLAUDE.md`。本文件只放**本项目特有**的坑与约定，
> 让每个会话/agent 开工就看见，不靠人肉口口相传。

## 测试基建陷阱（2026-09-28 固化）

### `test_direct_run.py` 会直跑每个带 `__main__` 块的 unit 测试文件
`tests/unit/test_direct_run.py` 把所有「带 `if __name__ == "__main__"` 的
`tests/unit/test_*.py`」逐个独立 subprocess 直跑，断言 exit 0。两条硬约束：

- **`__main__` 块里不能调用带 pytest fixture 的用例**（`monkeypatch` / `tmp_path` /
  `capsys` 等）——直跑没有 fixture 注入，调了直接 `TypeError`，全量 pytest 炸 1 条。
  `__main__` 只列无 fixture 子集。
- **`__main__` 里不要 print 中文 / emoji**——Windows GBK 终端会崩编码。用 ASCII。

新增 unit 测试若要可直跑，照 `test_bridge_clash_conflict.py` / `test_clash_detection.py`
的 `__main__` 范式写。

## 验证纪律（收口/改核心文件后必做）
- 起桥验端点前先 `SO_REUSEADDR` 探空闲端口——**旧桥进程常占着 8642**，直接 curl
  打到旧进程会全 404，误判"新端点没生效"。
- 收口/重构后必跑全量 `python -m pytest tests/ -q` + `python scripts/smoke_test.py`，
  贴真实数字才交付（红线一：没有输出的完成叫自嗨）。

## 诚实边界（不虚标，留给人）
- M1 结构/给排水数值、M2 DWG 图层约定、M5 权限模型 = **外部依赖**。
  机制已通、值/约定待专家与业务回填，**不要替专家把占位翻成 confirmed=true**。
