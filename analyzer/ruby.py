"""Ruby analyzer using regex-based analysis."""
import re
from .base import BaseAnalyzer, AnalysisResult, Issue, DimensionScore
from .tools import run_semgrep, map_semgrep_result, get_tool_version


class RubyAnalyzer(BaseAnalyzer):
    LANGUAGE = "ruby"
    FILE_EXTENSIONS = ['.rb', '.rake', '.gemspec']

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
            self._analyze_idioms(files_lines),
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
                if not s or s.startswith('#'): continue
                depth += s.count('do') + s.count('{') - s.count('end') - s.count('}')
                if re.match(r'^\s*(if|elsif|else|unless|case|when|begin|rescue|for|while|until)\b', s):
                    depth += 1
                if depth > 5:
                    dim.score = max(0, dim.score - 1.5)
                    if depth > 8:
                        dim.issues.append(Issue(severity='warning', file_path=fpath, line_number=i,
                            description=f'嵌套深度 {depth} 层', suggestion='提取方法减少嵌套', metric=f'深度 {depth}'))
        return dim

    def _analyze_duplicates(self, files_lines):
        dim = DimensionScore(name="代码重复率", score=100, weight=0.12)
        issues = self.detect_duplicate_code(files_lines, min_lines=6)
        dim.issues = issues[:20]; dim.score = max(0, 100 - len(issues) * 3)
        return dim

    def _analyze_naming(self, files_lines):
        dim = DimensionScore(name="命名规范", score=100, weight=0.10)
        for fpath, lines in files_lines.items():
            for i, line in enumerate(lines, 1):
                s = line.strip()
                m = re.match(r'def\s+([A-Z]\w+)', s)
                if m:
                    dim.score -= 2
                    dim.issues.append(Issue(severity='info', file_path=fpath, line_number=i,
                        description=f'方法名 "{m.group(1)}" 应使用 snake_case', suggestion='Ruby 方法命名规范为 snake_case', metric=m.group(1)))
                m = re.match(r'class\s+([a-z]\w*)', s)
                if m:
                    dim.score -= 2
                    dim.issues.append(Issue(severity='info', file_path=fpath, line_number=i,
                        description=f'类名 "{m.group(1)}" 应使用 PascalCase', suggestion='Ruby 类名使用 PascalCase', metric=m.group(1)))
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
                    if '=end' in s: in_block = False
                elif s.startswith('#'):
                    comment += 1
                elif s.startswith('=begin'):
                    comment += 1; in_block = True
        if total:
            ratio = comment / total
            dim.score = 95 if ratio >= 0.10 else 70 if ratio >= 0.05 else 40
            if dim.score < 60:
                dim.issues.append(Issue(severity='warning', file_path='', line_number=0,
                    description=f'注释覆盖率 {ratio:.1%}', suggestion='添加 YARD 文档注释', metric=f'{ratio:.1%}'))
        return dim

    def _analyze_function_length(self, files_lines):
        dim = DimensionScore(name="方法长度", score=100, weight=0.12)
        for fpath, lines in files_lines.items():
            method_start = None
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if re.match(r'^\s*def\s+\w+', s):
                    method_start = i
                elif method_start and re.match(r'^\s*end\b', s):
                    length = i - method_start
                    if length > 50:
                        dim.score = max(0, dim.score - 5)
                        dim.issues.append(Issue(severity='warning', file_path=fpath, line_number=method_start,
                            description=f'方法长度 {length} 行，建议 ≤ 30', suggestion='拆分方法', metric=f'{length} 行'))
                    elif length > 30: dim.score = max(0, dim.score - 2)
                    method_start = None
        return dim

    def _analyze_security(self, files_lines, semgrep_findings):
        dim = DimensionScore(name="安全隐患", score=100, weight=0.15)
        for fpath, lines in files_lines.items():
            issues = self.detect_security_issues_regex(lines, fpath)
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if re.search(r'\beval\s*\(', s):
                    dim.issues.append(Issue(severity='critical', file_path=fpath, line_number=i,
                        description='使用了 eval()', suggestion='避免动态执行代码', metric=s[:60]))
                if re.search(r'\bsystem\s*\(|\bexec\s*\(|\b`[^`]+`', s):
                    dim.issues.append(Issue(severity='warning', file_path=fpath, line_number=i,
                        description='可能存在命令注入风险', suggestion='使用 system(array) 形式', metric=s[:60]))
            dim.issues.extend(issues)
            dim.issues.extend([i for i in semgrep_findings if i.file_path == fpath])
        crit = len([i for i in dim.issues if i.severity == 'critical'])
        warn = len([i for i in dim.issues if i.severity == 'warning'])
        dim.score = max(0, 100 - crit * 10 - warn * 3)
        return dim

    def _analyze_idioms(self, files_lines):
        dim = DimensionScore(name="Ruby 惯用法", score=100, weight=0.11)
        for fpath, lines in files_lines.items():
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if re.search(r'\.each\s+do\s*\|.\|\s*\n\s*\w+\[.\]\s*=', s):
                    dim.score -= 2
                if s == 'return nil':
                    dim.score -= 1
                    dim.issues.append(Issue(severity='info', file_path=fpath, line_number=i,
                        description='不必要的 return nil', suggestion='Ruby 隐式返回 nil', metric=s[:60]))
        dim.score = max(0, dim.score)
        return dim

    def _analyze_solid(self, files_lines):
        dim = DimensionScore(name="SOLID 原则", score=100, weight=0.10)
        for fpath, lines in files_lines.items():
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if re.match(r'class\s+\w+', s):
                    methods = sum(1 for l in lines if re.match(r'\s*def\s+', l.strip()))
                    if methods > 15:
                        dim.score -= 5
                        dim.issues.append(Issue(severity='warning', file_path=fpath, line_number=i,
                            description=f'类方法数 {methods}，建议 ≤ 15', suggestion='拆分职责 (SRP)', metric=f'{methods} 个方法'))
        dim.score = max(0, dim.score)
        return dim
