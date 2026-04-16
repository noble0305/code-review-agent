"""Python analyzer using AST for deep analysis with Ruff and Semgrep integration."""
import ast
import re
import os
from collections import defaultdict
from .base import BaseAnalyzer, AnalysisResult, Issue, DimensionScore
from .tools import (run_ruff, run_semgrep, map_ruff_result, map_semgrep_result,
                    is_tool_available, get_tool_version)


class PythonAnalyzer(BaseAnalyzer):
    LANGUAGE = "python"
    FILE_EXTENSIONS = ['.py']
    
    # Tool status tracking
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
        
        # Run external tools
        ruff_results, ruff_ok = run_ruff(project_path)
        semgrep_results, semgrep_ok = run_semgrep(project_path, timeout=60)
        
        # Track tool status
        self.tools_status = {
            'ruff': {
                'available': ruff_ok,
                'version': get_tool_version('ruff') if ruff_ok else None,
                'findings': len(ruff_results),
            },
            'semgrep': {
                'available': semgrep_ok,
                'version': get_tool_version('semgrep') if semgrep_ok else None,
                'findings': len(semgrep_results),
            }
        }
        
        # Map Ruff results by dimension
        ruff_by_dim = defaultdict(list)
        ruff_general = []
        if ruff_ok:
            for r in ruff_results:
                mapped = map_ruff_result(r)
                if mapped:
                    if mapped["dimension"]:
                        ruff_by_dim[mapped["dimension"]].append(mapped)
                    else:
                        ruff_general.append(mapped)
        
        # Map Semgrep results (security only)
        semgrep_findings = []
        if semgrep_ok:
            semgrep_findings = [map_semgrep_result(r) for r in semgrep_results]
        
        # 1. Complexity — prefer Ruff, fallback to AST
        dim_complexity = self._analyze_complexity(files_lines, ruff_by_dim.get("complexity", []))
        # 2. Duplicates
        dim_duplicates = self._analyze_duplicates(files_lines)
        # 3. Naming — prefer Ruff, fallback to AST
        dim_naming = self._analyze_naming(files_lines, ruff_by_dim.get("naming", []))
        # 4. Comments (AST only)
        dim_comments = self._analyze_comments(files_lines)
        # 5. Function length — prefer Ruff, fallback to AST
        dim_func_len = self._analyze_function_length(files_lines, ruff_by_dim.get("function_length", []))
        # 6. Security — prefer Semgrep, fallback to regex
        dim_security = self._analyze_security(files_lines, semgrep_findings)
        # 7. Dependencies — prefer Ruff, fallback to AST
        dim_deps = self._analyze_dependencies(files_lines, ruff_by_dim.get("dependencies", []))
        # 8. SOLID (AST only, plus Ruff general findings)
        dim_solid = self._analyze_solid(files_lines, ruff_general)
        
        result.dimensions = [dim_complexity, dim_duplicates, dim_naming, dim_comments,
                             dim_func_len, dim_security, dim_deps, dim_solid]
        for d in result.dimensions:
            result.all_issues.extend(d.issues)
        result.total_score = round(self.compute_total_score(result.dimensions), 1)
        return result
    
    def _parse_ast(self, source: str):
        try:
            return ast.parse(source)
        except SyntaxError:
            return None

    # --- 1. Complexity ---
    def _analyze_complexity(self, files_lines, ruff_issues=None):
        dim = DimensionScore(name="代码复杂度", score=100, weight=0.20)
        # Use Ruff results if available
        if ruff_issues:
            for ri in ruff_issues:
                dim.issues.append(Issue(
                    'warning' if 'C901' in ri['code'] else 'info',
                    ri['file_path'], ri['line'],
                    ri['message'],
                    '拆分函数，降低分支数量',
                    f"Ruff {ri['code']}"
                ))
                dim.score = max(0, dim.score - 3)
            dim.details = f"Ruff 检测到 {len(ruff_issues)} 个复杂度问题，共 {len(files_lines)} 个文件"
            dim.score = max(0, min(100, dim.score))
            return dim
        
        # Fallback to AST
        for fpath, lines in files_lines.items():
            source = ''.join(lines)
            tree = self._parse_ast(source)
            if not tree:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    cc = self._cyclomatic_complexity(node)
                    if cc > self.MAX_CyclOMATIC_CRITICAL:
                        dim.issues.append(Issue('critical', fpath, node.lineno,
                            f'函数 "{node.name}" 圈复杂度过高', '拆分函数，降低分支数量',
                            f'圈复杂度 {cc}，建议 ≤ {self.MAX_CyclOMATIC_WARNING}'))
                        dim.score = max(0, dim.score - cc * 1.5)
                    elif cc > self.MAX_CyclOMATIC_WARNING:
                        dim.issues.append(Issue('warning', fpath, node.lineno,
                            f'函数 "{node.name}" 圈复杂度偏高', '考虑拆分函数减少分支',
                            f'圈复杂度 {cc}，建议 ≤ {self.MAX_CyclOMATIC_WARNING}'))
                        dim.score = max(0, dim.score - cc * 0.8)
        dim.score = max(0, min(100, dim.score))
        dim.details = f"共检查 {len(files_lines)} 个文件"
        return dim

    def _cyclomatic_complexity(self, func_node):
        cc = 1
        for node in ast.walk(func_node):
            if isinstance(node, (ast.If, ast.IfExp)):
                cc += 1
            elif isinstance(node, ast.For):
                cc += 1
            elif isinstance(node, ast.While):
                cc += 1
            elif isinstance(node, ast.ExceptHandler):
                cc += 1
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                cc += 1
            elif isinstance(node, ast.BoolOp):
                cc += len(node.values) - 1
            # comprehensions
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                cc += sum(1 for _ in node.generators)
        return cc

    # --- 2. Duplicates ---
    def _analyze_duplicates(self, files_lines):
        dim = DimensionScore(name="代码重复率", score=100, weight=0.12)
        issues = self.detect_duplicate_code(files_lines)
        dim.issues = issues[:20]
        if issues:
            dim.score = max(0, 100 - len(issues) * 5)
        dim.details = f"检测到 {len(issues)} 处重复代码块"
        return dim

    # --- 3. Naming ---
    def _analyze_naming(self, files_lines, ruff_issues=None):
        dim = DimensionScore(name="命名规范", score=100, weight=0.10)
        bad_patterns = 0
        # Use Ruff results if available
        if ruff_issues:
            for ri in ruff_issues:
                dim.issues.append(Issue(
                    'info', ri['file_path'], ri['line'],
                    ri['message'],
                    '遵循 PEP 8 命名规范',
                    f"Ruff {ri['code']}"
                ))
                bad_patterns += 1
            dim.score = max(0, 100 - bad_patterns * 2)
            dim.details = f"Ruff 发现 {bad_patterns} 处命名不规范"
            return dim
        
        # Fallback to AST
        for fpath, lines in files_lines.items():
            source = ''.join(lines)
            tree = self._parse_ast(source)
            if not tree:
                continue
            for node in ast.walk(tree):
                # Function names should be snake_case
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = node.name
                    if not name.startswith('_') and not re.match(r'^[a-z_][a-z0-9_]*$', name):
                        dim.issues.append(Issue('info', fpath, node.lineno,
                            f'函数名 "{name}" 不符合 snake_case 规范',
                            f'建议改为 snake_case 风格，如 "{re.sub(r"([A-Z])", r"_\1", name).lower().lstrip("_")}"'))
                        bad_patterns += 1
                # Class names should be PascalCase
                elif isinstance(node, ast.ClassDef):
                    name = node.name
                    if not re.match(r'^[A-Z][a-zA-Z0-9]*$', name):
                        dim.issues.append(Issue('info', fpath, node.lineno,
                            f'类名 "{name}" 不符合 PascalCase 规范', '建议使用 PascalCase 风格命名类'))
                        bad_patterns += 1
                # Variable names - check for single letter or too short
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    name = node.id
                    if len(name) == 1 and name not in ('i', 'j', 'k', 'x', 'y', 'z', '_', 'e', 'f', 'n', 'm'):
                        dim.issues.append(Issue('info', fpath, node.lineno,
                            f'变量名 "{name}" 过于简短', '使用更具描述性的变量名'))
                        bad_patterns += 1
        dim.score = max(0, 100 - bad_patterns * 2)
        dim.details = f"发现 {bad_patterns} 处命名不规范"
        return dim

    # --- 4. Comments ---
    def _analyze_comments(self, files_lines):
        dim = DimensionScore(name="注释覆盖率", score=100, weight=0.10)
        total_comment = 0
        total_code = 0
        for fpath, lines in files_lines.items():
            for line in lines:
                s = line.strip()
                if not s:
                    continue
                if s.startswith('#') or s.startswith('"""') or s.startswith("'''"):
                    total_comment += 1
                else:
                    total_code += 1
        
        total = total_comment + total_code
        if total == 0:
            return dim
        ratio = total_comment / total
        if ratio < self.MIN_COMMENT_RATIO:
            dim.score = max(0, ratio / self.MIN_COMMENT_RATIO * 100)
            dim.issues.append(Issue('warning', '', 0,
                f'注释覆盖率 {ratio:.1%}，低于建议的 {self.MIN_COMMENT_RATIO:.0%}',
                '增加关键函数和复杂逻辑的注释',
                metric=f'注释行 {total_comment} / 总行 {total}'))
        dim.details = f"注释覆盖率 {ratio:.1%}"
        return dim

    # --- 5. Function length ---
    def _analyze_function_length(self, files_lines, ruff_issues=None):
        dim = DimensionScore(name="函数长度", score=100, weight=0.12)
        func_count = 0
        # Use Ruff results if available
        if ruff_issues:
            for ri in ruff_issues:
                dim.issues.append(Issue(
                    'warning', ri['file_path'], ri['line'],
                    ri['message'],
                    '将函数拆分为多个小函数，每个函数只做一件事',
                    f"Ruff {ri['code']}"
                ))
                dim.score = max(0, dim.score - 5)
            dim.details = f"Ruff 检测到 {len(ruff_issues)} 个函数长度问题"
            return dim
        
        # Fallback to AST
        for fpath, lines in files_lines.items():
            source = ''.join(lines)
            tree = self._parse_ast(source)
            if not tree:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    length = node.end_lineno - node.lineno + 1 if hasattr(node, 'end_lineno') and node.end_lineno else 0
                    func_count += 1
                    if length > self.MAX_FUNCTION_LENGTH_CRITICAL:
                        dim.issues.append(Issue('critical', fpath, node.lineno,
                            f'函数 "{node.name}" 过长', '将函数拆分为多个小函数，每个函数只做一件事',
                            f'{length} 行，建议 ≤ {self.MAX_FUNCTION_LENGTH_WARNING} 行'))
                        dim.score = max(0, dim.score - 8)
                    elif length > self.MAX_FUNCTION_LENGTH_WARNING:
                        dim.issues.append(Issue('warning', fpath, node.lineno,
                            f'函数 "{node.name}" 较长', '考虑拆分此函数',
                            f'{length} 行，建议 ≤ {self.MAX_FUNCTION_LENGTH_WARNING} 行'))
                        dim.score = max(0, dim.score - 3)
        dim.details = f"共 {func_count} 个函数/方法"
        return dim

    # --- 6. Security ---
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
            for iss in issues:
                dim.score = max(0, dim.score - 10)
        dim.details = f"发现 {len(dim.issues)} 个安全隐患"
        return dim

    # --- 7. Dependencies ---
    def _analyze_dependencies(self, files_lines, ruff_issues=None):
        dim = DimensionScore(name="依赖管理", score=100, weight=0.08)
        # Use Ruff results if available
        if ruff_issues:
            for ri in ruff_issues:
                sev = 'warning' if ri['code'].startswith('F401') else 'info'
                dim.issues.append(Issue(
                    sev, ri['file_path'], ri['line'],
                    ri['message'],
                    '移除未使用的导入，保持依赖精简',
                    f"Ruff {ri['code']}"
                ))
                dim.score = max(0, dim.score - 5)
            dim.details = f"Ruff 检测到 {len(ruff_issues)} 个依赖问题"
            return dim
        
        # Fallback to AST
        for fpath, lines in files_lines.items():
            source = ''.join(lines)
            tree = self._parse_ast(source)
            if not tree:
                continue
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for alias in node.names:
                        imports.append(f"{module}.{alias.name}")
            if len(imports) > self.MAX_IMPORTS_WARNING:
                dim.issues.append(Issue('warning', fpath, 1,
                    f'导入数量过多（{len(imports)} 个）', '检查是否有未使用的导入，拆分模块职责',
                    metric=f'{len(imports)} 个导入'))
                dim.score = max(0, dim.score - 15)
        dim.details = "检查各文件导入数量"
        return dim

    # --- 8. SOLID ---
    def _analyze_solid(self, files_lines, ruff_general=None):
        dim = DimensionScore(name="SOLID 原则", score=100, weight=0.13)
        # Add Ruff general findings as SOLID issues
        if ruff_general:
            for ri in ruff_general[:10]:
                dim.issues.append(Issue(
                    'info', ri['file_path'], ri['line'],
                    ri['message'],
                    '参考 Ruff 建议优化代码结构',
                    f"Ruff {ri['code']}"
                ))
                dim.score = max(0, dim.score - 2)
        
        for fpath, lines in files_lines.items():
            source = ''.join(lines)
            tree = self._parse_ast(source)
            if not tree:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                    if len(methods) > 15:
                        dim.issues.append(Issue('warning', fpath, node.lineno,
                            f'类 "{node.name}" 方法数过多（{len(methods)} 个）',
                            '可能违反单一职责原则，考虑拆分类',
                            metric=f'{len(methods)} 个方法'))
                        dim.score = max(0, dim.score - 8)
                    
                    # Check for God class (too many lines)
                    if hasattr(node, 'end_lineno') and node.end_lineno:
                        cls_lines = node.end_lineno - node.lineno
                        if cls_lines > 300:
                            dim.issues.append(Issue('warning', fpath, node.lineno,
                                f'类 "{node.name}" 代码量过大（{cls_lines} 行）',
                                '考虑拆分为多个更小的类',
                                metric=f'{cls_lines} 行'))
                            dim.score = max(0, dim.score - 5)
        dim.details = "检查单一职责原则"
        return dim
