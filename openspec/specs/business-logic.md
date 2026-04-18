# Business Logic

## Core Analysis Flow

```
用户提交项目路径
       │
       ▼
┌──────────────┐
│ 路径校验      │ → 目录不存在？→ 返回错误
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ 选择分析器    │ → 根据 language 参数
│ (Python/JS/  │    不支持？→ 返回错误
│  Java/Go)    │
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌─────────────────────┐
│ 分析模式判断  │────▶│ full: 全量分析       │
│              │     │ diff/pr: Git Diff    │
│              │     │ incremental: 增量     │
└──────┬───────┘     └─────────────────────┘
       │
       ▼
┌──────────────┐
│ 收集源文件    │ → 按语言扩展名过滤
│ (collect_    │    跳过 .git/node_modules 等
│  files)      │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────┐
│          规则分析 (Rules Engine)       │
│  ┌────────────┐  ┌────────────────┐  │
│  │ 内置规则    │  │ 外部工具       │  │
│  │ 复杂度      │  │ ruff (Python)  │  │
│  │ 命名规范    │  │ semgrep (多语言)│  │
│  │ 注释率      │  │                │  │
│  │ 函数长度    │  │                │  │
│  │ 重复代码    │  │                │  │
│  └────────────┘  └────────────────┘  │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│        评分计算 (Scoring)             │
│                                      │
│  每个 Issue → severity 映射扣分      │
│  每个 Dimension → 加权平均           │
│  Total Score = Σ(dim.score × weight) │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────┐     ┌────────────────┐
│ 保存结果      │     │ LLM 增强       │
│ (SQLite)     │     │ (可选)         │
└──────┬───────┘     │ · 总体摘要     │
       │             │ · 智能建议     │
       │             │ · 问题解释     │
       │             │ · 修复方案     │
       ▼             └────────────────┘
┌──────────────┐
│ 返回结果      │ → JSON / SSE 流
│ + Webhook    │
│ + 飞书通知    │
└──────────────┘
```

## Analysis Modes

### Full Mode（全量分析）
- 扫描项目所有匹配扩展名的文件
- 默认模式

### Diff / PR Mode（差异分析）
- 需要 Git 仓库
- `git diff --name-only <base> <head>` 获取变更文件列表
- 只分析变更文件
- 非 Git 仓库自动降级为 Full Mode

### Incremental Mode（增量分析）
- 基于 SQLite 中上次分析的文件哈希
- 只分析 MD5 变化的文件
- 无变更时直接返回上次结果

## LLM Enhancement Features

| Feature | Prompt | Input | Output |
|---------|--------|-------|--------|
| 总体摘要 | PROMPT_SUMMARY | 维度评分 + Top Issues | 自然语言总结 |
| 智能建议 | PROMPT_SMART_SUGGESTION | Issue + 代码上下文 | 修复建议 |
| 交互对话 | PROMPT_CHAT | 分析上下文 + 历史对话 | 问答回复 |
| 问题解释 | PROMPT_EXPLAIN | Issue + 代码片段 | 详细解释 |
| 修复方案 | PROMPT_FIX_SUGGESTION | 问题代码块 | JSON: {analysis, fix_description, fixed_code} |
| 测试计划 | PROMPT_TEST_PLAN | Git Diff + 变更范围 | 场景化测试计划 |

## Supported Languages

| Language | Analyzer | External Tools | Key Checks |
|----------|----------|----------------|------------|
| Python | `analyzer/python.py` | ruff, semgrep | PEP8, 类型提示, 复杂度 |
| JavaScript | `analyzer/javascript.py` | semgrep | ESLint 规则, 异步模式 |
| Java | `analyzer/java.py` | semgrep | Spring 规范, 设计模式 |
| Go | `analyzer/go.py` | semgrep | 错误处理, 并发模式 |

## Export Formats

- **Markdown** (`export_markdown`) — 纯文本报告
- **HTML** (`export_html`) — 格式化网页报告

## Notification

- 飞书 Webhook 通知（异步发送）
- 用户自定义 Webhook（注册后自动推送分析结果）
