"""Prompt templates for LLM-enhanced code review."""

SYSTEM_PROMPT = """你是一位资深代码审查专家。你的任务是：
1. 根据静态分析工具的检测结果，生成清晰易懂的中文解释
2. 给出具体的、可操作的修复建议
3. 必须提供修复代码示例（除非确实是架构级问题）
请用专业但友好的语气回答，避免过于笼统的建议。
重要：当被要求返回 JSON 格式时，必须严格按格式返回，不要添加 markdown 代码块包裹。"""

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

请用通俗的语言解释（不要重复粘贴原始代码）：
1. **问题分析**：用 2-3 句话指出问题所在
2. **影响说明**：这个 bug/缺陷可能导致什么后果
3. **修复思路**：简要说明怎么改（不要贴完整代码，只需说清楚思路）
"""

PROMPT_FIX_SUGGESTION = """请为以下代码问题提供具体的修复方案。

**文件**: {file_path}（第 {line} 行）
**语言**: {language}
**问题描述**: {description}

**原始代码**:
```{language}
{original_code}
```

你**必须**返回以下 JSON 格式（直接返回纯 JSON，不要用 markdown 代码块包裹）：
{{
  "analysis": "用 1-2 句话分析问题原因",
  "fix_description": "具体说明改了什么、为什么这样改",
  "fixed_code": "修复后的代码"
}}

要求：
- analysis：简明分析问题根因
- fix_description：说清楚修改策略
- fixed_code：这是**最重要**的字段！必须提供可以直接替换原始代码的完整修复代码
- 绝大多数代码问题都可以修复，只有纯架构级重构问题才留空 fixed_code
- 保持原有的缩进风格和命名风格
- 不要在 fixed_code 里加注释说明修改了什么，直接给出修复后的干净代码
"""

PROMPT_TEST_PLAN = """你是一位资深测试工程师。请根据以下 Git Diff 分析改动范围，生成场景测试计划。

## 项目技术栈
{tech_stack}

## 改动文件分类
{change_scope}

## Git Diff 内容
```
{diff_content}
```

## 要求
请分析改动的代码，识别涉及的功能模块和影响范围，然后生成测试计划。

严格按以下 JSON 格式返回（不要加 ```json 包裹）：
{{
  "change_summary": "用 2-3 句话概述本次改动的目的和范围",
  "affected_modules": ["模块1", "模块2"],
  "scope_analysis": {{
    "frontend": {{
      "changed": true/false,
      "files": ["文件列表"],
      "areas": ["影响的 UI/交互/样式 领域"]
    }},
    "backend": {{
      "changed": true/false,
      "files": ["文件列表"],
      "areas": ["影响的 API/服务/逻辑 领域"]
    }},
    "database": {{
      "changed": true/false,
      "files": ["文件列表"],
      "areas": ["影响的表/字段/迁移"]
    }},
    "config": {{
      "changed": true/false,
      "files": ["文件列表"],
      "areas": ["影响的配置项"]
    }}
  }},
  "test_scenarios": [
    {{
      "id": "TC001",
      "title": "测试场景标题",
      "scope": "frontend/backend/api/integration",
      "priority": "P0/P1/P2",
      "precondition": "前置条件",
      "steps": ["步骤1", "步骤2", "步骤3"],
      "expected": "预期结果",
      "type": "functional/boundary/exception/regression"
    }}
  ],
  "regression_scope": "回归测试建议范围描述",
  "risk_points": ["风险点1", "风险点2"]
}}

注意：
- 测试场景要具体可执行，不要泛泛而谈
- 优先覆盖关键路径和边界情况
- 前后端联调的场景要特别标注
- type 类别：functional（功能）、boundary（边界）、exception（异常）、regression（回归）
- priority：P0（必须通过）、P1（应该通过）、P2（建议验证）
- 如果某个 scope 没有改动，changed 设为 false，files 和 areas 设为空列表
"""
