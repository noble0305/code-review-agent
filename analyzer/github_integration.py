"""GitHub PR 集成模块 — Webhook 接收、PR 分析、评论发布。"""

import hmac
import hashlib
import os
import shutil
import subprocess
import tempfile
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def verify_webhook_signature(secret: str, payload_body: bytes, signature_header: str) -> bool:
    """验证 GitHub Webhook 的 HMAC-SHA256 签名。

    Args:
        secret: Webhook Secret（在 GitHub App 设置中配置）
        payload_body: 原始请求体（bytes）
        signature_header: X-Hub-Signature-256 请求头的值，格式 sha256=<hex>

    Returns:
        签名是否匹配
    """
    if not secret or not signature_header:
        return False

    if not signature_header.startswith('sha256='):
        return False

    expected = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()

    received = signature_header[len('sha256='):]
    return hmac.compare_digest(expected, received)


def clone_pr_repo(clone_url: str, branch: str, target_dir: str) -> str:
    """浅克隆 PR 的 head 分支到临时目录。

    Args:
        clone_url: Git clone URL（https 格式）
        branch: 分支名
        target_dir: 目标目录

    Returns:
        克隆到的目录路径

    Raises:
        RuntimeError: 克隆失败
    """
    os.makedirs(target_dir, exist_ok=True)

    result = subprocess.run(
        ['git', 'clone', '--depth=1', '--branch', branch, clone_url, target_dir],
        capture_output=True, text=True, timeout=120
    )

    if result.returncode != 0:
        raise RuntimeError(f'Git clone 失败: {result.stderr}')

    return target_dir


def format_review_comment(analysis_result: Dict[str, Any]) -> str:
    """将分析结果格式化为 GitHub Markdown 评论。

    Args:
        analysis_result: 分析结果字典（包含 total_score, dimensions, all_issues 等）

    Returns:
        Markdown 格式的评论内容
    """
    score = analysis_result.get('total_score', 0)
    file_count = analysis_result.get('file_count', 0)
    total_lines = analysis_result.get('total_lines', 0)
    language = analysis_result.get('language', 'unknown')
    dimensions = analysis_result.get('dimensions', [])
    all_issues = analysis_result.get('all_issues', [])

    # 评分颜色
    if score >= 80:
        score_emoji = '🟢'
    elif score >= 60:
        score_emoji = '🟡'
    else:
        score_emoji = '🔴'

    lines = [
        '<!-- code-review-agent -->',
        f'## {score_emoji} Code Review Agent 自动审查报告',
        '',
        f'**总体评分**: {score:.1f}/100 | **语言**: {language} | **文件数**: {file_count} | **代码行数**: {total_lines}',
        '',
    ]

    # 维度评分表格
    if dimensions:
        lines.append('### 📊 维度评分')
        lines.append('')
        lines.append('| 维度 | 评分 | 权重 | 问题数 |')
        lines.append('|------|------|------|--------|')
        for d in dimensions:
            name = d.get('name', '')
            s = d.get('score', 0)
            w = d.get('weight', 0)
            issue_count = len(d.get('issues', []))
            s_emoji = '🟢' if s >= 80 else ('🟡' if s >= 60 else '🔴')
            lines.append(f'| {name} | {s_emoji} {s:.1f} | {w:.0%} | {issue_count} |')
        lines.append('')

    # 问题摘要（最多显示 10 个）
    if all_issues:
        critical = [i for i in all_issues if i.get('severity') == 'critical']
        warning = [i for i in all_issues if i.get('severity') == 'warning']
        info = [i for i in all_issues if i.get('severity') == 'info']

        lines.append('### 📋 问题摘要')
        lines.append('')
        lines.append(f'- 🔴 严重: {len(critical)} | 🟡 警告: {len(warning)} | 🔵 建议: {len(info)}')
        lines.append('')

        top_issues = all_issues[:10]
        if top_issues:
            lines.append('**Top 问题:**')
            lines.append('')
            for idx, iss in enumerate(top_issues, 1):
                severity_icon = {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}.get(iss.get('severity', ''), '⚪')
                file = iss.get('file', '')
                line_num = iss.get('line', '')
                desc = iss.get('description', '')
                location = f'`{file}:{line_num}`' if file else ''
                lines.append(f'{idx}. {severity_icon} {location} — {desc}')
            lines.append('')

    lines.append('---')
    lines.append('*由 [Code Review Agent](https://github.com/noble0305/code-review-agent) 自动生成*')

    return '\n'.join(lines)


