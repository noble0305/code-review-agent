"""Go analyzer using regex-based analysis with Semgrep integration."""
import re
from .base import BaseAnalyzer, AnalysisResult, Issue, DimensionScore
from .tools import run_semgrep, map_semgrep_result, get_tool_version


class GoAnalyzer(BaseAnalyzer):
    LANGUAGE = "go"
    FILE_EXTENSIONS = ['.go']
    
    tools_status = {}
    
    def analyze(self, project_path: str) -> AnalysisResult:
        files = self.collect_files(project_path)
        if not files:
            return AnalysisResult(language=self.LANGUAGE)
        
        result = AnalysisResult(language=self.LANGUAGE, file_count=len(files), analyzed_files=files)
        files_lines = {}
        for f in files:
            lines, err = self.read_file(f)
            if not err:
                files_lines[f] = lines
                result.total_lines += len(lines)
        
        # Run Semgrep for security
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
            self._analyze_dependencies(files_lines),
            self._analyze_solid(files_lines),
        ]
        for d in result.dimensions:
            result.all_issues.extend(d.issues)
        result.total_score = round(self.compute_total_score(result.dimensions), 1)
        return result
    
    def _analyze_complexity(self, files_lines):
        dim = DimensionScore(name="代码复杂度", score=100, weight=0.20)
        for fpath, lines in files_lines.items():
            source = ''.join(lines)
            for m in re.finditer(r'func\s+(?:\([^)]+\)\s*)?(\w+)\s*\([^)]*\)', source):
                fname = m.group(1)
                start = m.start()
                brace = 0
                end_pos = start
                found_brace = False
                for idx in range(source.find('{', start) if '{' in source[start:] else len(source), len(source)):
                    if source[idx] == '{': brace += 1; found_brace = True
                    elif source[idx] == '}': brace -= 1
                    if found_brace and brace == 0: end_pos = idx; break
                body = source[start:end_pos]
                branches = len(re.findall(r'\bif\b|\belse\b|\bfor\b|\bswitch\b|\bcase\b|\bselect\b|&&|\|\|', body))
                if branches > self.MAX_CyclOMATIC_CRITICAL:
                    dim.issues.append(Issue('critical', fpath, source[:start].count('\n')+1,
                        f'函数 "{fname}" 圈复杂度过高', '拆分函数',
                        f'圈复杂度 {branches}，建议 ≤ {self.MAX_CyclOMATIC_WARNING}'))
                    dim.score = max(0, dim.score - branches)
                elif branches > self.MAX_CyclOMATIC_WARNING:
                    dim.issues.append(Issue('warning', fpath, source[:start].count('\n')+1,
                        f'函数 "{fname}" 圈复杂度偏高', '简化逻辑',
                        f'圈复杂度 {branches}'))
                    dim.score = max(0, dim.score - branches * 0.5)
        dim.details = f"共检查 {len(files_lines)} 个文件"
        return dim
    
    def _analyze_duplicates(self, files_lines):
        dim = DimensionScore(name="代码重复率", score=100, weight=0.12)
        issues = self.detect_duplicate_code(files_lines)
        dim.issues = issues[:20]
        if issues: dim.score = max(0, 100 - len(issues) * 5)
        dim.details = f"检测到 {len(issues)} 处重复代码块"
        return dim
    
    def _analyze_naming(self, files_lines):
        dim = DimensionScore(name="命名规范", score=100, weight=0.10)
        bad = 0
        for fpath, lines in files_lines.items():
            source = ''.join(lines)
            # Exported names should be PascalCase (they are by default in Go)
            # Check for camelCase in exported functions (should be PascalCase)
            for m in re.finditer(r'func\s+(?:\([^)]+\)\s*)?([a-z]\w+)', source):
                name = m.group(1)
                # Unexported are fine as lowercase, check for mixedCase issues
                if re.search(r'[A-Z]', name[1:]):
                    dim.issues.append(Issue('info', fpath, source[:m.start()].count('\n')+1,
                        f'函数名 "{name}" 命名风格不一致', 'Go 建议使用 camelCase（未导出）或 PascalCase（导出）'))
                    bad += 1
        dim.score = max(0, 100 - bad * 2)
        dim.details = f"发现 {bad} 处命名不规范"
        return dim
    
    def _analyze_comments(self, files_lines):
        dim = DimensionScore(name="注释覆盖率", score=100, weight=0.10)
        total_c = total_code = 0
        for fpath, lines in files_lines.items():
            in_block = False
            for line in lines:
                s = line.strip()
                if not s: continue
                if in_block:
                    total_c += 1
                    if '*/' in s: in_block = False
                    continue
                if s.startswith('//'):
                    total_c += 1
                elif s.startswith('/*'):
                    total_c += 1
                    if '*/' not in s: in_block = True
                else:
                    total_code += 1
        total = total_c + total_code
        if total == 0: return dim
        ratio = total_c / total
        if ratio < self.MIN_COMMENT_RATIO:
            dim.score = max(0, ratio / self.MIN_COMMENT_RATIO * 100)
            dim.issues.append(Issue('warning', '', 0,
                f'注释覆盖率 {ratio:.1%}，偏低', '增加 godoc 注释',
                metric=f'注释 {total_c} / 总计 {total}'))
        dim.details = f"注释覆盖率 {ratio:.1%}"
        return dim
    
    def _analyze_function_length(self, files_lines):
        dim = DimensionScore(name="函数长度", score=100, weight=0.12)
        for fpath, lines in files_lines.items():
            source = ''.join(lines)
            for m in re.finditer(r'func\s+(?:\([^)]+\)\s*)?(\w+)\s*\([^)]*\)', source):
                start = m.start()
                lineno = source[:start].count('\n') + 1
                brace = 0
                end_pos = start
                found = False
                for idx in range(source.find('{', start) if '{' in source[start:] else len(source), len(source)):
                    if source[idx] == '{': brace += 1; found = True
                    elif source[idx] == '}': brace -= 1
                    if found and brace == 0: end_pos = idx; break
                func_lines = source[start:end_pos].count('\n') + 1
                if func_lines > self.MAX_FUNCTION_LENGTH_CRITICAL:
                    dim.issues.append(Issue('critical', fpath, lineno,
                        f'函数 "{m.group(1)}" 过长', '拆分为多个小函数',
                        f'{func_lines} 行，建议 ≤ {self.MAX_FUNCTION_LENGTH_WARNING}'))
                    dim.score = max(0, dim.score - 8)
                elif func_lines > self.MAX_FUNCTION_LENGTH_WARNING:
                    dim.issues.append(Issue('warning', fpath, lineno,
                        f'函数 "{m.group(1)}" 较长', '考虑拆分',
                        f'{func_lines} 行'))
                    dim.score = max(0, dim.score - 3)
        dim.details = "检查函数长度分布"
        return dim
    
    def _analyze_security(self, files_lines, semgrep_findings=None):
        dim = DimensionScore(name="安全隐患", score=100, weight=0.15)
        # Use Semgrep results if available
        if semgrep_findings:
            for sf in semgrep_findings:
                sev = 'critical' if sf.get('severity') == 'ERROR' else 'warning'
                dim.issues.append(Issue(
                    sev, sf['file_path'], sf['line'],
                    sf['message'] or sf.get('check_id', '安全问题'),
                    '修复安全问题，参考 Semgrep 建议',
                    f"Semgrep: {sf.get('check_id', '')}"
                ))
                dim.score = max(0, dim.score - (10 if sev == 'critical' else 5))
            dim.details = f"Semgrep 检测到 {len(semgrep_findings)} 个安全问题"
            return dim
        
        # Fallback to regex
        for fpath, lines in files_lines.items():
            issues = self.detect_security_issues_regex(lines, fpath)
            dim.issues.extend(issues)
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if re.search(r'os\.Exec', s):
                    dim.issues.append(Issue('critical', fpath, i, '可能执行外部命令', '确保不执行不可信输入'))
                    dim.score = max(0, dim.score - 10)
            for _ in issues:
                dim.score = max(0, dim.score - 10)
        dim.details = f"发现 {len(dim.issues)} 个安全隐患"
        return dim
    
    def _analyze_dependencies(self, files_lines):
        dim = DimensionScore(name="依赖管理", score=100, weight=0.08)
        for fpath, lines in files_lines.items():
            source = ''.join(lines)
            imports = re.findall(r'"[^"]+"', source[source.find('import'):source.find(')')+1] if 'import' in source else '')
            if len(imports) > self.MAX_IMPORTS_WARNING:
                dim.issues.append(Issue('warning', fpath, 1,
                    f'导入数量过多（{len(imports)} 个）', '审查并精简依赖',
                    metric=f'{len(imports)} 个导入'))
                dim.score = max(0, dim.score - 15)
        dim.details = "检查导入数量"
        return dim
    
    def _analyze_solid(self, files_lines):
        dim = DimensionScore(name="SOLID 原则", score=100, weight=0.13)
        # Go uses structs, check methods per struct
        for fpath, lines in files_lines.items():
            source = ''.join(lines)
            structs = re.finditer(r'type\s+(\w+)\s+struct', source)
            for m in structs:
                sname = m.group(1)
                lineno = source[:m.start()].count('\n') + 1
                methods = re.findall(rf'func\s*\([^)]*\*?{sname}\w*\)\s*\w+', source)
                if len(methods) > 15:
                    dim.issues.append(Issue('warning', fpath, lineno,
                        f'结构体 "{sname}" 方法数过多', '考虑拆分职责',
                        metric=f'{len(methods)} 个方法'))
                    dim.score = max(0, dim.score - 8)
        dim.details = "检查单一职责原则"
        return dim
