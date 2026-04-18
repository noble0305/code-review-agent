"""C# analyzer using regex-based analysis."""
import re
from .base import BaseAnalyzer, AnalysisResult, Issue, DimensionScore
from .tools import run_semgrep, map_semgrep_result, get_tool_version

class CSharpAnalyzer(BaseAnalyzer):
    LANGUAGE = "csharp"
    FILE_EXTENSIONS = ['.cs', '.csx']
    tools_status = {}

    def analyze(self, project_path, file_list=None):
        files = self.collect_files(project_path, file_list)
        if not files: return AnalysisResult(language=self.LANGUAGE)
        result = AnalysisResult(language=self.LANGUAGE, file_count=len(files), analyzed_files=files)
        fl = {}
        for f in files:
            lines, err = self.read_file(f)
            if not err: fl[f] = lines; result.total_lines += len(lines)
        sr, sok = run_semgrep(project_path, timeout=60)
        sf = [map_semgrep_result(r) for r in sr] if sok else []
        self.tools_status = {'semgrep': {'available': sok, 'version': get_tool_version('sempeg') if sok else None, 'findings': len(sr)}}
        result.dimensions = [self._complexity(fl), self._duplicates(fl), self._naming(fl), self._comments(fl),
                             self._func_length(fl), self._security(fl, sf), self._modern(fl), self._solid(fl)]
        for d in result.dimensions: result.all_issues.extend(d.issues)
        result.total_score = round(self.compute_total_score(result.dimensions), 1)
        return result

    def _complexity(self, fl):
        dim = DimensionScore(name="代码复杂度", score=100, weight=0.20)
        for fp, lines in fl.items():
            depth = 0
            for i, l in enumerate(lines, 1):
                s = l.strip()
                if not s or s.startswith('//'): continue
                depth += s.count('{') - s.count('}')
                if re.match(r'^\s*(if|else|for|foreach|while|do|switch|case|catch|try|using)\b', s): depth += 1
                if depth > 5:
                    dim.score = max(0, dim.score - 1.5)
                    if depth > 8: dim.issues.append(Issue(severity='warning', file_path=fp, line_number=i,
                        description=f'嵌套深度 {depth} 层', suggestion='提取方法', metric=f'深度 {depth}'))
        return dim

    def _duplicates(self, fl):
        dim = DimensionScore(name="代码重复率", score=100, weight=0.12)
        issues = self.detect_duplicate_code(fl, 6); dim.issues = issues[:20]; dim.score = max(0, 100 - len(issues) * 3)
        return dim

    def _naming(self, fl):
        dim = DimensionScore(name="命名规范", score=100, weight=0.10)
        for fp, lines in fl.items():
            for i, l in enumerate(lines, 1):
                s = l.strip()
                # C# methods: PascalCase
                m = re.match(r'(?:public|private|protected|internal)\s+\w+\s+([a-z]\w+)\s*\(', s)
                if m:
                    dim.score -= 2; dim.issues.append(Issue(severity='info', file_path=fp, line_number=i,
                        description=f'方法名 "{m.group(1)}" 应使用 PascalCase', suggestion='C# 方法名使用 PascalCase', metric=m.group(1)))
        dim.score = max(0, dim.score); return dim

    def _comments(self, fl):
        dim = DimensionScore(name="注释覆盖率", score=100, weight=0.10)
        total = comment = 0
        for fp, lines in fl.items():
            in_b = False
            for l in lines:
                s = l.strip()
                if not s: continue
                total += 1
                if in_b: comment += 1;
                if '*/' in s: in_b = False
                elif s.startswith('//') or s.startswith('///') or s.startswith('/*'): comment += 1
                if s.startswith('/*') and '*/' not in s: in_b = True
        if total:
            r = comment / total; dim.score = 95 if r >= 0.10 else 70 if r >= 0.05 else 40
        return dim

    def _func_length(self, fl):
        dim = DimensionScore(name="方法长度", score=100, weight=0.12)
        for fp, lines in fl.items():
            fs = None; bc = 0
            for i, l in enumerate(lines, 1):
                s = l.strip()
                if fs is None:
                    if re.match(r'\s*(?:public|private|protected|internal|static|\w+\s+)\w+\s+\w+\s*\(', s) and '{' in s:
                        fs = i; bc = s.count('{') - s.count('}')
                        if bc <= 0: fs = None
                else:
                    bc += s.count('{') - s.count('}')
                    if bc <= 0:
                        ln = i - fs
                        if ln > 80: dim.score = max(0, dim.score - 5); dim.issues.append(Issue(severity='warning', file_path=fp, line_number=fs,
                            description=f'方法长度 {ln} 行', suggestion='拆分方法', metric=f'{ln} 行'))
                        elif ln > 50: dim.score = max(0, dim.score - 2)
                        fs = None; bc = 0
        return dim

    def _security(self, fl, sf):
        dim = DimensionScore(name="安全隐患", score=100, weight=0.15)
        for fp, lines in fl.items():
            issues = self.detect_security_issues_regex(lines, fp)
            for i, l in enumerate(lines, 1):
                s = l.strip()
                if re.search(r'SqlCommand\s*\(\s*"', s):
                    dim.issues.append(Issue(severity='critical', file_path=fp, line_number=i,
                        description='可能存在 SQL 注入', suggestion='使用参数化查询', metric=s[:60]))
            dim.issues.extend(issues); dim.issues.extend([i for i in sf if i.file_path == fp])
        crit = len([i for i in dim.issues if i.severity == 'critical']); warn = len([i for i in dim.issues if i.severity == 'warning'])
        dim.score = max(0, 100 - crit * 10 - warn * 3); return dim

    def _modern(self, fl):
        dim = DimensionScore(name="现代 C# 实践", score=100, weight=0.11)
        for fp, lines in fl.items():
            for i, l in enumerate(lines, 1):
                s = l.strip()
                if re.search(r'\bvar\b', s) and re.search(r'\bnew\s+List<', s):
                    pass  # good
                if re.search(r'String\.Format|String\.Concat', s):
                    dim.score -= 1; dim.issues.append(Issue(severity='info', file_path=fp, line_number=i,
                        description='建议使用字符串插值 $""', suggestion='使用 $"..." 替代 String.Format', metric=s[:60]))
        dim.score = max(0, dim.score); return dim

    def _solid(self, fl):
        dim = DimensionScore(name="SOLID 原则", score=100, weight=0.10)
        for fp, lines in fl.items():
            for i, l in enumerate(lines, 1):
                s = l.strip()
                if re.match(r'(public|internal)\s+class\s+\w+', s):
                    methods = sum(1 for ll in lines if re.match(r'\s*(public|private|protected)\s+\w+\s+\w+\s*\(', ll.strip()))
                    if methods > 15: dim.score -= 5; dim.issues.append(Issue(severity='warning', file_path=fp, line_number=i,
                        description=f'类方法数 {methods}', suggestion='拆分职责 (SRP)', metric=f'{methods} 个'))
        dim.score = max(0, dim.score); return dim
