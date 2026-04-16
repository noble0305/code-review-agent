"""Prompt templates for LLM-enhanced code review."""

SYSTEM_PROMPT = """你是一位资深代码审查专家。你的任务是：
1. 根据静态分析工具的检测结果，生成清晰易懂的中文解释
2. 给出具体的、可操作的修复建议
3. 必要时提供修复代码示例
请用专业但友好的语气回答，避免过于笼统的建议。"""

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

PROMPT_FIX_SUGGESTION = """请为以下代码问题提供修复建议，要求严格按格式返回。

**文件**: {file_path}（第 {line} 行）
**语言**: {language}
**问题描述**: {description}

**原始代码**:
```{language}
{original_code}
```

请严格按以下 JSON 格式返回（不要加 ```json 包裹，直接返回 JSON）：
{{
  "analysis": "用 1-2 句话分析问题原因",
  "fix_description": "修复方案的简要描述",
  "fixed_code": "修复后的完整代码片段（替换原始代码的部分）"
}}

注意：
- fixed_code 必须是可以直接替换原始代码的完整代码
- 保持原有的缩进风格
- 如果问题无法通过代码修复（如架构问题），fixed_code 设为空字符串
"""