def post_pr_comment(token: str, repo_full_name: str, pr_number: int, body: str) -> int:
    """发布评论到 GitHub PR。

    如果已有 code-review-agent 标记的评论，则更新而非重复创建。

    Args:
        token: GitHub Personal Access Token
        repo_full_name: 仓库全名（owner/repo）
        pr_number: PR 编号
        body: 评论内容（Markdown）

    Returns:
        评论 ID

    Raises:
        ImportError: PyGithub 未安装
        Exception: API 调用失败
    """
    try:
        from github import Github
    except ImportError:
        raise ImportError('请安装 PyGithub: pip install PyGithub')

    g = Github(token)
    repo = g.get_repo(repo_full_name)
    pr = repo.get_pull(pr_number)

    # 检查是否已有 code-review-agent 的评论
    marker = '<!-- code-review-agent -->'
    existing_comment = None
    for comment in pr.get_issue_comments():
        if marker in comment.body:
            existing_comment = comment
            break

    if existing_comment:
        existing_comment.edit(body)
        return existing_comment.id
    else:
        comment = pr.create_issue_comment(body)
        return comment.id


def run_pr_analysis(
    token: str,
    repo_full_name: str,
    pr_number: int,
    clone_url: str,
    head_branch: str,
    language: str = 'python',
    cleanup: bool = True
) -> Dict[str, Any]:
    """完整的 PR 分析流程：克隆 → 分析 → 评论。

    Args:
        token: GitHub Token
        repo_full_name: owner/repo
        pr_number: PR 编号
        clone_url: Git clone URL
        head_branch: 分支名
        language: 编程语言
        cleanup: 是否清理临时目录

    Returns:
        分析结果字典
    """
    tmp_dir = tempfile.mkdtemp(prefix='code-review-pr-')
    analysis_result = {'status': 'failed', 'error': None}

    try:
        # 1. 克隆
        logger.info(f'Cloning {repo_full_name} branch {head_branch}...')
        clone_pr_repo(clone_url, head_branch, tmp_dir)

        # 2. 分析
        from analyzer import get_analyzer
        analyzer = get_analyzer(language)
        if not analyzer:
            raise ValueError(f'不支持的语言: {language}')

        logger.info(f'Analyzing {tmp_dir}...')
        result = analyzer.analyze(tmp_dir)

        # 3. 构建结果字典
        analysis_result = {
            'status': 'completed',
            'total_score': result.total_score,
            'file_count': result.file_count,
            'total_lines': result.total_lines,
            'language': result.language,
            'dimensions': [
                {
                    'name': d.name,
                    'score': d.score,
                    'weight': d.weight,
                    'issues': [
                        {
                            'severity': i.severity,
                            'file': os.path.relpath(i.file_path, tmp_dir) if i.file_path else '',
                            'line': i.line_number,
                            'description': i.description,
                        }
                        for i in d.issues
                    ]
                }
                for d in result.dimensions
            ],
            'all_issues': [
                {
                    'severity': i.severity,
                    'file': os.path.relpath(i.file_path, tmp_dir) if i.file_path else '',
                    'line': i.line_number,
                    'description': i.description,
                }
                for i in result.all_issues
            ],
        }

        # 4. 格式化并评论
        comment_body = format_review_comment(analysis_result)
        comment_id = post_pr_comment(token, repo_full_name, pr_number, comment_body)
        analysis_result['comment_id'] = comment_id
        logger.info(f'Posted comment {comment_id} to PR #{pr_number}')

    except Exception as e:
        logger.error(f'PR analysis failed: {e}')
        analysis_result['error'] = str(e)

    finally:
        # 5. 清理
        if cleanup and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
            logger.info(f'Cleaned up {tmp_dir}')

    return analysis_result
