# 架构设计文档

## 概述

Code Review Agent 采用分层架构，从上到下分为三层：

1. **Web 层**（app.py + templates/）— HTTP API 和前端 UI
2. **分析器层**（analyzer/）— 语言特定的分析逻辑
3. **工具层**（analyzer/tools.py）— 外部工具（Ruff/Semgrep）的封装

## 数据模型

### 核心数据结构（定义在 base.py）

```
AnalysisResult
├── total_score: float          # 加权总分 (0-100)
├── language: str               # 分析的语言
├── file_count: int             # 文件数
├── total_lines: int            # 总行数
├── analyzed_files: List[str]   # 分析的文件路径
├── dimensions: List[DimensionScore]  # 8 个维度
└── all_issues: List[Issue]     # 所有问题汇总

DimensionScore
├── name: str        # 维度名称
├── score: float     # 该维度得分 (0-100)
├── weight: float    # 权重
├── issues: List[Issue]
└── details: str     # 文字摘要

Issue
├── severity: str     # critical / warning / info
├── file_path: str
├── line_number: int
├── description: str  # 问题描述
├── suggestion: str   # 修复建议
└── metric: str       # 度量信息
```

## 八个分析维度

| # | 维度 | 权重 | Python 分析方式 | 其他语言 |
|---|------|------|----------------|---------|
| 1 | 代码复杂度 | 0.20 | Ruff C901 → AST 圈复杂度 | 正则检测 |
| 2 | 代码重复率 | 0.12 | MD5 哈希滑动窗口比对（所有语言相同） | 同左 |
| 3 | 命名规范 | 0.10 | Ruff Nxxx → AST 命名检查 | 正则匹配 |
| 4 | 注释覆盖率 | 0.10 | AST + 行分析（所有语言相同） | 同左 |
| 5 | 函数长度 | 0.12 | Ruff PLR0915 → AST 行数统计 | 正则检测 |
| 6 | 安全隐患 | 0.15 | Semgrep → 正则模式匹配 | Semgrep → 正则 |
| 7 | 依赖管理 | 0.08 | Ruff F401/F811 → AST 导入检查 | 正则检测 |
| 8 | SOLID 原则 | 0.13 | AST 类分析 + Ruff 通用规则 | 正则检测 |

总分计算：`Σ(维度分数 × 权重) / Σ(权重)`

## 工具集成方案

### Ruff（Python 专用）

**调用方式**：`ruff check --output-format=json <path>`

**规则映射**（定义在 tools.py 的 RUFF_DIMENSION_MAP）：

| Ruff 规则 | 映射维度 | 说明 |
|-----------|---------|------|
| C901 | 复杂度 | McCabe 复杂度超标 |
| PLR0912 | 复杂度 | 分支过多 |
| PLR0913 | 复杂度 | 参数过多 |
| N8xx | 命名规范 | PEP 8 命名违规 |
| PLR0915 | 函数长度 | 语句过多 |
| C3001/C3002 | 函数长度 | 复杂度相关 |
| F401 | 依赖管理 | 未使用的导入 |
| F811 | 依赖管理 | 重复导入 |
| F821 | 依赖管理 | 未定义名称 |
| F841 | 依赖管理 | 未使用变量 |
| 其他规则 | SOLID 原则 | 通用建议 |

### Semgrep（多语言安全检测）

**调用方式**：`semgrep --json --config auto <path>`

- `--config auto` 自动选择适合项目的规则集
- 结果全部映射到「安全隐患」维度
- `severity: ERROR` → critical，其余 → warning
- 超时控制：60 秒

## 降级策略

```
分析请求
  │
  ├── 检测 Ruff 可用？ ── 是 → 使用 Ruff 结果
  │                    └── 否 → 降级到 AST 分析
  │
  ├── 检测 Semgrep 可用？ ── 是 → 使用 Semgrep 结果
  │                      └── 否 → 降级到正则匹配
  │
  └── 不受影响：重复检测、注释覆盖率、SOLID（AST/算法实现）
```

**关键原则**：工具不可用时必须静默降级，不能报错中断分析流程。

### 各语言降级路径

| 语言 | 复杂度/命名/函数长度/依赖 | 安全检测 | 其他维度 |
|------|------------------------|---------|---------|
| Python | Ruff → AST | Semgrep → 正则 | AST/算法 |
| JavaScript | 正则 | Semgrep → 正则 | 正则/算法 |
| Java | 正则 | Semgrep → 正则 | 正则/算法 |
| Go | 正则 | Semgrep → 正则 | 正则/算法 |

## 分析器继承关系

```
BaseAnalyzer（base.py）
│   提供：collect_files(), read_file(), compute_total_score(),
│         detect_duplicate_code(), detect_security_issues_regex()
│
├── PythonAnalyzer（python.py）
│   额外：AST 解析、圈复杂度计算、类/函数遍历
│
├── JavaScriptAnalyzer（javascript.py）
│   正则匹配：函数复杂度、命名规范、函数长度等
│
├── JavaAnalyzer（java.py）
│   正则匹配：类/方法分析
│
└── GoAnalyzer（go.py）
    正则匹配：func/结构体分析
```

## 工具封装层（analyzer/tools.py）

### 函数列表

| 函数 | 说明 |
|------|------|
| `is_tool_available(name)` | 检测 CLI 工具是否在 PATH 中 |
| `get_tool_version(name)` | 获取工具版本号（带缓存） |
| `run_tool(cmd, timeout)` | 通用子进程执行，处理超时和异常 |
| `run_ruff(path)` | 执行 Ruff 检查，返回 JSON 结果 |
| `run_semgrep(path, timeout)` | 执行 Semgrep 扫描，返回 JSON 结果 |
| `map_ruff_result(result)` | 将单条 Ruff 结果映射到维度 |
| `map_semgrep_result(result)` | 将 Semgrep 结果映射为安全维度格式 |

### 调用流程

```
PythonAnalyzer.analyze()
│
├── run_ruff(project_path) → (results, success)
├── run_semgrep(project_path) → (results, success)
│
├── 映射 Ruff 结果 → ruff_by_dim[dimension]
├── 映射 Semgrep 结果 → semgrep_findings
│
├── _analyze_complexity(files_lines, ruff_by_dim["complexity"])
├── _analyze_naming(files_lines, ruff_by_dim["naming"])
├── _analyze_function_length(files_lines, ruff_by_dim["function_length"])
├── _analyze_security(files_lines, semgrep_findings)
├── _analyze_dependencies(files_lines, ruff_by_dim["dependencies"])
├── _analyze_solid(files_lines, ruff_general)
├── _analyze_duplicates(files_lines)    # 无工具依赖
└── _analyze_comments(files_lines)      # 无工具依赖
```

## 前端架构

单页应用（templates/index.html），无构建步骤：

- **进度条**：5 个步骤（检测工具 → 收集文件 → 分析维度 → 生成报告 → 完成）
- **结果展示**：雷达图（Chart.js）+ 维度卡片 + 问题列表
- **工具状态面板**：页面底部显示 Ruff/Semgrep 版本或降级提示
- **页面加载时**：调用 `/api/tools` 获取工具可用性

## 性能考虑

- **Semgrep 较慢**：设置 60 秒超时，避免长时间阻塞
- **重复检测**：MD5 滑动窗口，结果上限 50 条
- **文件遍历**：自动跳过 `.git`、`node_modules`、`__pycache__`、`venv` 等目录
- **工具版本缓存**：避免重复执行 `--version` 命令
