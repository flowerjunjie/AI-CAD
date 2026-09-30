# AI-CAD — 智能体施工图深化系统

> **定位**：工业级 AI Agent 系统，辅助建筑师完成施工图深化阶段的重复性工作  
> **核心原则**：规则引擎保准确 + LLM保灵活 + 人在回路保可控  
> **当前阶段**：Phase 0-3 全部收口 + M3 出图深化 ✅ + M4 多专业碰撞检测 ✅ + M5 改动冲突检测 ✅；M1 数值终确认 / M2 图层约定 / M5 权限模型 仍为外部依赖占位 ▢  
> **创建日期**：2026-09-09 · **最后更新**：2026-09-28（M3出图深化 + M4碰撞 + M5冲突 + 双击exe交付物 + 352测试）

---

## 📋 项目概述

这不是"AI 画图"工具，而是 **AI 辅助施工图深化 Agent**——基于人类方案，由 AI 完成规则化、重复性的深化工作。

| 维度 | 描述 |
|------|------|
| 产品形态 | 桌面端应用（FastAPI 桥 + React 面板，PyInstaller 打包成双击 exe 交付） |
| 目标用户 | 建筑设计院施工图设计师 |
| 核心价值 | 将设计师 80% 的重复性工作时间（标注、材料表、规范检查）自动化 |
| 人机协作模式 | 人在回路——每个关键节点暂停等待确认，AI 不直接出图 |
| 第一版范围 | 建筑专业 · 住宅套型施工图 |

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                界面层 (React 面板 + FastAPI 桥, PyInstaller 打包) │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ CAD编辑器 │  │ 图元预览  │  │ 规则面板  │  │ 成果导出  │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
│       └──────────────┴──────────────┴──────────────┘         │
│                         │                                    │
│              ┌──────────▼──────────┐                         │
│              │    Agent 编排引擎    │                         │
│              │  (任务分解→执行→验证) │                         │
│              └──────────┬──────────┘                         │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────┐             │
│  │           核心能力模块池                      │             │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐     │             │
│  │  │ CAD引擎   │ │ 规则引擎  │ │ 对话引擎  │     │             │
│  │  │(ezdxf+COM)│ │(规范校验) │ │(LLM)    │     │             │
│  │  └──────────┘ └──────────┘ └──────────┘     │             │
│  └─────────────────────────────────────────────┘             │
│                         │                                    │
│  ┌─────────────────────────────────────────────────┐         │
│  │              知识层                               │         │
│  │  ChromaDB(本地) + SQLite(图元库) + 规范文档        │         │
│  └─────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 目录结构

> 对照实际文件（非旧版规划）。核心引擎为 Python（ezdxf + LangGraph），`src/gui` 是 FastAPI 桥 + React 面板。

```
AI-CAD/
├── run.py                  # 全链路入口：--no-llm 快验 / --llm 出图+渲染
├── start_gui.py            # 开发态 GUI（FastAPI 桥 + 浏览器面板，端口 3000）
├── start_gui.bat           # Windows 双击起开发态 GUI
├── start.bat               # 命令行一键（自动装依赖 + 跑全链路 + 弹户型图）
├── make_desktop_shortcut.bat   # 生成桌面 .lnk 快捷方式
├── build/dist/ai_cad_gui/  # 双击 exe 交付物（无 node/源码也能跑）
│   ├── ai_cad_gui.exe      # 双击即开，自动起桥 + 浏览器弹面板
│   └── _internal/         # 引擎 + 桥 + 前端 dist + data/sample (含 default.json)
├── src/
│   ├── agents/             # Python Agent 核心（LangGraph）
│   │   └── src/
│   │       ├── graph.py            # Agent 图定义
│   │       ├── layout.py / numbering.py
│   │       ├── nodes/             # 意图/解析/规则回写 节点
│   │       └── tools/             # 工具池
│   │           ├── cad_tools.py         # ezdxf 读/写 + 上游解析
│   │           ├── clash_detection.py   # M4 多专业碰撞检测（纯函数几何库）
│   │           ├── conflict_detection.py # M5 改动冲突检测（两稿 raw 比对）
│   │           ├── llm_adapter.py       # LLM 工厂（Agnes/MiniMax/Kimi/GLM）
│   │           ├── rag_tools.py         # ChromaDB 本地 RAG
│   │           ├── wall_topology.py     # 墙体拓扑
│   │           └── {plumbing,electrical,hvac,structural}_extractor.py
│   ├── gui/bridge.py       # FastAPI 桥（/api/* 端点，M4/M5 端点在此）
│   ├── client/             # React 面板（Vite，构建产物落 src/dist）
│   ├── rules/              # 建筑规范规则库
│   │   └── src/
│   │       ├── dsl.py / engine.py / baselines.py / batch_check.py / diff.py
│   │       └── {residential,fire_safety,accessibility,plumbing,electrical,hvac,structural}
│   └── server/             # Node 后端（package.json + src/api）
├── config/                 # agents.yaml / app.json
├── data/                   # baselines / sample / chroma_db（default.json 样本）
├── scripts/
│   ├── smoke_test.py       # 秒级冒烟（5 大核心不变量）
│   ├── ai_cad_cli.py       # 命令行（列规则等）
│   ├── build_exe.py / verify_exe.py   # 打包 + 端到端验证
│   └── render_floorplan.py / seed_rag.py
├── tests/                  # 43 个测试文件（unit + integration）
├── docs/                   # 设计文档（capability-map.md / architecture.md / phases.md …）
├── doc/                    # 原始需求文档（合作方案）
├── DELIVERY.md             # 交付报告（决策者主文档）
└── README.md
```

