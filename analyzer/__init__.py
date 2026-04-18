from .base import BaseAnalyzer, AnalysisResult, Issue, DimensionScore
from .python import PythonAnalyzer
from .javascript import JavaScriptAnalyzer
from .java import JavaAnalyzer
from .go import GoAnalyzer
import os
from collections import Counter

ANALYZERS = {
    'python': PythonAnalyzer,
    'javascript': JavaScriptAnalyzer,
    'java': JavaAnalyzer,
    'go': GoAnalyzer,
}

# 文件扩展名 → 语言映射
EXTENSION_MAP = {
    '.py': 'python',
    '.js': 'javascript', '.jsx': 'javascript', '.mjs': 'javascript', '.cjs': 'javascript',
    '.ts': 'javascript', '.tsx': 'javascript',  # TypeScript 走 JS 分析器
    '.java': 'java',
    '.go': 'go',
}


def detect_language(project_path: str) -> str:
    """根据项目中源代码文件扩展名自动检测主要语言。
    
    Returns:
        检测到的语言名（小写），默认 'python'
    """
    if not os.path.isdir(project_path):
        return 'python'
    
    counter = Counter()
    ignore_dirs = {
        'node_modules', '.git', '__pycache__', '.venv', 'venv', 'env',
        'dist', 'build', '.tox', '.mypy_cache', '.pytest_cache',
        'vendor', 'target', 'bin', 'obj', '.gradle', '.idea', '.vscode',
        'assets', 'static', 'public', 'media', 'coverage', '.next', '.nuxt'
    }
    
    for root, dirs, files in os.walk(project_path):
        # 跳过忽略目录
        dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith('.')]
        for f in files:
            _, ext = os.path.splitext(f)
            lang = EXTENSION_MAP.get(ext.lower())
            if lang:
                counter[lang] += 1
    
    if not counter:
        return 'python'
    
    # 返回文件数最多的语言
    return counter.most_common(1)[0][0]


def get_analyzer(language):
    cls = ANALYZERS.get(language)
    if cls:
        return cls()
    return None
