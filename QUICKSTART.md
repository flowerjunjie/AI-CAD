# AI-CAD 快速启动指南

## 环境要求

- Python >= 3.11
- Node.js >= 18 (可选，用于Electron桌面端)
- API Key: Agnes AI (`AGNES_API_KEY`)

## 一键启动

```bash
# 1. 进入项目目录
cd E:/workspace0525/AI-CAD

# 2. 安装Python依赖
pip install -r src/agents/requirements.txt

# 3. 安装Node.js依赖 (可选)
npm install

# 4. 配置环境变量
# 创建 .env 文件，或设置以下环境变量:
export AI_CAD_LLM_PROVIDER=agnes
export AGNES_API_KEY=你的Agnes密钥 (填入 .env)
export AGNES_BASE_URL=https://apihub.agnes-ai.com/v1
export AGNES_MODEL=agnes-2.0-flash
```

## 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行单元测试
python -m pytest tests/unit/ -v

# 运行集成测试
python -m pytest tests/integration/ -v
```

## 使用CLI

```bash
# 查看规范规则
python scripts/ai_cad_cli.py rules

# 运行样本测试
python scripts/ai_cad_cli.py sample

# 运行Agent演示
python scripts/ai_cad_cli.py demo

# 运行测试套件
python scripts/ai_cad_cli.py test
```

## 直接调用Python

```python
import sys, os
sys.path.insert(0, '.')
os.environ['AI_CAD_LLM_PROVIDER'] = 'agnes'
os.environ['AGNES_API_KEY'] = '你的Agnes密钥'
os.environ['AGNES_BASE_URL'] = 'https://apihub.agnes-ai.com/v1'
os.environ['AGNES_MODEL'] = 'agnes-2.0-flash'

# 方式1: 运行完整Agent流程
from src.agents.src.graph import run_agent_demo
result = run_agent_demo()
print(f"DWG: {result['final_dwg_path']}")
print(f"违规: {len(result['rule_violations'])} 条")

# 方式2: 解析户型JSON
from src.agents.src.nodes.input_parser import parse_json_input
parsed = parse_json_input('data/sample/residential_100sqm.json')
print(f"任务数: {len(parsed['task_list'])}")

# 方式3: 规则引擎校验
from src.rules.src.engine import get_engine
from src.rules.src.residential.doors import Door
engine = get_engine()
doors = [Door(id='d1', width_m=0.8, room_type='entrance', location=(0,0))]
violations = engine.check(doors, rule_ids=['residential-door-main-width'])
print(f"违规: {len(violations)} 条")
```

## 目录结构

```
AI-CAD/
├── tests/                  # 测试 (23个测试全部通过)
├── src/
│   ├── rules/src/         # 规则引擎 (25条规范)
│   ├── agents/src/        # Agent核心
│   ├── server/src/        # Node.js后端
│   └── client/src/        # Electron前端
├── data/sample/           # 样本数据
├── scripts/               # 工具脚本
├── config/                # 配置文件
├── docs/                  # 设计文档
├── README.md              # 项目概述
└── USAGE.md               # 使用指南
```

## 验证清单

- [x] 23个测试全部通过
- [x] 25条规范规则可执行校验
- [x] Agent端到端流程可运行
- [x] DWG文件可生成
- [x] CLI工具可用
- [x] JSON样本数据可解析
- [x] Agnes API可调用