---

## 🚀 快速开始

三条入口，按"要不要装环境"选：

| 入口 | 适用 | 说明 |
|------|------|------|
| **双击 exe 交付物** | 无 node / 无工程源码的机器 | `build/dist/ai_cad_gui/ai_cad_gui.exe`，双击即开专业面板（自动起桥 + 浏览器弹出，端口自动探测） |
| **start_gui.py 起 GUI** | 开发态，有 node/vite | `python start_gui.py`（或双击 `start_gui.bat`），FastAPI 桥 + Vite 面板（端口 3000） |
| **start.bat 命令行** | 全链路验证 / 出图 | 自动装依赖 + 跑 `run.py` + 弹户型图 |

### ① 双击 exe 交付物（交付态，推荐给最终用户）

```
build/dist/ai_cad_gui/
├── ai_cad_gui.exe          # 双击即开, 自动起桥 + 浏览器开 http://127.0.0.1:<port>
└── _internal/             # 引擎 + 桥 + 前端 dist + data/sample (含 default.json)
```

- 构建：`python scripts/build_exe.py`（首次 ~5 min）
- 端到端验证：`python scripts/verify_exe.py`（起 exe → /api/health → 面板 → confirmed 透出，全绿 PASS）

### ② start_gui.py 起 GUI 面板（开发态）

```bash
python start_gui.py        # 或双击 start_gui.bat
# 起 FastAPI 桥 (127.0.0.1, 端口自动探测) + Vite dev (端口 3000), 浏览器自动弹出
```

### ③ 命令行一键（全链路出图）

双击或命令行运行 `start.bat`，自动装依赖 + 跑全链路 + 弹出户型图：

```bat
start.bat            全流程含 LLM (联网, 出图+自动弹窗口型图)
start.bat no-llm     纯本地快验 (不联网, 秒级确定结果)
```

想在桌面放一个图标？双击 `make_desktop_shortcut.bat` 即可生成 `.lnk`。

### 命令行（手动）

### 环境要求

- Python >= 3.11（核心引擎）
- Node.js >= 18（仅 GUI 开发态 / 前端构建需要；exe 交付态不需要）
- AutoCAD 2020+（可选，用于 COM 接口测试）

### 安装

```bash
# Agent 核心依赖
pip install -r src/agents/requirements.txt

# 前端（仅 GUI 开发态）
cd src/client && npm install && npm run build
```

### 开发命令

```bash
python scripts/smoke_test.py            # 秒级冒烟（5 大核心不变量）
python scripts/ai_cad_cli.py rules     # 列全部规范规则
python run.py --no-llm                 # 本地全链路出图（不联网）
python run.py --llm --render           # LLM 主导出图 + 自动弹户型图（联网）
python -m pytest tests/ -q             # 全量测试（352 passed / 5 skipped）
```


---

## 📅 实施阶段

