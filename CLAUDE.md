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

## 重构纪律（物理搬文件前必做，2026-10-08 固化）
- **物理搬模块/段到子文件前，先 grep 谁在 patch/引用被搬的模块级符号（含测试的
  monkeypatch），搬家后全量必绿才 commit**——2026-10-08 拆 bridge.py H 段时把
  模块级 `_COLLAB_STATE_PATH` 随段体搬走，测试 `monkeypatch bridge._COLLAB_STATE_PATH`
  的 patch 目标直接悬空（端点读子模块的值，patch 打偏），撞出 9 个回归 + 误 push 带病状态。
  教训：任何"物理搬家"必须**先拉通隐式契约**（测试 monkeypatch / 模块级全局被跨段引用），
  再动手；单一事实源留在测试契约的稳定位置（如 bridge.py），子模块运行时惰性读。
- **判定"段是否自包含"要 grep 跨段函数引用，不能只看段内 import**——bridge.py F 段
  定义了 `_load_sample_raw`，但 B 段 `api_rules_batch_verify`（L333）也跨段引用它，
  看似"只调工具库"的 F 段实际非自包含，拆它须先处理这条跨段依赖（H 段能"段间 0 交叉"
  纯物理搬，F 段不能照搬）。

## 打包 / 长任务纪律（2026-09-30 固化）
- **重打包 exe 前必须先刷新前端**：`cd src/client && npm run build`（产物落 `src/dist`，
  非 `src/client/dist`——vite `outDir: '../dist'` 上移一层）。旧 dist 打进去 = 界面里没有新面板。
- **PyInstaller 长构建放后台就等完成通知，不轮询、不手停**——手停会留残留
  `ai_cad_gui.exe` 进程锁 `_internal/*.pyd`，下次构建 COLLECT 阶段 `rmtree` 报 WinError 5。
  遇文件锁先 `taskkill` 残留 exe + 删整个 `build/dist/ai_cad_gui` 再重跑。
- **改懒 import 的新模块要同步补 `build_exe.py` 的 `HIDDEN_IMPORTS`**（如 M4/M5 的
  `clash_detection`/`conflict_detection`）——`tools` 是命名空间包，PyInstaller 静态分析
  追不到，不显式列则 exe 运行时 ModuleNotFoundError（开发态正常、打包态才炸的坑）。
  **精确判定（2026-10-08 固化，防误判"该不该补"）**：先分清包性质再决定——
  - **命名空间包**（目录无 `__init__.py`，如 `src/agents/src/tools/`）：静态分析追不到
    跨目录懒 import，**必须**列进 HIDDEN_IMPORTS。
  - **普通包**（有 `__init__.py`，如 `src/rules/src/`）：整包被 PyInstaller 追进 PYZ，
    包内成员（`diff.py` 等）自动进，**不必**单列某文件——但前提是该成员自身**不懒 import
    命名空间包**（若 `diff.py` 内部 `from ...tools import x`，那 x 仍要补）。
  拿不准就**起 exe 真调一次该端点**验证（红线二：验证再归因，别猜"会不会炸"）——
  2026-10-08 曾据误判要补 `src.rules.src.diff`，实测 `/api/rules/dsl/apply` 真透出
  `diff_consistent`，证明普通包成员无需补 spec，避免白改。
- 前端 `vite.config` 已开 `emptyOutDir`（outDir 在根外默认不清空会堆积历史 bundle 进 exe）。

## 诚实边界（不虚标，留给人）
- M1 结构/给排水数值、M2 DWG 图层约定、M5 权限模型 = **外部依赖**。
  机制已通、值/约定待专家与业务回填，**不要替专家把占位翻成 confirmed=true**。
