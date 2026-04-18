"""Rust analyzer using regex-based analysis with Semgrep integration."""
import re
import os
from .base import BaseAnalyzer, AnalysisResult, Issue, DimensionScore
from .tools import run_semgrep, map_semgrep_result, get_tool_version


class RustAnalyzer(BaseAnalyzer):
    LANGUAGE = "rust"
    FILE_EXTENSIONS = ['.rs']

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
            self._analyze_idioms(files_lines),
            self._analyze_error_handling(files_lines),
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
                if not s or s.startswith('//'):
                    continue
                for ch in s:
                    if ch == '{': depth += 1
                    elif ch == '}': depth = max(0, depth - 1)
                if re.match(r'^\s*(if|else|for|while|loop|match|if let)\b', s):
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
                # Rust: fn snake_case, struct/trait PascalCase
                m = re.match(r'fn\s+([A-Z]\w+)', s)
                if m:
                    dim.score -= 3
                    dim.issues.append(Issue(
                        severity='warning', file_path=fpath, line_number=i,
                        description=f'函数名 "{m.group(1)}" 应使用 snake_case',
                        suggestion='Rust 函数命名规范为 snake_case',
                        metric=m.group(1)
                    ))
                m = re.match(r'struct\s+([a-z]\w*)', s)
                if m:
                    dim.score -= 3
                    dim.issues.append(Issue(
                        severity='warning', file_path=fpath, line_number=i,
                        description=f'结构体名 "{m.group(1)}" 应使用 PascalCase',
                        suggestion='Rust 类型命名规范为 PascalCase',
                        metric=m.group(1)
                    ))
        dim.score = max(0, dim.score)
        return dim

    def _analyze_comments(self, files_lines):
        dim = DimensionScore(name="注释覆盖率", score=100, weight=0.10)
        total = comment = 0
        for fpath, lines in files_lines.items():
            in_doc = False
            for line in lines:
                s = line.strip()
                if not s: continue
                total += 1
                if in_doc:
                    comment += 1
                    if '*/' in s: in_doc = False
                elif s.startswith('///') or s.startswith('//') or s.startswith('/*!') or s.startswith('//!'):
                    comment += 1
                elif s.startswith('/*'):
                    comment += 1
                    if '*/' not in s: in_doc = True
        if total:
            ratio = comment / total
            if ratio < 0.05:
                dim.score = 40
                dim.issues.append(Issue(
                    severity='warning', file_path='', line_number=0,
                    description=f'注释覆盖率仅 {ratio:.1%}，建议 ≥ 10%',
                    suggestion='使用 /// 为公共 API 添加文档注释',
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
                    if re.match(r'^\s*(?:pub\s+)?fn\s+\w+', s) and '{' in s:
                        func_start = i
                        brace_count = s.count('{') - s.count('}')
                        if brace_count <= 0: func_start = None
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
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if re.search(r'\bunsafe\b', s) and 'fn' not in s:
                    dim.issues.append(Issue(
                        severity='warning', file_path=fpath, line_number=i,
                        description='使用了 unsafe 代码块',
                        suggestion='确保 unsafe 块有充分的安全注释说明',
                        metric=s[:60]
                    ))
                if re.search(r'\bunwrap\(\)', s) and 'test' not in fpath:
                    dim.issues.append(Issue(
                        severity='info', file_path=fpath, line_number=i,
                        description='使用了 .unwrap() 可能导致 panic',
                        suggestion='使用 match 或 ? 操作符处理错误',
                        metric=s[:60]
                    ))
            dim.issues.extend(issues)
            dim.issues.extend([i for i in semgrep_findings if i.file_path == fpath])
        crit = len([i for i in dim.issues if i.severity == 'critical'])
        warn = len([i for i in dim.issues if i.severity == 'warning'])
        dim.score = max(0, 100 - crit * 10 - warn * 3)
        return dim

    def _analyze_idioms(self, files_lines):
        dim = DimensionScore(name="Rust 惯用法", score=100, weight=0.11)
        for fpath, lines in files_lines.items():
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if re.search(r'\bclone\(\)', s) and re.search(r'&', s):
                    dim.score -= 1
                if re.search(r'\bString::from\(&', s):
                    pass  # good
                if re.search(r'\bto_string\(\)', s) and 'format!' not in s:
                    pass  # ok
                if re.search(r'\b\.collect::<Vec<_>>\(\)\.iter\(\)', s):
                    dim.score -= 2
                    dim.issues.append(Issue(
                        severity='info', file_path=fpath, line_number=i,
                        description='不必要的 collect 后 iter',
                        suggestion='直接使用迭代器链',
                        metric=s[:60]
                    ))
        dim.score = max(0, dim.score)
        return dim

    def _analyze_error_handling(self, files_lines):
        dim = DimensionScore(name="错误处理", score=100, weight=0.10)
        for fpath, lines in files_lines.items():
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if re.search(r'\bpanic!\(', s):
                    dim.score -= 3
                    dim.issues.append(Issue(
                        severity='warning', file_path=fpath, line_number=i,
                        description='使用了 panic!，库代码中不建议直接 panic',
                        suggestion='返回 Result<T, E> 让调用方决定',
                        metric=s[:60]
                    ))
                if re.search(r'\bexpect\(', s) and 'test' not in fpath:
                    dim.score -= 1
        dim.score = max(0, dim.score)
        return dim
