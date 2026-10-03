# 测试水位 · 单一事实源

> **本文是「当前测试水位」的唯一权威出处。** 推测试水位只改这一处。
> 其他文档（DELIVERY.md / capability-map.md / INDEX.md / README.md）的
> 「当前测试数字」一律**引用本文**，不再各自硬编码（根治历史散落 281/409/419 的同类坑）。
>
> **历史演进记录**（带「本轮基线 / 立项时 / 改前基线」时间戳的段落）
> 是审计痕迹，**不随本文改**——它们是"当时"的水位，不是"当前"。

## 当前水位

```
python -m pytest tests/ -q   →   451 passed / 5 skipped / 0 failed
```

- **测试文件**：53（49 unit + 4 integration；含 2026-10-03 新增的文档水位护栏 test_doc_test_waterlevel）
- **5 skipped**：外部依赖用例（4 条 langgraph 框架需 `AI_CAD_RUN_FRAMEWORK=1`；
  1 条 LLM 需 `AGNES_API_KEY`），非缺陷。
- **冒烟**：`python scripts/smoke_test.py` 秒级验 5 大核心不变量（0.4s）。
- **覆盖率**：`.coveragerc` `fail_under=90`（纯可测代码实测 95%）。

## 刷新方法（推水位后跑这条）

```bash
# 1. 实跑拿权威数字
python -m pytest tests/ -q 2>&1 | tail -1
# 2. 把上面那行数字填进「当前水位」代码块 (只改 451 这处, 别碰历史段落)
```

**约定**：CI / 收口 commit 前，把实跑数字回填到本文「当前水位」段；
**绝不**把带时间戳的历史段落（如 DELIVERY 第 250 行"数据截止 2026-09-30 … 409"）当活数字改。

*最后刷新：2026-10-03 · 451 passed / 5 skipped / 0 failed（对应 commit `4812064` 后 + 文档水位护栏 4 测试）*
