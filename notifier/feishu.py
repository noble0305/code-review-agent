"""飞书通知模块。"""
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional


def send_analysis_result(webhook_url: str, analysis_result: Dict[str, Any]) -> bool:
    """发送飞书消息卡片通知分析结果。

    Args:
        webhook_url: 飞书自定义机器人 webhook URL
        analysis_result: 分析结果字典

    Returns:
        是否发送成功
    """
    score = analysis_result.get('total_score', 0)
    score_color = 'green' if score >= 80 else 'orange' if score >= 60 else 'red'

    # 维度得分
    dim_elements = []
    for dim in analysis_result.get('dimensions', []):
        dim_elements.append({
            "tag": "div",
            "text": {
                "tag": "plain_text",
                "content": f"  {dim['name']}: {dim.get('score', 0)} 分"
            }
        })

    # Top issues
    top_issues = analysis_result.get('all_issues', [])[:5]
    issue_lines = []
    for iss in top_issues:
        icon = {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}.get(iss.get('severity', ''), '⚪')
        issue_lines.append(f"{icon} {iss.get('file', '')}:{iss.get('line', '')} - {iss.get('description', '')}")

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🔍 代码审查报告 - {analysis_result.get('project_path', 'N/A')}"
                },
                "template": score_color
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**总分**: {score}/100\n**文件数**: {analysis_result.get('file_count', 0)} | **代码行数**: {analysis_result.get('total_lines', 0)}\n**语言**: {analysis_result.get('language', 'N/A')}"
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**📊 维度评分**"
                    }
                },
                *dim_elements,
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**📋 Top Issues**\n" + ("\n".join(issue_lines) if issue_lines else "✅ 没有严重问题")
                    }
                }
            ]
        }
    }

    try:
        data = json.dumps(card, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"飞书通知发送失败: {e}")
        return False
