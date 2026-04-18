# API Specification

## Base URL
`http://localhost:5001`

## Endpoints

### Analysis

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/analyze` | 基础代码分析 |
| POST | `/api/analyze/enhanced` | 增强分析（含 LLM 建议） |
| POST | `/api/analyze/stream` | SSE 流式分析 |
| POST | `/api/analyze/async` | 异步分析任务 |
| GET | `/api/task/<task_id>` | 查询异步任务状态 |
| GET | `/api/tasks` | 列出所有任务 |

### Analysis Request Body
```json
{
  "path": "/path/to/project",
  "language": "python",
  "mode": "full|diff|pr",
  "base": "HEAD~1",
  "head": "HEAD",
  "incremental": false
}
```

### Analysis Response
```json
{
  "project_path": "...",
  "total_score": 75.5,
  "language": "python",
  "file_count": 12,
  "total_lines": 1500,
  "tools_status": {"ruff": {"available": true}},
  "analyzed_files": ["src/main.py"],
  "dimensions": [
    {
      "name": "复杂度",
      "score": 80.0,
      "weight": 0.20,
      "details": "...",
      "issues": [
        {
          "severity": "warning",
          "icon": "🟡",
          "file": "src/main.py",
          "line": 42,
          "description": "函数过长",
          "suggestion": "...",
          "metric": "function_length"
        }
      ]
    }
  ],
  "all_issues": [...]
}
```

### LLM Interaction

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/llm/status` | LLM 状态和配置 |
| POST | `/api/chat` | 交互式对话（支持 SSE 流式） |
| POST | `/api/issue/explain` | 问题详细解释 |
| POST | `/api/issue/fix` | 生成修复建议（含代码对比） |

### Chat Request
```json
{
  "message": "如何优化这个函数？",
  "analysis_context": {"language": "python", "total_score": 60},
  "history": [{"question": "...", "answer": "..."}],
  "stream": true
}
```

### Fix Response
```json
{
  "file_path": "src/main.py",
  "line": 42,
  "severity": "warning",
  "analysis": "问题分析...",
  "fix_description": "修复说明...",
  "original_code": "...",
  "fixed_code": "...",
  "context_start": 35,
  "context_end": 50
}
```

### History & Export

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/history` | 分析历史列表 |
| GET | `/api/history/<id>` | 单次分析详情 |
| GET | `/api/history/compare?id1=&id2=` | 对比两次分析 |
| GET | `/api/export/<id>?format=markdown\|html` | 导出报告 |

### Test Plan

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/test-plan` | 基于 Git Diff 生成测试计划 |

### Infrastructure

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/tools` | 工具状态（ruff/semgrep） |
| GET | `/api/browse?path=` | 浏览本地目录 |
| GET | `/api/git/log?path=&count=` | Git 提交记录 |
| POST | `/api/notify` | 手动触发飞书通知 |
| POST | `/api/webhook/register` | 注册 webhook |
| DELETE | `/api/webhook/<id>` | 删除 webhook |
| GET | `/api/webhook` | 列出 webhooks |
