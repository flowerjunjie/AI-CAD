# AI-CAD 项目架构设计

> 文档版本：v0.1  
> 创建日期：2026-09-09  
> 状态：Phase 0 · 技术预研

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                         桌面端 (Electron)                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────┐  │
│  │ CAD 视图层   │  │  规则面板    │  │  Agent 状态  │  │ 导出面板  │  │
│  │ (Three.js)  │  │  (实时检查) │  │  (流程图)   │  │          │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └────┬─────┘  │
│         └─────────────────┴─────────────────┴─────────────┘        │
│                          │  IPC / WebSocket                       │
│              ┌───────────▼───────────┐                             │
│              │     Node.js Backend    │                             │
│              │   (Express + MCP)     │                             │
│              └───────────┬───────────┘                             │
│                          │ HTTP / gRPC                              │
│         ┌────────────────┼────────────────┐                        │
│         │                │                │                        │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌─────▼─────┐                   │
│  │  Python     │  │  Python     │  │  Python   │                   │
│  │  Agent      │  │  Rules      │  │  RAG      │                   │
│  │  (LangGraph)│  │  (DSL)     │  │  (ChromaDB)│                   │
│  └──────┬──────┘  └──────┬──────┘  └─────┬─────┘                   │
│         └─────────────────┴─────────────────┘                       │
│                          │                                         │
│              ┌───────────▼───────────┐                             │
│              │     知识层             │                             │
│              │  ChromaDB + SQLite    │                             │
│              │  + 本地规范文档        │                             │
│              └───────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 模块划分

### 2.1 桌面端应用层 (`src/client/`)

**职责**：用户交互、CAD 可视化、Agent 状态展示

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| 主框架 | Electron 28+ | 跨平台桌面应用 |
| UI 框架 | React 18 + TypeScript | 组件化开发 |
| CAD 视图 | Three.js +ezdxf 解析结果 | 3D 图纸预览 |
| 状态管理 | Zustand | 轻量级全局状态 |
| 通信 | IPC (Electron) + WebSocket | 与后端服务通信 |

**核心页面**：
- `CADEditor` — 主编辑区，嵌入 AutoCAD COM 控件或 Three.js 渲染
- `RulePanel` — 实时规范检查结果面板
- `AgentFlow` — Agent 执行流程图，显示当前节点和等待状态
- `ExportDialog` — 成果导出（DWG/PDF/报表）

### 2.2 后端服务层 (`src/server/`)

**职责**：API 路由、Agent 编排、MCP 服务器

```
src/server/src/
├── api/                    # HTTP API 路由
│   ├── routes/
│   │   ├── design.ts      # 设计方案相关接口
│   │   ├── agents.ts      # Agent 任务接口
│   │   └── export.ts      # 导出接口
│   └── middleware/
│       └── auth.ts         # 认证中间件
├── mcp/                    # MCP 服务器
│   └── server.ts           # AutoCAD MCP 工具注册
├── agents/                 # Agent 编排（Lightweight）
│   ├── orchestrator.ts    # 任务分发器
│   └── state.ts           # Agent 状态管理
└── index.ts               # 服务入口
```

### 2.3 Agent 核心层 (`src/agents/`)

**职责**：LangGraph 定义的 Agent 执行图、节点实现

```
src/agents/src/
├── graph.py               # Agent 图定义（主入口）
├── edges.py               # 状态转移逻辑
├── nodes/
│   ├── intent.py          # 意图理解 Agent
│   ├── structure.py       # 方案结构化 Agent
│   ├── decompose.py       # 任务分解 Agent
│   ├── cad_execute.py     # CAD 执行 Agent
│   ├── rule_check.py      # 规则校验 Agent
│   ├── multi_discipline.py # 多专业协调 Agent
│   └── export.py          # 成果输出 Agent
├── states/
│   └── design_state.py    # 共享状态定义
└── tools/
    ├── cad_tools.py       # ezdxf/COM 工具封装
    ├── rule_tools.py      # 规则查询工具
    └── rag_tools.py       # 知识库检索工具
```

### 2.4 规则引擎层 (`src/rules/`)

**职责**：建筑规范的可执行规则定义

```
src/rules/src/
├── engine.py              # 规则执行引擎
├── dsl.py                 # 规则 DSL 解析器
├── residential/           # 住宅套型规范
│   ├── doors.py           # 门窗规则
│   ├── windows.py         # 窗户规则
│   ├── corridors.py       # 走廊规则
│   └── areas.py           # 面积计算规则
├── fire_safety/           # 防火规范
│   └── distance.py        # 防火间距
└── accessibility/         # 无障碍规范
    └── ramps.py           # 坡道规则
```

**规则 DSL 示例**：
```python
# 住宅设计规范示例
@rule("住宅户内门宽度")
def door_width(room: Room) -> bool:
    """户内门宽度不应小于 0.9m"""
    return room.door_width >= 0.9

@rule("窗台高度")
def window_sill(room: Room) -> bool:
    """窗台高度不应大于 0.9m"""
    return room.window_sill_height <= 0.9
```

### 2.5 知识层

