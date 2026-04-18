# Data Model

## Core Data Structures

### Issue（代码问题）
```
┌────────────────────────────────────────┐
│              Issue                      │
├────────────────────────────────────────┤
│ severity: critical | warning | info    │
│ file_path: str                         │
│ line_number: int                       │
│ description: str                       │
│ suggestion: str                        │
│ metric: str (function_length, etc.)    │
└────────────────────────────────────────┘
```

### DimensionScore（评分维度）
```
┌────────────────────────────────────────┐
│          DimensionScore                 │
├────────────────────────────────────────┤
│ name: str (复杂度/命名/安全...)         │
│ score: float (0-100)                   │
│ weight: float (总评分权重)              │
│ issues: List[Issue]                    │
│ details: str                           │
└────────────────────────────────────────┘
```

### AnalysisResult（分析结果）
```
┌────────────────────────────────────────┐
│         AnalysisResult                  │
├────────────────────────────────────────┤
│ total_score: float                     │
│ dimensions: List[DimensionScore]       │
│ all_issues: List[Issue]                │
│ file_count: int                        │
│ total_lines: int                       │
│ language: str                          │
│ analyzed_files: List[str]              │
└────────────────────────────────────────┘
```

## SQLite Database Schema

数据库位置：`data/reviews.db`

```sql
-- 分析记录
CREATE TABLE analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path TEXT NOT NULL,
    language TEXT NOT NULL,
    total_score REAL NOT NULL,
    file_count INTEGER NOT NULL,
    total_lines INTEGER NOT NULL,
    dimensions_json TEXT NOT NULL,    -- JSON 序列化的维度数据
    llm_summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_analyses_project ON analyses(project_path);

-- 文件哈希（增量分析用）
-- file_hashes 表
-- association: analysis_id → file_path + md5_hash

-- Webhook 注册
CREATE TABLE webhooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Scoring Dimensions & Weights

| Dimension | Weight | Description |
|-----------|--------|-------------|
| 复杂度 (complexity) | 0.20 | 圈复杂度、函数长度 |
| 安全性 (security) | 0.15 | 安全漏洞检测 |
| SOLID 原则 (solid) | 0.13 | 设计原则合规性 |
| 重复代码 (duplicates) | 0.12 | 代码重复检测 |
| 函数长度 (function_length) | 0.12 | 函数行数超限 |
| 命名规范 (naming) | 0.10 | 命名风格一致性 |
| 注释率 (comments) | 0.10 | 注释覆盖率 |
| 依赖管理 (dependencies) | 0.08 | 导入数量、依赖合理性 |

## Configuration Model

```yaml
# config.yaml 结构
llm:
  provider: openai | anthropic | ollama | zhipu | deepseek
  model: str
  max_tokens: int (default 2048)
  temperature: float (default 0.3)
  timeout: int (default 60s)
  features:
    smart_suggestion: bool
    overall_summary: bool
    interactive_chat: bool
    code_explain: bool

tools:
  ruff: { timeout: 60 }
  semgrep: { timeout: 60, config: auto }

rules:
  thresholds:
    max_function_length: 50
    max_complexity: 10
    min_comment_ratio: 0.10
    max_imports: 20
```
