# Code Review Agent — 大模型接入方案与功能规划

## 一、大模型接入方案

### 1.1 架构设计

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Web 前端    │────▶│  Flask API    │────▶│  规则分析引擎    │
│  (index.html)│     │  (app.py)    │     │  (Ruff/Semgrep)  │
└──────┬───────┘     └──────┬───────┘     └────────┬────────┘
       │                    │                      │
       │  SSE/WS            │                      │ 检测结果
       │  流式输出           │                      ▼
       │                    │              ┌─────────────────┐
       │                    └─────────────▶│  LLM 增强层      │
       │                                   │  (analyzer/llm.py)
       │                                   └────────┬────────┘
       │                                            │
       │                         ┌──────────────────┼──────────────────┐
       │                         ▼                  ▼                  ▼
       │                   OpenAI/Anthropic    本地模型(Ollama)   Zhipu/DeepSeek
       │                                            │
       └────────────────────────────────────────────┘
```

### 1.2 新增文件结构

```
code-review-agent/
├── analyzer/
│   ├── llm.py              # 新增：LLM 调用封装层
│   └── prompts.py          # 新增：Prompt 模板管理
├── config.py               # 新增：配置管理
├── config.yaml             # 新增：用户配置文件
├── static/
│   └── chat.js             # 新增：对话交互 JS
├── templates/
│   ├── index.html          # 改造：新增对话面板
│   └── review.html         # 新增：交互式 Review 页面（可选）
└── ...
```

### 1.3 LLM 封装层（analyzer/llm.py）

```python
"""LLM abstraction layer — supports multiple providers."""
import os
import json
import logging
from typing import Optional, Generator

logger = logging.getLogger(__name__)


class LLMConfig:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai")  # openai / anthropic / ollama / zhipu
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.base_url = os.getenv("LLM_BASE_URL", "")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "2048"))
        self.timeout = int(os.getenv("LLM_TIMEOUT", "60"))


class LLMClient:
    """Unified LLM client with provider abstraction."""
    
    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig()
        self._client = None
    
    @property
    def available(self) -> bool:
        """Check if LLM is configured and available."""
        if self.config.provider == "ollama":
            return True  # 本地模型无需 API Key
        return bool(self.config.api_key)
    
    def _get_client(self):
        """Lazy init provider client."""
        if self._client:
            return self._client
        
        provider = self.config.provider
        
        if provider == "openai":
            from openai import OpenAI
            kwargs = {"api_key": self.config.api_key}
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = OpenAI(**kwargs)
        
        elif provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.config.api_key)
        
        elif provider == "ollama":
            from openai import OpenAI
            self._client = OpenAI(
                api_key="ollama",
                base_url=self.config.base_url or "http://localhost:11434/v1"
            )
        
        elif provider == "zhipu":
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.config.api_key,
                base_url="https://open.bigmodel.cn/api/paas/v4"
            )
        
        return self._client
    
    def chat(self, system: str, user: str, stream: bool = False) -> str:
        """Single-turn chat, return full text."""
        if not self.available:
            return ""
        client = self._get_client()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]
        
        if self.config.provider == "anthropic":
            resp = client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}]
            )
            return resp.content[0].text
        
        resp = client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            max_tokens=self.config.max_tokens,
            stream=stream,
        )
        
        if stream:
            return self._collect_stream(resp)
        return resp.choices[0].message.content
    
    def chat_stream(self, system: str, user: str) -> Generator[str, None, None]:
        """Streaming chat, yield text chunks."""
        if not self.available:
            return
        client = self._get_client()
        
        if self.config.provider == "anthropic":
            with client.messages.stream(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}]
            ) as stream:
                for text in stream.text_stream:
                    yield text
            return
        
        resp = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            max_tokens=self.config.max_tokens,
            stream=True,
        )
        for chunk in resp:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    def _collect_stream(self, stream) -> str:
        parts = []
        for chunk in stream:
            if chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
        return "".join(parts)


# Singleton
_default_client: Optional[LLMClient] = None

def get_llm_client() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
```

### 1.4 Prompt 模板（analyzer/prompts.py）

```python
"""Prompt templates for LLM-enhanced code review."""

SYSTEM_PROMPT = """你是一位资深代码审查专家。你的任务是：
1. 根据静态分析工具的检测结果，生成清晰易懂的中文解释
2. 给出具体的、可操作的修复建议
3. 必要时提供修复代码示例
请用专业但友好的语气回答，避免过于笼统的建议。"""