| 阶段 | 核心目标 | 状态 |
|------|---------|------|
| **Phase 0** | 技术预研（DWG 读写、LLM 接入、RAG 雏形） | ✅ 已通 |
| **Phase 1** | 建筑专业 MVP（墙/门窗/标注/规范初检 + 人在回路） | ✅ 已通 |
| **Phase 2** | 规则 DSL 化 + 编辑器 + 写回落盘 | ✅ 已通 |
| **Phase 3** | 四专业接入（给排水/电气/暖通/结构出图 + 条文回填） | ✅ 已通 |
| **M3** | 出图深化（图层着色 + 线宽标准） | ✅ 已通 |
| **M4** | 多专业碰撞检测（管线穿梁/插座撞梁/风管撞梁） | ✅ 已通 |
| **M5** | 团队协作 | ◑ 部分：改动冲突检测 ✅ · 权限模型 ▢ 占位 |
| **M1** | 规范数值终确认 | ▢ 占位（给排水/结构已回填 medium/low，电气开关/暖通风速 high；终确认需各专业专家背书） |
| **M2** | DWG 图层/块名约定对齐 | ▢ 占位（各院制图规范，改 dict 即可） |

**当前进度**：Phase 0-3 全部收口 + M3 出图深化 + M4 碰撞检测 + M5 改动冲突检测已落地；
M1 数值终确认 / M2 图层约定 / M5 权限模型 为**外部依赖占位**（需专家/业务回填，机制已通、值待补），详见 [能力地图](./docs/capability-map.md) 与 [交付报告](./DELIVERY.md)。

---

## ✅ 测试与质量

- **352 passed / 5 skipped / 0 failed**（43 个测试文件，unit + integration）。
  5 个 skip 是外部依赖用例：4 条 langgraph 框架（设 `AI_CAD_RUN_FRAMEWORK=1` 启用）+ 1 条 LLM（需 `AGNES_API_KEY` 环境变量）。
- 冒烟：`python scripts/smoke_test.py` 秒级验证 5 大核心不变量（小改动 0.4s 出结果）。
- 覆盖率门槛：`.coveragerc` 设 `fail_under=90`（纯可测代码实测 ~94%）；`graph.py` / `llm_adapter.py` / `rag_tools.py` 三个模块因需真实框架/LLM key/向量库而**豁免**（是"需外部依赖"，非"漏测热点"）。


---

## 🎯 第一版 MVP 范围

**场景**：住宅套型施工图  
**核心功能**：

1. 方案输入（PDF/图片 → 户型轮廓识别）
2. 墙体生成（含厚度标注）
3. 门窗插入（按规范自动编号）
4. 尺寸标注（轴线、洞口）
5. 规范初检（门宽≥0.9m、窗台≤0.9m 等硬性规则）
6. 人工确认界面（每步暂停等待确认）

**验收标准**：1-2个真实住宅户型跑通全流程，统计人工工时减少比例。

---

## 📝 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| CAD 双引擎 | ezdxf(读) + COM(写) | 最成熟的 DWG 处理方案 |
| Agent 框架 | LangGraph | 支持可中断/可观察的执行流 |
| LLM | 国内优先（MiniMax/Kimi/GLM） | 中文规范理解强，数据不出境 |
| 知识库 | ChromaDB（本地） | 轻量，符合设计院安全要求 |
| 规则引擎 | 自定义 DSL | 规范条文写成代码，不依赖 LLM 做逻辑判断 |

---

## 🔗 相关文档

- [交付报告 DELIVERY.md](./DELIVERY.md) — 决策者主文档（能力清单 / 占位边界 / 路线图 / 实跑命令）
- [能力地图 capability-map.md](./docs/capability-map.md) — 一页纸 ✅ 已通 / ▢ 占位
- [技术合作方案](./doc/AIWeb_AICAD技术合作方案.md)

---

## 👥 团队配置（第一版 3-5人）

| 角色 | 人数 | 核心职责 |
|------|------|---------|
| 技术负责人 | 1 | 技术路线、核心 Agent 框架、CAD 引擎对接 |
| 后端工程师 | 1-2 | 规则引擎、RAG 知识库、API 层 |
| 前端/界面 | 1 | React 面板 + FastAPI 桥 + PyInstaller 打包、CAD 可视化、UI 交互 |
| CAD 开发 | 1（可选） | ezdxf/COM 深度封装、图元标准化 |

---

> **一句话总结**：让 AI 做 AI 擅长的事（规则化、重复性工作），让人做人擅长的事（判断、决策、创新）。
