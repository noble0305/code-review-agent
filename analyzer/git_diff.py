"""Git Diff 支持模块。"""
import os
import subprocess
from typing import Optional, List, Tuple


def is_git_repo(path: str) -> bool:
    """检查是否是 git 仓库。"""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--is-inside-work-tree'],
            cwd=path, capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0 and result.stdout.strip() == 'true'
    except Exception:
        return False


def get_changed_files(repo_path: str, base: str = 'HEAD~1', head: str = 'HEAD') -> Optional[List[str]]:
    """获取变更文件列表（相对于仓库根目录的路径）。

    Args:
        repo_path: 仓库路径
        base: 基准 commit/分支，默认 HEAD~1
        head: 目标 commit/分支，默认 HEAD

    Returns:
        变更文件路径列表，如果不是 git 仓库返回 None
    """
    if not is_git_repo(repo_path):
        return None
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', base, head],
            cwd=repo_path, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None
        files = [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
        # 转为绝对路径
        abs_files = [os.path.join(repo_path, f) for f in files]
        # 只保留存在的文件
        return [f for f in abs_files if os.path.isfile(f)]
    except Exception:
        return None


def get_diff_content(repo_path: str, base: str = 'HEAD~1', head: str = 'HEAD') -> Optional[str]:
    """获取 diff 内容。

    Returns:
        diff 文本，如果不是 git 仓库返回 None
    """
    if not is_git_repo(repo_path):
        return None
    try:
        result = subprocess.run(
            ['git', 'diff', base, head],
            cwd=repo_path, capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except Exception:
        return None


def get_staged_files(repo_path: str) -> Optional[List[str]]:
    """获取暂存区文件列表。"""
    if not is_git_repo(repo_path):
        return None
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR'],
            cwd=repo_path, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None
        files = [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
        abs_files = [os.path.join(repo_path, f) for f in files]
        return [f for f in abs_files if os.path.isfile(f)]
    except Exception:
        return None