# --- 功能 1：智能建议生成 ---
PROMPT_SMART_SUGGESTION = """以下是代码审查工具检测到的一个问题：

**文件**: {file_path}（第 {line} 行）
**问题类型**: {issue_type}
**严重程度**: {severity}
**原始描述**: {description}

**相关代码**:
```
{code_context}
```

请给出：
1. 这个问题的具体影响（为什么需要修复）
2. 具体的修复方案
3. 修复后的代码示例（如果适用）
"""

# --- 功能 2：整体评价 ---
PROMPT_SUMMARY = """请根据以下代码分析结果，写一段整体评价：

**项目**: {file_count} 个文件，{total_lines} 行代码
**总分**: {total_score}/100
**各维度得分**:
{dimension_scores}

**关键问题**（最多 10 条）:
{top_issues}

要求：
- 用 2-3 段话总结代码质量
- 指出最需要优先改进的 2-3 个方面
- 给出具体的改进路线建议
- 语气专业友好，不要过于严厉
"""

# --- 功能 3：交互式追问 ---
PROMPT_CHAT = """你正在帮助开发者理解代码审查结果。

**项目分析摘要**:
- 语言: {language}
- 总分: {total_score}/100
- 文件数: {file_count}

**之前的对话**:
{chat_history}

**开发者的问题**: {user_question}

请基于审查上下文回答。如果开发者要求修复代码，请提供完整的修复方案。
"""

# --- 功能 4：代码解释 ---
PROMPT_EXPLAIN = """请解释以下代码片段中存在的问题：

**文件**: {file_path}
**检测到的规则**: {rule_id}
**问题描述**: {description}

```{language}
{code_block}
```

请用通俗的语言解释：
1. 这段代码在做什么
2. 问题出在哪里
3. 为什么这是一种不好的实践
"""
```

### 1.5 API 端点设计（新增到 app.py）

```python
# ========== 新增 API ==========

@app.route('/api/analyze/enhanced', methods=['POST'])
def analyze_enhanced():
    """分析 + LLM 增强。返回规则分析结果，异步生成 LLM 评价。"""
    # 第一步：执行规则分析（复用现有逻辑）
    result = analyzer.analyze(project_path)
    
    # 第二步：生成 LLM 总体评价
    llm = get_llm_client()
    if llm.available:
        summary_prompt = build_summary_prompt(result)
        enhanced_summary = llm.chat(SYSTEM_PROMPT, summary_prompt)
        # 为 top issues 生成智能建议
        enhanced_issues = enhance_issues_suggestions(result.all_issues[:10], files_lines)
    else:
        enhanced_summary = None
        enhanced_issues = None
    
    return jsonify({
        **existing_response,
        "llm_summary": enhanced_summary,
        "enhanced_issues": enhanced_issues,
        "llm_available": llm.available,
    })


@app.route('/api/analyze/stream', methods=['POST'])
def analyze_stream():
    """SSE 流式分析，实时推送进度和 LLM 输出。"""
    def generate():
        # ... 规则分析进度推送
        yield f"data: {json.dumps({'step': 'rules', 'progress': 100})}\n\n"
        
        # LLM 评价流式输出
        if llm.available:
            for chunk in llm.chat_stream(SYSTEM_PROMPT, summary_prompt):
                yield f"data: {json.dumps({'step': 'llm', 'text': chunk})}\n\n"
        
        yield f"data: {json.dumps({'step': 'done'})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/chat', methods=['POST'])
def chat():
    """交互式追问接口。"""
    data = request.get_json()
    # 基于 analysis_session_id 恢复上下文
    # 调用 LLM 生成回答
    # 返回流式或非流式响应


@app.route('/api/issue/explain', methods=['POST'])
def explain_issue():
    """对单个 issue 生成 LLM 详细解释。"""
    data = request.get_json()
    # 读取相关代码上下文（issue 文件 ±10 行）
    # 调用 LLM 生成解释
```

### 1.6 配置文件（config.yaml）

```yaml
# LLM 配置
llm:
  # 服务商: openai / anthropic / ollama / zhipu / deepseek
  provider: openai
  
  # API Key（建议用环境变量 LLM_API_KEY）
  # api_key: sk-xxx
  
  # 自定义 Base URL（兼容 OpenAI 协议的服务都可用）
  # base_url: https://api.deepseek.com/v1
  
  # 模型名称
  model: gpt-4o-mini
  
  # 生成参数
  max_tokens: 2048
  temperature: 0.3
  
  # 超时（秒）
  timeout: 60
  
  # 功能开关
  features:
    smart_suggestion: true    # 智能 issue 建议
    overall_summary: true     # 整体评价
    interactive_chat: true    # 交互式追问
    code_explain: true        # 代码解释
    
    # 成本控制
    max_issues_to_enhance: 10  # 最多增强多少个 issue
    context_lines: 10          # issue 上下文行数

