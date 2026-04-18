"""PHP analyzer using regex-based analysis."""
import re
from .base import BaseAnalyzer, AnalysisResult, Issue, DimensionScore
from .tools import run_semgrep, map_semgrep_result, get_tool_version


class PHPAnalyzer(BaseAnalyzer):
    LANGUAGE = "php"
    FILE_EXTENSIONS = ['.php', '.phtml']

    tools_status = {}

    def analyze(self, project_path: str, file_list=None) -> AnalysisResult:
        files = self.collect_files(project_path, file_list=file_list)
        if not files:
            return AnalysisResult(language=self.LANGUAGE)

        result = AnalysisResult(language=self.LANGUAGE, file_count=len(files), analyzed_files=files)
        files_lines = {}
        for f in files:
            lines, err = self.read_file(f)
            if not err:
                files_lines[f] = lines
                result.total_lines += len(lines)

        semgrep_results, semgrep_ok = run_semgrep(project_path, timeout=60)
        semgrep_findings = [map_semgrep_result(r) for r in semgrep_results] if semgrep_ok else []
        self.tools_status = {'semgrep': {'available': semgrep_ok, 'version': get_tool_version('semgrep') if semgrep_ok else None, 'findings': len(semgrep_results)}}

        result.dimensions = [
            self._analyze_complexity(files_lines),
            self._analyze_duplicates(files_lines),
            self._analyze_naming(files_lines),
            self._analyze_comments(files_lines),
            self._analyze_function_length(files_lines),
            self._analyze_security(files_lines, semgrep_findings),
            self._analyze_modern(files_lines),
            self._analyze_solid(files_lines),
        ]
        for d in result.dimensions:
            result.all_issues.extend(d.issues)
        result.total_score = round(self.compute_total_score(result.dimensions), 1)
        return result

    def _analyze_complexity(self, files_lines):
        dim = DimensionScore(name="代码复杂度", score=100, weight=0.20)
        for fpath, lines in files_lines.items():
            depth = 0
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if not s or s.startswith('//') or s.startswith('#') or s.startswith('/*'): continue
                for ch in s:
                    if ch == '{': depth += 1
                    elif ch == '}': depth = max(0, depth - 1)
                if re.match(r'^\s*(if|else|elseif|for|foreach|while|switch|case|catch|try)\b', s):
                    depth += 1
                if depth > 5:
                    dim.score = max(0, dim.score - 1.5)
                    if depth > 8:
                        dim.issues.append(Issue(severity='warning', file_path=fpath, line_number=i,
                            description=f'嵌套深度 {depth} 层', suggestion='提取函数减少嵌套', metric=f'深度 {depth}'))
        return dim

    def _analyze_duplicates(self, files_lines):
        dim = DimensionScore(name="代码重复率", score=100, weight=0.12)
        issues = self.detect_duplicate_code(files_lines, min_lines=6)
        dim.issues = issues[:20]
        dim.score = max(0, 100 - len(issues) * 3)
        return dim

    def _analyze_naming(self, files_lines):
        dim = DimensionScore(name="命名规范", score=100, weight=0.10)
        for fpath, lines in files_lines.items():
            for i, line in enumerate(lines, 1):
                s = line.strip()
                m = re.match(r'function\s+([A-Z]\w+)', s)
                if m:
                    dim.score -= 2
                    dim.issues.append(Issue(severity='info', file_path=fpath, line_number=i,
                        description=f'函数名 "{m.group(1)}" 应使用 camelCase', suggestion='PSR 规范要求函数名 camelCase', metric=m.group(1)))
        dim.score = max(0, dim.score)
        return dim

    def _analyze_comments(self, files_lines):
        dim = DimensionScore(name="注释覆盖率", score=100, weight=0.10)
        total = comment = 0
        for fpath, lines in files_lines.items():
            in_block = False
            for line in lines:
                s = line.strip()
                if not s: continue
                total += 1
                if in_block:
                    comment += 1
                    if '*/' in s: in_block = False
                elif s.startswith('//') or s.startswith('#') or s.startswith('/**') or s.startswith('/*'):
                    comment += 1
                    if '/*' in s and '*/' not in s: in_block = True
        if total:
            ratio = comment / total
            dim.score = 95 if ratio >= 0.10 else 70 if ratio >= 0.05 else 40
            if dim.score < 60:
                dim.issues.append(Issue(severity='warning', file_path='', line_number=0,
                    description=f'注释覆盖率 {ratio:.1%}，建议 ≥ 10%', suggestion='添加 PHPDoc 注释', metric=f'{ratio:.1%}'))
        return dim

    def _analyze_function_length(self, files_lines):
        dim = DimensionScore(name="函数长度", score=100, weight=0.12)
        for fpath, lines in files_lines.items():
            func_start = None; brace = 0
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if func_start is None:
                    if re.match(r'\s*function\s+\w+', s) and '{' in s:
                        func_start = i; brace = s.count('{') - s.count('}')
                        if brace <= 0: func_start = None
                else:
                    brace += s.count('{') - s.count('}')
                    if brace <= 0:
                        length = i - func_start
                        if length > 80:
                            dim.score = max(0, dim.score - 5)
                            dim.issues.append(Issue(severity='warning', file_path=fpath, line_number=func_start,
                                description=f'函数长度 {length} 行', suggestion='拆分函数', metric=f'{length} 行'))
                        elif length > 50: dim.score = max(0, dim.score - 2)
                        func_start = None; brace = 0
        return dim

    def _analyze_security(self, files_lines, semgrep_findings):
        dim = DimensionScore(name="安全隐患", score=100, weight=0.15)
        for fpath, lines in files_lines.items():
            issues = self.detect_security_issues_regex(lines, fpath)
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if re.search(r'\b(eval|assert)\s*\(', s):
                    dim.issues.append(Issue(severity='critical', file_path=fpath, line_number=i,
                        description='使用了 eval/assert', suggestion='避免动态代码执行', metric=s[:60]))
                if re.search(r'\bmysql_query\b', s):
                    dim.issues.append(Issue(severity='critical', file_path=fpath, line_number=i,
                        description='使用了已废弃的 mysql_* 函数', suggestion='使用 PDO 或 mysqli', metric=s[:60]))
                if re.search(r'\$_(GET|POST|REQUEST|COOKIE)\s*\[', s) and re.search(r'\becho\b', s):
                    dim.issues.append(Issue(severity='critical', file_path=fpath, line_number=i,
                        description='直接输出用户输入可能导致 XSS', suggestion='使用 htmlspecialchars() 转义', metric=s[:60]))
            dim.issues.extend(issues)
            dim.issues.extend([i for i in semgrep_findings if i.file_path == fpath])
        crit = len([i for i in dim.issues if i.severity == 'critical'])
        warn = len([i for i in dim.issues if i.severity == 'warning'])
        dim.score = max(0, 100 - crit * 10 - warn * 3)
        return dim

    def _analyze_modern(self, files_lines):
        dim = DimensionScore(name="现代 PHP 实践", score=100, weight=0.11)
        for fpath, lines in files_lines.items():
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if re.search(r'\bglobal\s+\$', s):
                    dim.score -= 3
                    dim.issues.append(Issue(severity='warning', file_path=fpath, line_number=i,
                        description='使用了 global 关键字', suggestion='使用依赖注入替代全局变量', metric=s[:60]))
                if re.search(r'\$\w+\s*=\s*&\s*new\b', s):
                    dim.score -= 2
        dim.score = max(0, dim.score)
        return dim

    def _analyze_solid(self, files_lines):
        dim = DimensionScore(name="SOLID 原则", score=100, weight=0.10)
        for fpath, lines in files_lines.items():
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if re.match(r'class\s+\w+', s):
                    methods = sum(1 for l in lines if re.match(r'\s*(public|private|protected)?\s*function\s+', l.strip()))
                    if methods > 15:
                        dim.score -= 5
                        dim.issues.append(Issue(severity='warning', file_path=fpath, line_number=i,
                            description=f'类方法数 {methods}，建议 ≤ 15', suggestion='考虑拆分职责 (SRP)', metric=f'{methods} 个方法'))
        dim.score = max(0, dim.score)
        return dim
