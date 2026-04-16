# Code Review Agent — 代码审查智能体

一个基于 Flask 的自动化代码审查工具，支持 Python、JavaScript、Java、Go 四种语言，从 8 个维度对代码质量进行评分和分析。

## 功能特性

- **8 维度分析**：复杂度、重复率、命名规范、注释覆盖率、函数长度、安全隐患、依赖管理、SOLID 原则
- **工具驱动 + 降级策略**：优先使用 Ruff（Python）和 Semgrep（多语言安全检测），不可用时自动降级到 AST/正则分析
- **Web 界面**：三栏式 UI，实时进度显示，结果可视化为雷达图
- **多语言支持**：Python（深度 AST 分析）、JavaScript、Java、Go（正则 + Semgrep）
- **中文界面**

## 快速开始

### 1. 安装依赖

```bash
cd code-review-agent
pip install -r requirements.txt
```

### 2. 安装分析工具（可选，推荐）

```bash
pip install ruff semgrep
```

> 不安装也不影响使用，系统会自动降级到内置分析。

### 3. 启动服务

```bash
python3 app.py
```

服务默认运行在 `http://0.0.0.0:5001`。

### 4. 使用

1. 浏览器打开 `http://localhost:5001`
2. 输入要分析的项目目录路径
3. 选择编程语言
4. 点击「开始分析」

## API 接口

### GET /api/tools

返回可用分析工具的状态。

**响应示例：**
```json
{
  "ruff": {
    "available": true,
    "version": "0.4.4"
  },
  "semgrep": {
    "available": true,
    "version": "1.60.0"
  }
}
```

### POST /api/analyze

分析指定目录的代码。

**请求体：**
```json
{
  "path": "/path/to/project",
  "language": "python"
}
```

**响应示例：**
```json
{
  "total_score": 82.5,
  "language": "python",
  "file_count": 15,
  "total_lines": 2300,
  "tools_status": {
    "ruff": { "available": true, "version": "0.4.4", "findings": 12 },
    "semgrep": { "available": true, "version": "1.60.0", "findings": 3 }
  },
  "analyzed_files": ["main.py", "utils.py"],
  "dimensions": [
    {
      "name": "代码复杂度",
      "score": 78.0,
      "weight": 0.20,
      "details": "Ruff 检测到 5 个复杂度问题",
      "issues": [
        {
          "severity": "warning",
          "icon": "🟡",
          "file": "main.py",
          "line": 42,
          "description": "Function \"process\" is too complex (11 > 10)",
          "suggestion": "拆分函数，降低分支数量",
          "metric": "Ruff C901"
        }
      ]
    }
  ],
  "all_issues": [...]
}
```

## 项目结构

```
code-review-agent/
├── app.py                  # Flask 应用入口，API 路由
├── requirements.txt        # Python 依赖
├── analyzer/
│   ├── __init__.py         # 分析器注册与工厂函数
│   ├── base.py             # 基类：数据结构、通用检测方法
│   ├── tools.py            # Ruff/Semgrep 工具封装层
│   ├── python.py           # Python 分析器（AST + Ruff + Semgrep）
│   ├── javascript.py       # JavaScript 分析器（正则 + Semgrep）
│   ├── java.py             # Java 分析器（正则 + Semgrep）
│   └── go.py               # Go 分析器（正则 + Semgrep）
└── templates/
    └── index.html          # 前端单页应用
```

## 配置

- 端口：默认 5001，修改 `app.py` 最后一行即可
- 分析工具超时：Semgrep 默认 60 秒，Ruff 默认 60 秒
- 评分阈值：在 `base.py` 的 `BaseAnalyzer` 类中配置

## 技术栈

- **后端**：Python 3 + Flask
- **前端**：原生 HTML/CSS/JS，Chart.js 雷达图
- **分析工具**：Ruff（Python Lint）、Semgrep（安全检测）
- **降级方案**：AST 解析 + 正则匹配