# 分析工具配置
tools:
  ruff:
    timeout: 60
  semgrep:
    timeout: 60
    config: auto

# 项目配置
project:
  max_file_size: 500000       # 单文件最大 500KB
  skip_dirs:
    - .git
    - node_modules
    - __pycache__
    - venv
    - .venv
    - dist
    - build
    - vendor
    - target
```

### 1.7 环境变量

```bash
# LLM 配置（优先级高于 config.yaml）
LLM_PROVIDER=openai          # openai / anthropic / ollama / zhipu / deepseek
LLM_API_KEY=sk-xxx
LLM_BASE_URL=                # 可选，兼容 OpenAI 协议的端点
LLM_MODEL=gpt-4o-mini
LLM_MAX_TOKENS=2048
LLM_TIMEOUT=60

# 推荐的低成本配置方案：
# DeepSeek:    LLM_PROVIDER=openai LLM_BASE_URL=https://api.deepseek.com/v1 LLM_MODEL=deepseek-chat
# Zhipu:       LLM_PROVIDER=zhipu LLM_API_KEY=xxx LLM_MODEL=glm-4-flash
# 本地 Ollama: LLM_PROVIDER=ollama LLM_MODEL=qwen2.5-coder:7b
```

### 1.8 前端改造要点

```
现有页面                              新增/改造
┌──────────────────┐    ┌──────────────────────────────────┐
│                  │    │                                  │
│  ┌────────────┐  │    │  ┌────────────┐  ┌────────────┐  │
│  │ 输入面板    │  │    │  │ 输入面板    │  │ LLM 状态   │  │
│  └────────────┘  │    │  └────────────┘  │ 🤖 DeepSeek │  │
│                  │    │                   └────────────┘  │
│  ┌────────────┐  │    │  ┌──────────────────────────────┐ │
│  │ 雷达图     │  │    │  │ 雷达图                       │ │
│  └────────────┘  │    │  └──────────────────────────────┘ │
│                  │    │                                   │
│  ┌────────────┐  │    │  ┌──────────────────────────────┐ │
│  │ 维度详情    │  │    │  │ 🤖 AI 总体评价               │ │
│  │            │  │    │  │ （LLM 生成的段落）            │ │
│  │ 🔴 issue 1 │  │    │  └──────────────────────────────┘ │
│  │ 🟡 issue 2 │  │    │                                   │
│  └────────────┘  │    │  ┌────────────┐  ┌────────────┐  │
│                  │    │  │ 维度详情    │  │ AI 对话     │  │
│  ┌────────────┐  │    │  │ 🔴 issue 1 │  │            │  │
│  │ 工具状态    │  │    │  │ 🟡 issue 2 │  │ 用户: 帮我  │  │
│  │ 🐍 Ruff    │  │    │  │  └→ [解释]  │  │ 改下这个   │  │
│  └────────────┘  │    │  └────────────┘  │ AI: 好的... │  │
│                  │    │                   └────────────┘  │
└──────────────────┘    └──────────────────────────────────┘
```

**关键改动**：

1. **AI 评价区**：维度详情上方新增 LLM 生成的总体评价卡片，支持流式输出
2. **Issue 解释按钮**：每个 issue 旁加「🤖 AI 解释」按钮，点击后调用 `/api/issue/explain`
3. **右侧对话面板**：可折叠的 Chat 面板，基于当前分析结果对话
4. **LLM 状态指示器**：顶部显示 LLM 连接状态和模型信息

---

## 二、功能迭代清单

### Phase 1 — LLM 智能化（2-3 周）

| # | 功能 | 优先级 | 描述 | 预估工时 |
|---|------|--------|------|---------|
| 1.1 | LLM 封装层 | P0 | `analyzer/llm.py`，支持 OpenAI/Anthropic/Ollama/Zhipu/DeepSeek | 1 天 |
| 1.2 | 配置系统 | P0 | `config.yaml` + 环境变量 + config.py | 0.5 天 |
| 1.3 | 智能 Issue 建议 | P0 | 对 Top N issues 生成 LLM 增强建议 | 1 天 |
| 1.4 | 整体评价生成 | P1 | 分析完成后 LLM 生成 2-3 段总结 | 0.5 天 |
| 1.5 | SSE 流式输出 | P1 | 前端实时展示 LLM 生成过程 | 1 天 |
| 1.6 | Issue 解释按钮 | P1 | 点击单个 issue 获取详细解释 | 0.5 天 |
| 1.7 | 交互式对话 | P2 | 右侧 Chat 面板，基于分析结果追问 | 1.5 天 |

### Phase 2 — 工程化增强（2 周）

| # | 功能 | 优先级 | 描述 | 预估工时 |
|---|------|--------|------|---------|
| 2.1 | 结果持久化 | P0 | SQLite 存储分析历史，支持对比 | 1 天 |
| 2.2 | Git Diff 模式 | P0 | 只分析 git diff 变更的文件 | 1 天 |
| 2.3 | 增量分析 | P1 | 文件哈希缓存，跳过未变更文件 | 1 天 |
| 2.4 | 自定义规则 | P1 | `.reviewrc` 配置文件，自定义阈值和忽略 | 1 天 |
| 2.5 | 质量趋势图 | P2 | 多次分析分数折线图 | 0.5 天 |
| 2.6 | 异步任务 | P2 | 大项目异步分析，WebSocket 推送进度 | 1.5 天 |
| 2.7 | 导出报告 | P2 | 导出 Markdown/PDF 分析报告 | 1 天 |

### Phase 3 — 集成与部署（1-2 周）

| # | 功能 | 优先级 | 描述 | 预估工时 |
|---|------|--------|------|---------|
| 3.1 | GitHub Action | P1 | PR 时自动审查，评论到 PR | 2 天 |
| 3.2 | Git Hook | P2 | pre-commit / pre-push hook | 0.5 天 |
| 3.3 | Docker 化 | P1 | Dockerfile + docker-compose 一键部署 | 1 天 |
| 3.4 | 飞书/钉钉通知 | P2 | 分析完成推送消息卡片 | 1 天 |
| 3.5 | Webhook | P2 | 支持注册 Webhook 回调 | 0.5 天 |
| 3.6 | CLI 模式 | P2 | 命令行直接运行分析 | 1 天 |

### Phase 4 — 高级功能（持续迭代）

| # | 功能 | 描述 |
|---|------|------|
| 4.1 | 多项目仪表盘 | 管理多个仓库的代码质量看板 |
| 4.2 | 团队协作 | 多人共享分析结果，指派 issue |
| 4.3 | 自动修复 | LLM 直接生成修复 PR |
| 4.4 | 代码相似度检测 | 检测跨项目代码抄袭/复用 |
| 4.5 | 安全合规扫描 | OWASP Top 10 专项检测 |
| 4.6 | 多语言扩展 | Rust / TypeScript / C++ / PHP |
| 4.7 | 自定义 LLM Agent | 用户定义审查规则自然语言描述 |
| 4.8 | IDE 插件 | VS Code 实时分析扩展 |

---

## 三、技术选型建议

### LLM Provider 推荐

| 场景 | 推荐方案 | 成本 | 质量 |
|------|---------|------|------|
| 低成本日常使用 | DeepSeek V3 | ¥1/百万token | 优秀 |
| 国产合规 | 智谱 GLM-4-Flash | 免费/低价 | 良好 |
| 最高质量 | Claude Sonnet | ~$3/百万token | 顶级 |
| 离线/隐私 | Ollama + Qwen2.5-Coder:7b | 免费 | 良好 |
| 平衡之选 | GPT-4o-mini | ~$0.15/百万token | 良好 |

### 新增依赖

```
# requirements.txt 追加
openai>=1.0          # OpenAI 兼容协议（覆盖大部分 Provider）
anthropic>=0.30      # Anthropic（可选）
pyyaml>=6.0          # 配置文件解析
```

---

## 四、关键设计原则

1. **LLM 不可用时不影响核心功能**：和 Ruff/Semgrep 一样，LLM 也是可选增强层
2. **成本可控**：默认只增强 Top 10 issues + 一段总结，可配置
3. **流式优先**：LLM 响应一律用流式，用户不用干等
4. **Prompt 可定制**：所有 prompt 模板独立管理，用户可覆盖
5. **Provider 无关**：统一接口，切换 Provider 只改配置
