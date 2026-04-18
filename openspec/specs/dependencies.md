# Dependencies & Configuration

## Python Dependencies

```
flask            — Web 框架
ruff             — Python 静态分析工具
semgrep          — 多语言静态分析工具
openai>=1.0      — OpenAI API 客户端
anthropic>=0.30  — Anthropic API 客户端
pyyaml>=6.0      — YAML 配置解析
```

## External Tools

| Tool | 用途 | 安装方式 |
|------|------|----------|
| ruff | Python 代码检查 | `pip install ruff` |
| semgrep | 多语言安全/质量检查 | `pip install semgrep` |
| git | 版本控制、差异分析 | 系统自带 |

## Environment Variables

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `LLM_PROVIDER` | LLM 服务商 | `openai` |
| `LLM_API_KEY` | API 密钥 | 空 |
| `LLM_BASE_URL` | API 基础 URL | 空（用官方默认） |
| `LLM_MODEL` | 模型名称 | `gpt-4o-mini` |
| `LLM_MAX_TOKENS` | 最大 token 数 | `2048` |
| `LLM_TIMEOUT` | 超时秒数 | `60` |
| `FLASK_DEBUG` | Flask 调试模式 | `false` |

## Runtime

- **端口**: 5001
- **Host**: 0.0.0.0
- **数据库**: `data/reviews.db`（SQLite，自动创建）
- **服务入口**: `python app.py`

## Docker

```bash
# 构建
docker build -t code-review-agent .

# 运行
docker-compose up -d

# 或手动
docker run -p 5001:5001 \
  -e LLM_API_KEY=sk-xxx \
  -e LLM_BASE_URL=https://api.example.com/v1 \
  code-review-agent
```

## Key Configuration (config.yaml)

```yaml
# LLM 配置
llm:
  provider: openai
  model: gpt-4o-mini
  max_tokens: 2048
  temperature: 0.3
  timeout: 60
  features:
    smart_suggestion: true
    overall_summary: true
    interactive_chat: true
    code_explain: true

# 项目配置
project:
  max_file_size: 500000
  skip_dirs: [.git, node_modules, __pycache__, venv, dist, build]

# 评分规则
rules:
  thresholds:
    max_function_length: 50
    max_complexity: 10
    min_comment_ratio: 0.10
  weights:
    complexity: 0.20
    security: 0.15
    solid: 0.13
    duplicates: 0.12
    function_length: 0.12
    naming: 0.10
    comments: 0.10
    dependencies: 0.08
```

## Known Issues

1. **LLM 响应解析**：LLM 返回 JSON 时常包裹在 markdown 代码块中，需 `_extract_json_text` 提取
2. **Git 操作**：非 Git 仓库需降级处理，`git_diff` 返回 None
3. **文件编码**：假设所有源文件为 UTF-8，非 UTF-8 文件会报错
4. **并发安全**：SQLite WAL 模式，但多进程写入仍有风险
5. **外部工具超时**：ruff/semgrep 在大项目上可能超时（60s 限制）
