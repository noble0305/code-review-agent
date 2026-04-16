# Code Review Agent — AI 驱动的智能代码审查工具

一个全功能的自动化代码审查平台，集成大模型智能分析、多语言静态检查、历史趋势追踪，支持 Web/CLI/Docker/GitHub Action 多种使用方式。

## ✨ 核心特性

### 静态分析
- **8 维度评分**：代码复杂度、重复率、命名规范、注释覆盖率、函数长度、安全隐患、依赖管理、SOLID 原则
- **工具驱动 + 降级策略**：Ruff（Python Lint）+ Semgrep（安全检测），不可用时自动降级到 AST/正则
- **多语言支持**：Python（深度 AST）、JavaScript、Java、Go

### AI 智能化
- **🤖 智能建议**：基于 LLM 为每个 Issue 生成针对性修复方案和代码示例
- **📝 总体评价**：AI 自动生成代码质量总结，指出优先改进方向
- **💬 交互对话**：基于分析结果追问，获取详细解释和修复建议
- **🔍 代码解释**：点击任意 Issue 获取通俗的代码解释
- **多模型支持**：OpenAI / Anthropic / DeepSeek / 智谱 / Ollama（本地）

### 工程化
- **Git Diff 模式**：只分析变更文件，适合 PR Review
- **增量分析**：文件哈希缓存，跳过未变更文件
- **自定义规则**：项目级 `.reviewrc` 配置阈值、权重和忽略规则
- **结果持久化**：SQLite 存储分析历史，支持对比和趋势追踪
- **异步任务**：大项目后台分析，前端轮询进度
- **报告导出**：Markdown / HTML 格式导出

### 集成部署
- **GitHub Action**：PR 时自动审查并评论
- **CLI 工具**：命令行直接分析，支持 CI/CD 集成
- **Git Hook**：pre-commit 检查，分数不达标阻止提交
- **Docker**：一键部署，Dockerfile + docker-compose
- **飞书通知**：分析结果推送飞书群卡片
- **Webhook**：分析完成自动回调

## 🚀 快速开始

### 方式一：直接运行

```bash
# 克隆项目
git clone https://github.com/noble0305/code-review-agent.git
cd code-review-agent

# 安装依赖
pip install -r requirements.txt

# （可选）安装分析工具
pip install ruff semgrep

# 启动 Web 服务
python3 app.py
```

浏览器打开 `http://localhost:5001`

### 方式二：Docker

```bash
# 构建并启动
docker-compose up -d

# 访问
open http://localhost:5001
```

### 方式三：CLI 命令行

```bash
# 分析项目
python scripts/cli.py analyze /path/to/project --lang python

# 指定输出格式
python scripts/cli.py analyze /path/to/project --lang python --output markdown

# Git Diff 模式
python scripts/cli.py analyze /path/to/project --mode diff

# 查看历史
python scripts/cli.py history

# 导出报告
python scripts/cli.py export <analysis_id> --format markdown
```

## 🤖 配置 LLM（可选，强烈推荐）

不配置 LLM 也能用，但 AI 增强功能会不可用。

### 环境变量方式

```bash
# OpenAI
export LLM_PROVIDER=openai
export LLM_API_KEY=sk-xxx
export LLM_MODEL=gpt-4o-mini

# DeepSeek（低成本推荐）
export LLM_PROVIDER=openai
export LLM_BASE_URL=https://api.deepseek.com/v1
export LLM_MODEL=deepseek-chat
export LLM_API_KEY=sk-xxx

# 智谱 GLM
export LLM_PROVIDER=zhipu
export LLM_API_KEY=xxx
export LLM_MODEL=glm-4-flash

# 本地 Ollama（免费，隐私）
export LLM_PROVIDER=ollama
export LLM_MODEL=qwen2.5-coder:7b
```

### 配置文件方式

编辑 `config.yaml`：

```yaml
llm:
  provider: openai
  model: gpt-4o-mini
  max_tokens: 2048
  features:
    smart_suggestion: true
    overall_summary: true
    interactive_chat: true
    code_explain: true
```

## 📖 API 文档

### 分析接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/analyze` | POST | 基础分析（纯规则） |
| `/api/analyze/enhanced` | POST | 增强分析（规则 + LLM） |
| `/api/analyze/stream` | POST | SSE 流式增强分析 |
| `/api/analyze/async` | POST | 异步分析（返回 task_id） |

**请求参数：**
```json
{
  "path": "/path/to/project",
  "language": "python",
  "mode": "full",
  "base": "HEAD~1",
  "incremental": false
}
```

### AI 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/chat` | POST | 交互式对话（流式） |
| `/api/issue/explain` | POST | Issue 详细解释 |
| `/api/llm/status` | GET | LLM 连接状态 |

### 历史与导出

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/history` | GET | 分析历史列表 |
| `/api/history/<id>` | GET | 单次分析详情 |
| `/api/history/compare` | GET | 对比两次分析 |
| `/api/export/<id>` | GET | 导出报告（?format=markdown\|html） |

### 任务管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/task/<id>` | GET | 查询异步任务状态 |
| `/api/tasks` | GET | 列出所有任务 |

### 工具与通知

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/tools` | GET | 分析工具状态（Ruff/Semgrep） |
| `/api/notify` | POST | 发送飞书通知 |
| `/api/webhook` | GET/POST/DELETE | Webhook 管理 |

## 📂 项目结构

```
code-review-agent/
├── app.py                      # Flask 应用入口
├── config.py                   # 配置管理
├── config.yaml                 # 默认配置
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── analyzer/
│   ├── __init__.py             # 分析器工厂
│   ├── base.py                 # 基类 + 数据结构
│   ├── tools.py                # Ruff/Semgrep 封装
│   ├── llm.py                  # LLM 客户端
│   ├── prompts.py              # Prompt 模板
│   ├── python.py               # Python 分析器
│   ├── javascript.py           # JavaScript 分析器
│   ├── java.py                 # Java 分析器
│   ├── go.py                   # Go 分析器
│   ├── storage.py              # SQLite 持久化 + 增量分析
│   ├── git_diff.py             # Git Diff 支持
│   ├── rules.py                # 自定义规则
│   ├── tasks.py                # 异步任务管理
│   └── export.py               # 报告导出
├── notifier/
│   └── feishu.py               # 飞书通知
├── scripts/
│   ├── cli.py                  # CLI 工具
│   └── install-hooks.sh        # Git Hook 安装
├── hooks/
│   └── pre-commit              # pre-commit hook
├── .github/
│   └── workflows/
│       └── code-review.yml     # GitHub Action
├── templates/
│   └── index.html              # Web 前端
└── docs/
    ├── README.md
    ├── ARCHITECTURE.md         # 架构设计文档
    └── ROADMAP.md              # 功能规划
```

## ⚙️ 自定义规则

在项目根目录创建 `.reviewrc`：

```yaml
# 忽略的文件/目录
ignore:
  - "test/**"
  - "migrations/**"
  - "*.generated.*"

# 阈值覆盖
thresholds:
  max_function_length: 50
  max_complexity: 10
  min_comment_ratio: 0.10

# 维度权重调整
weights:
  complexity: 0.20
  security: 0.20
  solid: 0.10
```

## 🔧 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3 + Flask |
| 前端 | 原生 HTML/CSS/JS + Chart.js |
| 静态分析 | Ruff + Semgrep + AST |
| AI | OpenAI / Anthropic / Ollama / 智谱 |
| 存储 | SQLite |
| 部署 | Docker / GitHub Action / CLI |

## 📄 License

MIT
