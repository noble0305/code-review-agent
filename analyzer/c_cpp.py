"""C/C++ analyzer using regex-based analysis with Semgrep integration."""
import re
import os
from .base import BaseAnalyzer, AnalysisResult, Issue, DimensionScore
from .tools import run_semgrep, map_semgrep_result, get_tool_version


class CAnalyzer(BaseAnalyzer):
    LANGUAGE = "c_cpp"
    FILE_EXTENSIONS = ['.c', '.cpp', '.cc', '.cxx', '.h', '.hpp', '.hxx']

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
        self.tools_status = {
            'semgrep': {
                'available': semgrep_ok,
                'version': get_tool_version('semgrep') if semgrep_ok else None,
                'findings': len(semgrep_results),
            }
        }

        result.dimensions = [
            self._analyze_complexity(files_lines),
            self._analyze_duplicates(files_lines),
            self._analyze_naming(files_lines),
            self._analyze_comments(files_lines),
            self._analyze_function_length(files_lines),
            self._analyze_security(files_lines, semgrep_findings),
            self._analyze_memory(files_lines),
            self._analyze_modern(files_lines),
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
                if not s or s.startswith('//') or s.startswith('/*'):
                    continue
                for ch in s:
                    if ch == '{': depth += 1
                    elif ch == '}': depth = max(0, depth - 1)
                if re.match(r'^\s*(if|else|for|while|switch|case|catch|do)\b', s):
                    depth += 1
                if depth > 5:
                    dim.score = max(0, dim.score - 1.5)
                    if depth > 8:
                        dim.issues.append(Issue(
                            severity='warning', file_path=fpath, line_number=i,
                            description=f'嵌套深度 {depth} 层，建议 ≤ 5',
                            suggestion='提取为独立函数减少嵌套',
                            metric=f'嵌套深度 {depth}'
                        ))
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
                m = re.match(r'(?:void|int|char|float|double|long|bool|auto|std::\w+)\s+\**\s*(\w+)\s*\(', s)
                if m:
                    name = m.group(1)
                    if len(name) <= 2 and name not in ('fn', 'id', 'ok', 'fp', 'cb'):
                        dim.score -= 1
                        dim.issues.append(Issue(
                            severity='info', file_path=fpath, line_number=i,
                            description=f'函数名 "{name}" 过短',
                            suggestion='使用更具描述性的名称',
                            metric=name
                        ))
        dim.score = max(0, dim.score)
        return dim

    def _analyze_comments(self, files_lines):
        dim = DimensionScore(name="注释覆盖率", score=100, weight=0.10)
        total = comment = 0
        for fpath, lines in files_lines.items():
            in_block = False
            for line in lines:
                s = line.strip()
                if not s:
                    continue
                total += 1
                if in_block:
                    comment += 1
                    if '*/' in s: in_block = False
                elif s.startswith('//') or s.startswith('/*'):
                    comment += 1
                    if '/*' in s and '*/' not in s: in_block = True
                elif s.startswith('*'):
                    comment += 1
        if total:
            ratio = comment / total
            if ratio < 0.05:
                dim.score = 40
                dim.issues.append(Issue(
                    severity='warning', file_path='', line_number=0,
                    description=f'注释覆盖率仅 {ratio:.1%}，建议 ≥ 10%',
                    suggestion='为关键函数和复杂逻辑添加注释',
                    metric=f'{ratio:.1%}'
                ))
            elif ratio < 0.10:
                dim.score = 70
            else:
                dim.score = 95
        return dim

    def _analyze_function_length(self, files_lines):
        dim = DimensionScore(name="函数长度", score=100, weight=0.12)
        for fpath, lines in files_lines.items():
            func_start = None
            brace_count = 0
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if func_start is None:
                    if re.match(r'^\s*(?:void|int|char|float|double|long|bool|auto|std::\w+|[A-Z]\w+)\s+\**\s*\w+\s*\(', s):
                        if '{' in s:
                            func_start = i
                            brace_count = s.count('{') - s.count('}')
                            if brace_count <= 0:
                                func_start = None
                else:
                    brace_count += s.count('{') - s.count('}')
                    length = i - func_start
                    if brace_count <= 0:
                        if length > 80:
                            dim.score = max(0, dim.score - 5)
                            dim.issues.append(Issue(
                                severity='warning', file_path=fpath, line_number=func_start,
                                description=f'函数长度 {length} 行，建议 ≤ 50',
                                suggestion='拆分为多个小函数',
                                metric=f'{length} 行'
                            ))
                        elif length > 50:
                            dim.score = max(0, dim.score - 2)
                        func_start = None
                        brace_count = 0
        return dim

    def _analyze_security(self, files_lines, semgrep_findings):
        dim = DimensionScore(name="安全隐患", score=100, weight=0.15)
        for fpath, lines in files_lines.items():
            issues = self.detect_security_issues_regex(lines, fpath)
            # C/C++ specific
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if re.search(r'\b(gets|scanf)\s*\(', s):
                    dim.issues.append(Issue(
                        severity='critical', file_path=fpath, line_number=i,
                        description='使用了不安全的输入函数',
                        suggestion='使用 fgets/scanf_s 替代',
                        metric=s[:60]
                    ))
                if re.search(r'\bstrcpy|strcat|sprintf\b', s) and '#include' not in s:
                    dim.issues.append(Issue(
                        severity='critical', file_path=fpath, line_number=i,
                        description='使用了不安全的字符串函数',
                        suggestion='使用 strncpy/strncat/snprintf 替代',
                        metric=s[:60]
                    ))
                if re.search(r'\bmalloc\s*\(', s) and 'free' not in s:
                    pass  # just note
            dim.issues.extend(issues)
            dim.issues.extend([i for i in semgrep_findings if i.file_path == fpath])
        if dim.issues:
            dim.score = max(0, 100 - len([i for i in dim.issues if i.severity == 'critical']) * 10 - len([i for i in dim.issues if i.severity == 'warning']) * 3)
        return dim

    def _analyze_memory(self, files_lines):
        dim = DimensionScore(name="内存管理", score=100, weight=0.11)
        mallocs = {}
        for fpath, lines in files_lines.items():
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if re.search(r'\bmalloc|calloc|realloc|new\b', s):
                    mallocs[fpath] = mallocs.get(fpath, 0) + 1
                if re.search(r'\bfree|delete\b', s):
                    mallocs[fpath] = mallocs.get(fpath, 0) - 1
                if re.search(r'\bdelete\[\]', s) and not re.search(r'\bnew\[\]', s):
                    dim.issues.append(Issue(
                        severity='warning', file_path=fpath, line_number=i,
                        description='delete[] 与 new[] 不匹配可能导致未定义行为',
                        suggestion='确保 new/delete、new[]/delete[] 配对使用',
                        metric=s[:60]
                    ))
        for fp, count in mallocs.items():
            if count > 3:
                dim.score -= 5
                dim.issues.append(Issue(
                    severity='warning', file_path=fp, line_number=0,
                    description=f'可能的内存泄漏（{count} 处未释放）',
                    suggestion='确保每个 malloc/new 都有对应的 free/delete',
                    metric=f'{count} 处'
                ))
        dim.score = max(0, dim.score)
        return dim

    def _analyze_modern(self, files_lines):
        dim = DimensionScore(name="现代 C++ 实践", score=100, weight=0.10)
        for fpath, lines in files_lines.items():
            has_cpp = fpath.endswith(('.cpp', '.cc', '.cxx', '.hpp'))
            if not has_cpp:
                continue
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if re.search(r'\bNULL\b', s):
                    dim.score -= 2
                    dim.issues.append(Issue(
                        severity='info', file_path=fpath, line_number=i,
                        description='C++ 中建议使用 nullptr 替代 NULL',
                        suggestion='使用 nullptr',
                        metric=s[:60]
                    ))
                if re.search(r'\braw\s+pointer\b|\bint\s*\*\s+\w+\s*=', s):
                    dim.score -= 2
        dim.score = max(0, dim.score)
        return dim
