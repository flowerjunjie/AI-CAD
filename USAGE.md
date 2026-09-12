# AI-CAD 使用指南

## 快速开始

### 环境准备

```bash
# 安装 Python 依赖
pip install -r src/agents/requirements.txt

# 安装 Node.js 依赖
npm install

# 配置 API Key
cp .env.example .env
# 编辑 .env，填入 AGNES_API_KEY
```

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行单元测试
python -m pytest tests/unit/ -v

# 运行集成测试
python -m pytest tests/integration/ -v
```

### 使用 CLI

```bash
# 查看规范规则
python scripts/ai_cad_cli.py rules

# 运行样本测试
python scripts/ai_cad_cli.py sample

# 运行 Agent Demo
python scripts/ai_cad_cli.py demo

# 运行测试套件
python scripts/ai_cad_cli.py test
```

### 运行 Demo

```bash
# 端到端演示
python scripts/demo.py

# 直接调用 Agent
python -c "
import sys, os
sys.path.insert(0, '.')
os.environ['AI_CAD_LLM_PROVIDER'] = 'agnes'
os.environ['AGNES_API_KEY'] = 'your-key'
from src.agents.src.graph import run_agent_demo
result = run_agent_demo()
print(result)
"
```

## 配置说明

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AI_CAD_LLM_PROVIDER` | LLM提供商 | `agnes` |
| `AGNES_API_KEY` | Agnes API密钥 | — |
| `AGNES_BASE_URL` | Agnes API地址 | `https://apihub.agnes-ai.com/v1` |
| `AGNES_MODEL` | 模型名称 | `agnes-2.0-flash` |
| `MINIMAX_API_KEY` | MiniMax API密钥 | — |
| `KIMI_API_KEY` | Kimi API密钥 | — |
| `GLM_API_KEY` | GLM API密钥 | — |
| `SERVER_PORT` | 后端服务端口 | `3456` |

### 配置文件

- `config/app.json` — 应用配置
- `config/agents.yaml` — Agent参数配置

## 项目结构

```
AI-CAD/
├── src/
│   ├── agents/src/
│   │   ├── graph.py           # Agent 图定义
│   │   ├── nodes/
│   │   │   ├── intent_structure.py  # 意图理解+方案结构化
│   │   │   └── cad_rule_export.py   # CAD执行+规则校验+输出
│   │   └── tools/
│   │       ├── cad_tools.py     # ezdxf/COM CAD引擎
│   │       ├── llm_adapter.py   # LLM适配器
│   │       └── rag_tools.py     # RAG知识库
│   ├── rules/src/
│   │   ├── engine.py          # 规则引擎核心
│   │   ├── residential/       # 住宅规范规则
│   │   ├── fire_safety/       # 防火规范规则
│   │   └── accessibility/     # 无障碍规范规则
│   ├── server/src/            # Node.js 后端
│   └── client/src/            # Electron + React
├── tests/
│   ├── unit/                  # 单元测试
│   └── integration/           # 集成测试
├── data/sample/               # 样本数据
├── config/                    # 配置文件
├── scripts/                   # 工具脚本
└── docs/                      # 设计文档
```

## 规范规则清单

### 住宅规范 (GB 50096-2011)

| 规则ID | 规则名称 | 严重级别 | 规范依据 |
|--------|---------|---------|---------|
| residential-door-main-width | 户门宽度≥1.0m | ERROR | 第5.8.6条 |
| residential-door-interior-width | 户内门宽度≥0.9m | ERROR | 第5.8.6条 |
| residential-door-bathroom-width | 卫生间门宽度≥0.8m | ERROR | 第5.8.6条 |
| residential-window-sill-height | 窗台高度≤0.9m | WARNING | 第5.8.7条 |
| residential-balcony-railing-height | 阳台栏杆≥1.05m | ERROR | 第5.8.5条 |
| residential-corridor-solid-width | 套内走廊≥1.2m | ERROR | 第5.8.3条 |
| residential-corridor-living-width | 走道≥1.0m | ERROR | 第5.8.3条 |
| residential-room-bedroom-area | 卧室面积≥5㎡ | ERROR | 第5.2.1条 |
| residential-room-living-area | 起居室面积≥6㎡ | ERROR | 第5.2.2条 |
| residential-room-kitchen-area | 厨房面积≥3.5㎡ | ERROR | 第5.2.3条 |
| residential-room-bathroom-area | 卫生间面积≥2㎡ | ERROR | 第5.2.4条 |

### 防火规范 (GB 50016-2014)

| 规则ID | 规则名称 | 严重级别 | 规范依据 |
|--------|---------|---------|---------|
| fire-corridor-min-width | 疏散走道≥1.4m | ERROR | 第5.5.18条 |
| fire-corridor-length | 走廊长度限制 | WARNING | 第5.5.17条 |
| fire-door-clear-width | 疏散门≥0.9m | ERROR | 第5.5.19条 |

### 无障碍规范 (JGJ 50-2019)

| 规则ID | 规则名称 | 严重级别 | 规范依据 |
|--------|---------|---------|---------|
| accessibility-ramp-width | 坡道宽度≥1.2m | ERROR | 第6.5.1条 |
| accessibility-ramp-slope | 坡度≤1:12 | ERROR | 第6.4.2条 |

---

> **一句话**: 让AI做AI擅长的事（规则化、重复性工作），让人做人擅长的事（判断、决策、创新）。
