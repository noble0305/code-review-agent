"""Base analyzer with common data structures and utilities."""
import os
import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from collections import defaultdict


@dataclass
class Issue:
    severity: str          # 'critical', 'warning', 'info'
    file_path: str
    line_number: int
    description: str
    suggestion: str
    metric: str = ""


@dataclass
class DimensionScore:
    name: str
    score: float       # 0-100
    weight: float      # weight in total score
    issues: List[Issue] = field(default_factory=list)
    details: str = ""


@dataclass
class AnalysisResult:
    total_score: float = 0
    dimensions: List[DimensionScore] = field(default_factory=list)
    all_issues: List[Issue] = field(default_factory=list)
    file_count: int = 0
    total_lines: int = 0
    language: str = ""
    analyzed_files: List[str] = field(default_factory=list)


class BaseAnalyzer:
    """Base class for all language analyzers."""
    
    LANGUAGE = "unknown"
    FILE_EXTENSIONS = []
    
    # Thresholds
    MAX_FUNCTION_LENGTH_WARNING = 50
    MAX_FUNCTION_LENGTH_CRITICAL = 100
    MAX_CyclOMATIC_WARNING = 10
    MAX_CyclOMATIC_CRITICAL = 20
    MIN_COMMENT_RATIO = 0.10
    MAX_IMPORTS_WARNING = 20
    
    def collect_files(self, project_path: str, file_list: List[str] = None) -> List[str]:
        """Collect all source files of the target language.
        
        Args:
            project_path: 项目根目录
            file_list: 指定文件列表（如果提供，只分析这些文件）
        """
        if file_list is not None:
            # 过滤出匹配扩展名的文件
            return [f for f in file_list if any(f.endswith(ext) for ext in self.FILE_EXTENSIONS) and os.path.isfile(f)]
        
        skip_dirs = {'.git', 'node_modules', '__pycache__', 'venv', '.venv', 'env',
                     'dist', 'build', '.idea', '.vscode', 'vendor', 'target', 'bin', 'obj'}
        files = []
        for root, dirs, filenames in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for fn in filenames:
                if any(fn.endswith(ext) for ext in self.FILE_EXTENSIONS):
                    files.append(os.path.join(root, fn))
        return files
    
    def read_file(self, path: str) -> tuple:
        """Read file, return (lines, error)."""
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.readlines(), None
        except Exception as e:
            return [], str(e)
    
    def analyze(self, project_path: str, file_list: List[str] = None) -> AnalysisResult:
        """Main entry point. Override in subclass.
        
        Args:
            project_path: 项目根目录
            file_list: 指定文件列表（增量分析 / diff 模式）
        """
        raise NotImplementedError
    
    def compute_total_score(self, dimensions: List[DimensionScore]) -> float:
        """Weighted average of dimension scores."""
        if not dimensions:
            return 0
        total_weight = sum(d.weight for d in dimensions)
        if total_weight == 0:
            return 0
        return sum(d.score * d.weight for d in dimensions) / total_weight
    
    def severity_icon(self, severity: str) -> str:
        return {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}.get(severity, '⚪')
    
    def detect_duplicate_code(self, files_lines: Dict[str, List[str]], min_lines: int = 6) -> List[Issue]:
        """Detect similar code blocks across files."""
        issues = []
        # Build hash of sliding windows
        block_hashes = {}  # hash -> (file, start_line)
        
        for fpath, lines in files_lines.items():
            # Strip whitespace for comparison
            stripped = [l.strip() for l in lines]
            for i in range(len(stripped) - min_lines + 1):
                block = '\n'.join(stripped[i:i+min_lines])
                if not block.strip() or len(block) < 20:
                    continue
                h = hashlib.md5(block.encode()).hexdigest()
                if h in block_hashes:
                    orig_file, orig_line = block_hashes[h]
                    if orig_file != fpath:
                        issues.append(Issue(
                            severity='warning',
                            file_path=fpath,
                            line_number=i + 1,
                            description=f'重复代码块（与 {os.path.basename(orig_file)}:{orig_line} 相同）',
                            suggestion='提取为公共函数或模块以减少重复',
                            metric=f'{min_lines}行重复代码'
                        ))
                else:
                    block_hashes[h] = (fpath, i + 1)
        
        return issues[:50]  # cap results
    
    def detect_security_issues_regex(self, lines: List[str], file_path: str) -> List[Issue]:
        """Common security issue detection via regex."""
        issues = []
        patterns = [
            (r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']{3,}', '硬编码密码', '使用环境变量或配置文件管理密码'),
            (r'(?i)(api_key|apikey|secret_key|secret)\s*=\s*["\'][^"\']{3,}', '硬编码密钥/Token', '使用环境变量或密钥管理服务'),
            (r'(?i)eval\s*\(', '使用了 eval()，存在代码注入风险', '避免使用 eval，使用更安全的替代方案'),
            (r'(?i)(SELECT|INSERT|UPDATE|DELETE)\s+.*\+\s*(req|request|params|input)', '可能的 SQL 注入', '使用参数化查询代替字符串拼接'),
            (r'(?i)exec\s*\(\s*["\']', '可能的不安全代码执行', '避免动态执行不可信输入'),
            (r'(?i)subprocess\.call\s*\(.*shell\s*=\s*True', '使用 shell=True 可能导致命令注入', '避免 shell=True，使用列表形式传参'),
        ]
        for i, line in enumerate(lines, 1):
            for pattern, desc, sug in patterns:
                if re.search(pattern, line):
                    issues.append(Issue(
                        severity='critical', file_path=file_path, line_number=i,
                        description=desc, suggestion=sug,
                        metric=line.strip()[:80]
                    ))
        return issues
