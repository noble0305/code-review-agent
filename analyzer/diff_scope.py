"""Git diff 分析工具 — 识别改动范围（前端/后端/数据库/配置）。"""
import subprocess
import os
from typing import Dict, List, Tuple, Optional
from collections import defaultdict


# 文件分类规则
FILE_CATEGORIES = {
    'frontend': {
        'extensions': ['.vue', '.jsx', '.tsx', '.svelte', '.html', '.css', '.scss', '.less', '.sass', '.styl'],
        'dirs': ['src/components/', 'src/views/', 'src/pages/', 'src/styles/', 'public/', 'static/', 'assets/'],
    },
    'backend': {
        'extensions': ['.py', '.java', '.go', '.rs', '.rb', '.php', '.js', '.ts', '.c', '.cpp', '.cs'],
        'dirs': ['src/routes/', 'src/controllers/', 'src/services/', 'src/api/', 'app/', 'server/', 'api/'],
    },
    'database': {
        'extensions': ['.sql'],
        'dirs': ['migrations/', 'db/', 'database/', 'sql/', 'schema/'],
    },
    'config': {
        'extensions': ['.yaml', '.yml', '.json', '.toml', '.ini', '.env', '.conf', '.properties'],
        'dirs': ['config/', 'conf/', '.env/', 'settings/'],
        'names': ['docker-compose', 'Dockerfile', '.gitignore', 'Makefile', 'package.json', 'requirements.txt', 'go.mod', 'pom.xml'],
    },
}


def classify_file(file_path: str) -> str:
    """将文件分类到 frontend/backend/database/config。"""
    basename = os.path.basename(file_path)
    ext = os.path.splitext(file_path)[1].lower()

    for category, rules in FILE_CATEGORIES.items():
        if ext in rules.get('extensions', []):
            return category
        for d in rules.get('dirs', []):
            if d in file_path:
                return category
        if basename in rules.get('names', []):
            return category

    # 默认根据扩展名推断
    if ext in ('.js', '.ts') and '/api/' not in file_path and '/server/' not in file_path:
        return 'frontend'
    if ext in ('.py', '.java', '.go', '.rs'):
        return 'backend'

    return 'backend'


def analyze_diff_scope(project_path: str, base: str = 'HEAD~1', head: str = 'HEAD') -> Dict:
    """分析 diff 涉及的范围。

    Returns:
        {
            'changed_files': [{'path': ..., 'category': ..., 'status': ...}],
            'scope_summary': {'frontend': 3, 'backend': 5, ...},
            'diff_content': '完整 diff 文本',
            'is_git': True/False,
        }
    """
    result = {
        'changed_files': [],
        'scope_summary': defaultdict(int),
        'diff_content': '',
        'is_git': False,
    }

    # 检查是否是 git 仓库
    try:
        check = subprocess.run(
            ['git', 'rev-parse', '--is-inside-work-tree'],
            cwd=project_path, capture_output=True, text=True, timeout=5
        )
        if check.returncode != 0:
            return result
        result['is_git'] = True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return result

    # 获取变更文件列表及状态
    try:
        diff_names = subprocess.run(
            ['git', 'diff', '--name-status', f'{base}...{head}'],
            cwd=project_path, capture_output=True, text=True, timeout=15
        )
        if diff_names.returncode != 0:
            # fallback: 尝试两点之间
            diff_names = subprocess.run(
                ['git', 'diff', '--name-status', base, head],
                cwd=project_path, capture_output=True, text=True, timeout=15
            )

        status_map = {'A': '新增', 'M': '修改', 'D': '删除', 'R': '重命名'}
        for line in diff_names.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                status = status_map.get(parts[0][0], parts[0])
                fpath = parts[-1]
            else:
                status = '修改'
                fpath = parts[0]

            category = classify_file(fpath)
            result['changed_files'].append({
                'path': fpath,
                'category': category,
                'status': status,
            })
            result['scope_summary'][category] += 1
    except subprocess.TimeoutExpired:
        pass

    # 获取 diff 内容（限制大小）
    try:
        diff_result = subprocess.run(
            ['git', 'diff', f'{base}...{head}'],
            cwd=project_path, capture_output=True, text=True, timeout=30
        )
        diff_text = diff_result.stdout
        # 限制 diff 大小，避免 LLM token 过多
        if len(diff_text) > 30000:
            diff_text = diff_text[:30000] + '\n... (diff 内容过长，已截断)'
        result['diff_content'] = diff_text
    except subprocess.TimeoutExpired:
        result['diff_content'] = '(diff 获取超时)'

    return result


def get_change_scope_text(analysis: Dict) -> str:
    """生成供 LLM 使用的改动范围描述文本。"""
    if not analysis['changed_files']:
        return '无文件变更'

    scope_groups = defaultdict(list)
    for f in analysis['changed_files']:
        scope_groups[f['category']].append(f)

    lines = []
    for category in ['frontend', 'backend', 'database', 'config']:
        files = scope_groups.get(category, [])
        if not files:
            continue
        label = {'frontend': '🖥️ 前端', 'backend': '⚙️ 后端', 'database': '🗄️ 数据库', 'config': '📋 配置'}[category]
        lines.append(f'\n### {label}（{len(files)} 个文件）')
        for f in files:
            lines.append(f"- [{f['status']}] {f['path']}")

    return '\n'.join(lines)
