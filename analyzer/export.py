"""报告导出模块。"""
import json
from datetime import datetime
from typing import Dict, Any


def export_markdown(analysis: Dict[str, Any]) -> str:
    """导出 Markdown 报告。"""
    lines = []
    lines.append("# 🔍 代码审查报告\n")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"**项目路径**: {analysis.get('project_path', 'N/A')}")
    lines.append(f"**语言**: {analysis.get('language', 'N/A')}")
    lines.append(f"**文件数**: {analysis.get('file_count', 0)}")
    lines.append(f"**代码行数**: {analysis.get('total_lines', 0)}")
    lines.append(f"**总分**: {analysis.get('total_score', 0)}\n")

    # 维度评分
    lines.append("## 📊 维度评分\n")
    lines.append("| 维度 | 分数 | 问题数 |")
    lines.append("|------|------|--------|")
    for dim in analysis.get('dimensions', []):
        lines.append(f"| {dim['name']} | {dim.get('score', 0)} | {len(dim.get('issues', []))} |")
    lines.append("")

    # 问题列表
    lines.append("## 📋 问题列表\n")
    issues = analysis.get('all_issues', [])
    if not issues:
        lines.append("✅ 没有发现问题\n")
    else:
        for iss in issues:
            icon = {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}.get(iss.get('severity', ''), '⚪')
            lines.append(f"### {icon} [{iss.get('severity', 'unknown').upper()}] {iss.get('file', '')}:{iss.get('line', '')}")
            lines.append(f"- **描述**: {iss.get('description', '')}")
            if iss.get('suggestion'):
                lines.append(f"- **建议**: {iss['suggestion']}")
            if iss.get('metric'):
                lines.append(f"- **指标**: {iss['metric']}")
            lines.append("")

    # LLM 评价
    llm_summary = analysis.get('llm_summary')
    if llm_summary:
        lines.append("## 🤖 AI 评价\n")
        lines.append(llm_summary)
        lines.append("")

    return "\n".join(lines)


def export_html(analysis: Dict[str, Any]) -> str:
    """导出 HTML 报告。"""
    score = analysis.get('total_score', 0)
    color = '#3fb950' if score >= 80 else '#d29922' if score >= 60 else '#f85149'

    dim_rows = ""
    for dim in analysis.get('dimensions', []):
        dim_rows += f"<tr><td>{dim['name']}</td><td>{dim.get('score', 0)}</td><td>{len(dim.get('issues', []))}</td></tr>"

    issue_rows = ""
    for iss in analysis.get('all_issues', []):
        icon = {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}.get(iss.get('severity', ''), '⚪')
        issue_rows += f"""<tr>
            <td>{icon} {iss.get('severity', '')}</td>
            <td><code>{iss.get('file', '')}:{iss.get('line', '')}</code></td>
            <td>{iss.get('description', '')}</td>
            <td>{iss.get('suggestion', '')}</td>
        </tr>"""

    llm_section = ""
    if analysis.get('llm_summary'):
        llm_section = f"<h2>🤖 AI 评价</h2><div style='white-space:pre-wrap'>{analysis['llm_summary']}</div>"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>代码审查报告 - {analysis.get('project_path', '')}</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; background: #f6f8fa; color: #24292f; }}
h1 {{ border-bottom: 2px solid #d0d7de; padding-bottom: 12px; }}
table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
th, td {{ border: 1px solid #d0d7de; padding: 8px 12px; text-align: left; }}
th {{ background: #f6f8fa; }}
.score {{ font-size: 48px; font-weight: bold; color: {color}; }}
code {{ background: #f6f8fa; padding: 2px 6px; border-radius: 3px; font-size: 13px; }}
</style>
</head>
<body>
<h1>🔍 代码审查报告</h1>
<p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<p>项目: {analysis.get('project_path', '')} | 语言: {analysis.get('language', '')}</p>
<div style="margin:20px 0"><span class="score">{score}</span><span style="font-size:16px;color:#656d76"> / 100</span></div>
<p>文件数: {analysis.get('file_count', 0)} | 代码行数: {analysis.get('total_lines', 0)}</p>

<h2>📊 维度评分</h2>
<table><tr><th>维度</th><th>分数</th><th>问题数</th></tr>{dim_rows}</table>

<h2>📋 问题列表</h2>
<table><tr><th>级别</th><th>位置</th><th>描述</th><th>建议</th></tr>{issue_rows}</table>

{llm_section}
</body>
</html>"""
