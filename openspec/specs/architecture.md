# System Architecture

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Web Framework | Flask (Python) |
| LLM Provider | OpenAI-compatible API (configurable) |
| Static Analysis | Ruff (Python), Semgrep (multi-language) |
| Database | SQLite (reviews.db) |
| Notification | Feishu Webhook |
| Frontend | HTML + Vanilla JS |
| Deployment | Docker / docker-compose |

## Directory Structure

```
code-review-agent/
├── app.py                 # Flask 主应用，所有 API 路由
├── config.py              # 配置加载（YAML + 环境变量）
├── config.yaml            # 默认配置文件
├── requirements.txt       # Python 依赖
├── Dockerfile             # Docker 镜像
├── docker-compose.yml     # 编排配置
├── analyzer/              # 核心分析引擎
│   ├── base.py            # BaseAnalyzer 基类 + 数据结构
│   ├── python.py          # Python 分析器
│   ├── javascript.py      # JavaScript 分析器
│   ├── java.py            # Java 分析器
│   ├── go.py              # Go 分析器
│   ├── rules.py           # 规则引擎
│   ├── llm.py             # LLM 抽象层（多 Provider）
│   ├── prompts.py         # Prompt 模板
│   ├── storage.py         # SQLite 持久化
│   ├── tasks.py           # 异步任务管理
│   ├── tools.py           # 外部工具检测（ruff/semgrep）
│   ├── git_diff.py        # Git Diff 文件提取
│   ├── diff_scope.py      # Diff 范围分析
│   └── export.py          # 报告导出（Markdown/HTML）
├── notifier/
│   └── feishu.py          # 飞书通知
├── hooks/
│   └── pre-commit         # Git pre-commit 钩子
├── scripts/
│   ├── cli.py             # CLI 入口
│   └── install-hooks.sh   # 钩子安装脚本
├── templates/
│   └── index.html         # Web UI
└── data/
    └── reviews.db         # SQLite 数据库（运行时生成）
```

## Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│                    Web UI / CLI                      │
│              (templates/index.html)                  │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP / SSE
┌──────────────────────▼──────────────────────────────┐
│                   Flask (app.py)                     │
│  ┌──────────┐ ┌──────────┐ ┌───────────────────┐   │
│  │ /analyze │ │ /chat    │ │ /export /history  │   │
│  │ /stream  │ │ /fix     │ │ /webhook /browse  │   │
│  │ /enhanced│ │ /explain │ │ /test-plan        │   │
│  └────┬─────┘ └────┬─────┘ └────────┬──────────┘   │
└───────┼─────────────┼───────────────┼───────────────┘
        │             │               │
┌───────▼─────────────▼───────────────▼───────────────┐
│               Analyzer Engine                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ Python   │ │ JS/Java  │ │   Go     │            │
│  │ Analyzer │ │ Analyzer │ │ Analyzer │            │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘            │
│       └──────┬──────┘──────────┬─┘                  │
│              ▼                 ▼                     │
│  ┌──────────────┐    ┌──────────────┐               │
│  │ Rules Engine │    │ External     │               │
│  │ (rules.py)   │    │ Tools        │               │
│  └──────┬───────┘    │ (ruff,semgrep)│              │
│         │            └──────────────┘               │
│         ▼                                           │
│  ┌──────────────┐    ┌──────────────┐               │
│  │ LLM Client   │    │ Storage      │               │
│  │ (llm.py)     │    │ (SQLite)     │               │
│  └──────────────┘    └──────────────┘               │
└─────────────────────────────────────────────────────┘
                       │
              ┌────────▼────────┐
              │ Feishu Notifier │
              └─────────────────┘
```