| 组件 | 技术 | 说明 |
|------|------|------|
| 向量数据库 | ChromaDB（本地） | 规范条文、历史图纸向量化存储 |
| 图元库 | SQLite | 标准图块、门窗型号存储 |
| 文档存储 | 本地文件系统 | 原始规范 PDF/Word 文档 |

---

## 3. Agent 执行流程

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  意图理解     │────▶│  方案结构化   │────▶│  任务分解     │
│  Agent       │     │  Agent       │     │  Agent       │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                │
                                                ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  成果输出     │◀────│  多专业协调   │◀────│  规则校验     │
│  Agent       │     │  Agent       │     │  Agent       │
└──────────────┘     └──────────────┘     └──────▲───────┘
                                                │
                     ┌──────────────────────────┘
                     │ （人机协作节点）
                     ▼
              ┌──────────────┐
              │  CAD 执行     │
              │  Agent       │
              │  [等待确认]   │
              └──────────────┘
```

**关键设计**：每个 Agent 节点都是**可中断、可编辑、可追溯**的——人类可以随时介入修改，AI 从当前状态继续。

---

## 4. 数据流

```
用户输入方案
    │
    ▼
[PDF/图片] ──▶ [OCR + 图像识别] ──▶ [户型轮廓提取]
    │                                      │
    ▼                                      ▼
[结构化数据] ◀── [LLM 解析] ── [建筑面积、层数、功能分区]
    │
    ▼
[任务列表] ──▶ [Agent 编排] ──▶ [CAD 操作队列]
    │                                      │
    ▼                                      ▼
[规则检查] ◀── [执行结果] ── [DWG 实体生成]
    │
    ▼
[人工确认] ──▶ [修改指令] ──▶ [更新 DWG]
    │
    ▼
[成果输出] ──▶ [DWG/PDF/材料表]
```

---

## 5. 技术选型详细

### 5.1 CAD 引擎（双引擎策略）

| 操作 | 工具 | 理由 |
|------|------|------|
| 读取 DWG | ezdxf (Python) | 纯 Python，无需 AutoCAD 安装，跨平台 |
| 写入/编辑 DWG | COM 接口 (Windows) | 与 AutoCAD 原生兼容，保证输出格式标准 |
| 预览渲染 | Three.js | 浏览器/Electron 内 3D 渲染 |

**Fallback 策略**：当 COM 接口不可用时（Linux/macOS），使用 ezdxf 写入 + 离线验证。

### 5.2 Agent 框架

| 候选 | 选择 | 理由 |
|------|------|------|
| LangGraph | ✅ 选用 | 支持可中断/可观察的执行流，适合人在回路 |
| LangChain | — | 更偏 LLM 调用，缺乏状态管理 |
| 自建状态机 | — | 复杂度高，复用 LangGraph 更务实 |

### 5.3 LLM 选型

| 模型 | 用途 | 理由 |
|------|------|------|
| MiniMax-M2.7 | 主模型 | 中文理解强，API 成本低，数据不出境 |
| Kimi k3 | 备用 | 长上下文能力强，适合处理大图纸 |
| GLM-4 | 规范问答 | 国内模型，对中文规范理解好 |

**切换策略**：通过配置文件指定主模型，支持运行时切换。

### 5.4 RAG 知识库

```
规范文档 ──▶ [文本分割] ──▶ [向量嵌入] ──▶ [ChromaDB]
                                          │
用户问题 ──▶ [查询重写] ──▶ [相似度检索] ──▶ [上下文注入 LLM]
```

**本地部署**：ChromaDB 运行在本地，无需外部服务，符合设计院数据安全要求。

---

## 6. 安全设计

| 风险 | 措施 |
|------|------|
| 图纸数据安全 | 本地处理，不上传云端 |
| LLM 调用安全 | API Key 本地存储，不在代码中硬编码 |
| 规则执行安全 | 规则引擎独立进程，防止恶意注入 |
| 用户输入验证 | 所有输入经过 schema 校验 |

---

## 7. 扩展性设计

### 7.1 多专业扩展

当前架构支持通过添加新的 Agent 节点和规则模块来扩展专业：

```python
# 新增给排水专业
from agents.nodes.plumbing import PlumbingAgent
graph.add_node("plumbing", PlumbingAgent().run)
graph.add_edge("rule_check", "plumbing")
```

### 7.2 规则热更新

规则 DSL 支持运行时加载，设计师可自行编辑规则文件，无需重启应用。

---

## 8. Phase 0 关键技术验证点

| 验证项 | 成功标准 | 负责人 |
|--------|---------|--------|
| ezdxf 读取 DWG | 能解析实体列表，提取墙/门/窗对象 | 后端工程师 |
| COM 接口调用 | 能通过 Python 控制 AutoCAD 绘制 | CAD 开发 |
| LLM API 接入 | MiniMax/Kimi 调用延迟 < 3s | 后端工程师 |
| ChromaDB 查询 | 能回答规范条文问答 | 后端工程师 |
| Electron 空壳 | 能打开并显示基本 UI | 前端工程师 |

---

> **架构原则**：先跑通最小链路，再逐步增强。不要设计完美的系统——设计能演化的系统。
