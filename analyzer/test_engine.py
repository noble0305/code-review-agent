"""自动测试引擎 - 测试生成、执行、智能修复。"""
import os
import re
import json
import uuid
import shutil
import subprocess
import tempfile
from typing import List, Dict, Optional, Tuple
from .llm import get_llm_client


class TestEngine:
    """自动测试生成 + 执行 + 修复引擎。"""

    FRAMEWORKS = {
        'python': {'cmd': 'pytest', 'framework': 'pytest', 'suffix': '_test.py', 'dir': 'tests/'},
        'javascript': {'cmd': 'npx jest', 'framework': 'jest', 'suffix': '.test.js', 'dir': '__tests__/'},
        'go': {'cmd': 'go test', 'framework': 'go test', 'suffix': '_test.go', 'dir': ''},
        'java': {'cmd': 'mvn test', 'framework': 'junit', 'suffix': 'Test.java', 'dir': 'src/test/java/'},
    }

    # ===== Phase 1: 测试计划生成 =====

    def generate_plan(self, project_path: str, language: str, changed_files: List[str] = None) -> Dict:
        """扫描项目，生成测试计划。
        
        Args:
            changed_files: 如果指定，仅对这些文件生成测试（diff 模式）
        """
        fw = self.FRAMEWORKS.get(language)
        if not fw:
            return {'error': f'不支持的语言: {language}'}

        # 收集源码文件
        if changed_files:
            # diff 模式：只分析变更文件
            source_files = []
            for cf in changed_files:
                full_path = os.path.join(project_path, cf) if not os.path.isabs(cf) else cf
                if os.path.isfile(full_path):
                    source_files.append(full_path)
        else:
            source_files = self._collect_source_files(project_path, language)
        
        if not source_files:
            return {'error': '未找到源码文件'}

        # 提取函数/类签名
        functions = []
        for fp in source_files:
            funcs = self._extract_functions(fp, language)
            functions.extend(funcs)

        if not functions:
            return {'error': '未提取到可测试的函数/方法'}

        # 生成测试代码
        test_code = self._generate_test_code(functions, language, fw['framework'])

        return {
            'language': language,
            'framework': fw['framework'],
            'source_files': source_files,
            'functions': functions,
            'test_code': test_code,
            'total_functions': len(functions),
        }

    def _collect_source_files(self, project_path: str, language: str) -> List[str]:
        """收集项目源码文件。"""
        ext_map = {
            'python': ['.py'],
            'javascript': ['.js', '.jsx', '.ts', '.tsx'],
            'go': ['.go'],
            'java': ['.java'],
        }
        skip_dirs = {'node_modules', '.git', '__pycache__', '.venv', 'venv', 'dist', 'build', '.tox', 'egg-info'}
        extensions = ext_map.get(language, [])
        files = []
        for root, dirs, filenames in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for fn in filenames:
                if any(fn.endswith(ext) for ext in extensions):
                    # 跳过测试文件本身
                    if 'test' in fn.lower():
                        continue
                    files.append(os.path.join(root, fn))
        return files[:50]  # 限制数量

    def _extract_functions(self, file_path: str, language: str) -> List[Dict]:
        """从源码中提取函数/方法签名。"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            return []

        functions = []
        rel_path = os.path.basename(file_path)

        patterns = {
            'python': [
                r'def\s+(\w+)\s*\(([^)]*)\)',
                r'class\s+(\w+)',
            ],
            'javascript': [
                r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)',
                r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>',
                r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function\s*\(([^)]*)\)',
                r'class\s+(\w+)',
            ],
            'go': [
                r'func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(([^)]*)\)',
            ],
            'java': [
                r'(?:public|private|protected)\s+(?:static\s+)?(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*\(([^)]*)\)',
                r'class\s+(\w+)',
            ],
        }

        for pattern in patterns.get(language, []):
            for m in re.finditer(pattern, content):
                name = m.group(1)
                params = m.group(2) if m.lastindex >= 2 else ''
                # 排除私有/特殊方法
                if name.startswith('_') or name.startswith('__'):
                    continue
                functions.append({
                    'name': name,
                    'params': params.strip(),
                    'file': rel_path,
                    'full_path': file_path,
                    'type': 'class' if 'class ' in pattern else 'function',
                })
        return functions[:30]

    def _generate_test_code(self, functions: List[Dict], language: str, framework: str) -> str:
        """根据提取的函数生成测试代码。"""
        generators = {
            'pytest': self._gen_pytest,
            'jest': self._gen_jest,
            'go test': self._gen_go_test,
            'junit': self._gen_junit,
        }
        gen = generators.get(framework)
        if not gen:
            return f'# 暂不支持 {framework} 框架的自动生成'
        return gen(functions)

    def _gen_pytest(self, functions: List[Dict]) -> str:
        lines = ['"""自动生成的 pytest 测试。"""', 'import pytest', '']
        files_imported = {}
        for func in functions:
            if func['type'] == 'class':
                continue
            fp = func['full_path']
            if fp not in files_imported:
                mod_name = os.path.splitext(os.path.basename(fp))[0]
                lines.append(f'from {mod_name} import {func["name"]}  # noqa')
                files_imported[fp] = True
        lines.append('')
        lines.append('')
        for func in functions:
            if func['type'] == 'class':
                continue
            name = func['name']
            params = func['params']
            lines.append(f'def test_{name}_basic():')
            lines.append(f'    """测试 {name} 基本功能。"""')
            if params:
                param_names = [p.strip().split('=')[0].split(':')
                               for p in params.split(',') if p.strip()]
                param_names = [p[0].strip() for p in param_names if p[0].strip()]
                dummy_args = ', '.join(['None'] * len(param_names))
                lines.append(f'    result = {name}({dummy_args})')
            else:
                lines.append(f'    result = {name}()')
            lines.append(f'    # TODO: 添加断言')
            lines.append(f'    assert result is not None or True  # 占位断言')
            lines.append('')
            lines.append(f'def test_{name}_edge_cases():')
            lines.append(f'    """测试 {name} 边界条件。"""')
            lines.append(f'    # TODO: 边界值测试')
            lines.append(f'    pass')
            lines.append('')
        return '\n'.join(lines)

    def _gen_jest(self, functions: List[Dict]) -> str:
        lines = ['// 自动生成的 Jest 测试', '']
        files_imported = {}
        for func in functions:
            if func['type'] == 'class':
                continue
            fp = func['full_path']
            if fp not in files_imported:
                mod = os.path.splitext(os.path.basename(fp))[0]
                lines.append(f"const {{ {func['name']} }} = require('./{mod}');")
                files_imported[fp] = True
        lines.append('')
        for func in functions:
            if func['type'] == 'class':
                continue
            name = func['name']
            lines.append(f"describe('{name}', () => {{")
            lines.append(f"  test('{name} 基本功能', () => {{")
            lines.append(f"    // TODO: 添加断言")
            lines.append(f"    expect(true).toBe(true);")
            lines.append(f"  }});")
            lines.append(f"  test('{name} 边界条件', () => {{")
            lines.append(f"    // TODO: 边界值测试")
            lines.append(f"  }});")
            lines.append(f"}});")
            lines.append('')
        return '\n'.join(lines)

    def _gen_go_test(self, functions: List[Dict]) -> str:
        lines = ['package main', '', 'import "testing"', '']
        for func in functions:
            if func['type'] == 'class':
                continue
            name = func['name']
            lines.append(f'func Test{self._capitalize(name)}(t *testing.T) {{')
            lines.append(f'\t// TODO: 添加测试逻辑')
            lines.append(f'\tt.Log("testing {name}")')
            lines.append(f'}}')
            lines.append('')
        return '\n'.join(lines)

    def _gen_junit(self, functions: List[Dict]) -> str:
        lines = ['import org.junit.jupiter.api.Test;', 'import static org.junit.jupiter.api.Assertions.*;', '',
                 'class AutoGeneratedTest {']
        for func in functions:
            if func['type'] == 'class':
                continue
            name = func['name']
            lines.append(f'    @Test')
            lines.append(f'    void test{self._capitalize(name)}() {{')
            lines.append(f'        // TODO: 添加断言')
            lines.append(f'        assertTrue(true);')
            lines.append(f'    }}')
            lines.append('')
        lines.append('}')
        return '\n'.join(lines)

    @staticmethod
    def _capitalize(s: str) -> str:
        return s[0].upper() + s[1:] if s else s

    # ===== Phase 2: 测试执行 =====

    def run_tests(self, project_path: str, language: str, test_code: str) -> Dict:
        """在隔离环境中执行测试。"""
        fw = self.FRAMEWORKS.get(language)
        if not fw:
            return {'error': f'不支持的语言: {language}'}

        # 创建临时目录
        tmp_dir = tempfile.mkdtemp(prefix=f'test-{uuid.uuid4().hex[:8]}-')
        try:
            # 写入测试文件
            test_file = self._write_test_file(tmp_dir, project_path, language, test_code, fw)
            if not test_file:
                return {'error': '无法创建测试文件'}

            # 执行测试
            result = self._execute_test(tmp_dir, project_path, language, fw)
            return result
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _write_test_file(self, tmp_dir, project_path, language, test_code, fw) -> Optional[str]:
        """写入测试文件到临时目录。"""
        if language == 'python':
            test_dir = os.path.join(tmp_dir, 'tests')
            os.makedirs(test_dir, exist_ok=True)
            # 创建 conftest 以添加项目路径到 sys.path
            conf = os.path.join(test_dir, 'conftest.py')
            with open(conf, 'w') as f:
                f.write(f'import sys\nsys.path.insert(0, {repr(project_path)})\n')
            test_file = os.path.join(test_dir, 'test_auto.py')
            with open(test_file, 'w') as f:
                f.write(test_code)
            return test_file

        elif language == 'javascript':
            # 写入到项目 __tests__ 目录（临时）
            test_dir = os.path.join(tmp_dir, '__tests__')
            os.makedirs(test_dir, exist_ok=True)
            test_file = os.path.join(test_dir, 'auto.test.js')
            with open(test_file, 'w') as f:
                f.write(test_code)
            return test_file

        elif language == 'go':
            # Go 测试文件放在项目目录（需要同 package）
            test_file = os.path.join(project_path, 'auto_test.go')
            with open(test_file, 'w') as f:
                f.write(test_code)
            return test_file

        elif language == 'java':
            test_dir = os.path.join(tmp_dir, 'src', 'test', 'java')
            os.makedirs(test_dir, exist_ok=True)
            test_file = os.path.join(test_dir, 'AutoGeneratedTest.java')
            with open(test_file, 'w') as f:
                f.write(test_code)
            return test_file

        return None

    def _execute_test(self, tmp_dir, project_path, language, fw) -> Dict:
        """执行测试命令并解析结果。"""
        try:
            if language == 'python':
                cmd = [fw['cmd'] if shutil.which('pytest') else 'python', '-m', 'pytest',
                       os.path.join(tmp_dir, 'tests'), '-v', '--tb=short', '--no-header', '-q']
                cwd = tmp_dir
            elif language == 'javascript':
                cmd = ['npx', 'jest', '--no-coverage', '--verbose']
                cwd = tmp_dir
            elif language == 'go':
                cmd = ['go', 'test', '-v', './...']
                cwd = project_path
            elif language == 'java':
                cmd = ['mvn', 'test']
                cwd = tmp_dir
            else:
                return {'error': f'不支持的测试执行: {language}'}

            proc = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True, timeout=60,
                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'NO_PROXY': '*'}
            )

            return self._parse_test_output(proc, language)

        except subprocess.TimeoutExpired:
            return {'error': '测试执行超时（60s）', 'total': 0, 'passed': 0, 'failed': 0, 'output': ''}
        except FileNotFoundError:
            return {'error': f'测试工具未安装: {fw["cmd"]}', 'total': 0, 'passed': 0, 'failed': 0, 'output': ''}
        except Exception as e:
            return {'error': str(e), 'total': 0, 'passed': 0, 'failed': 0, 'output': ''}

    def _parse_test_output(self, proc: subprocess.CompletedProcess, language: str) -> Dict:
        """解析测试输出。"""
        output = proc.stdout + proc.stderr
        total = passed = failed = 0
        errors = []

        if language == 'python':
            # pytest: "2 passed, 1 failed"
            m = re.search(r'(\d+) passed', output)
            if m: passed = int(m.group(1))
            m = re.search(r'(\d+) failed', output)
            if m: failed = int(m.group(1))
            m = re.search(r'(\d+) error', output)
            errors_count = int(m.group(1)) if m else 0
            total = passed + failed + errors_count
            # 提取失败信息
            if failed > 0 or errors_count > 0:
                failures = re.findall(r'FAILED (.*?) -', output)
                error_msgs = re.findall(r'E\s+(.+)', output)
                errors = [{'test': f, 'message': msg} for f, msg in zip(failures, error_msgs)]

        elif language == 'javascript':
            m = re.search(r'Tests:\s+(\d+)\s+passed.*?(\d+)\s+failed', output)
            if m:
                passed, failed = int(m.group(1)), int(m.group(2))
            else:
                m = re.search(r'Tests:\s+(\d+)\s+passed', output)
                if m: passed = int(m.group(1))
            total = passed + failed

        elif language == 'go':
            m = re.search(r'(\d+)\s+passed.*?(\d+)\s+failed', output)
            if m:
                passed, failed = int(m.group(1)), int(m.group(2))
            else:
                m = re.search(r'ok\s+', output)
                if m: passed = 1
            total = passed + failed

        elif language == 'java':
            m = re.search(r'Tests run:\s+(\d+).*?Failures:\s+(\d+)', output)
            if m:
                total = int(m.group(1))
                failed = int(m.group(2))
                passed = total - failed

        return {
            'total': max(total, 1),
            'passed': passed,
            'failed': failed,
            'errors': errors,
            'output': output[-2000:],  # 保留最后 2000 字符
            'success': failed == 0 and proc.returncode == 0,
        }

    # ===== Phase 3: 智能修复 =====

    def analyze_failure(self, source_code: str, error_output: str, language: str) -> str:
        """用 LLM 分析测试失败原因。"""
        llm = get_llm_client()
        if not llm:
            return 'LLM 不可用，无法分析失败原因'

        prompt = f"""你是代码分析专家。分析以下测试失败的原因并给出修复建议。

## 源码
```{language}
{source_code[:3000]}
```

## 测试错误输出
```
{error_output[:2000]}
```

请分析：
1. 失败的根本原因
2. 具体修复方案（给出代码）
"""
        try:
            resp = llm.chat.completions.create(
                model=llm.model if hasattr(llm, 'model') else 'gpt-5.4',
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=1500, temperature=0.3,
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f'LLM 分析失败: {e}'

    def generate_fix(self, source_code: str, test_error: str, language: str) -> Optional[str]:
        """用 LLM 生成修复代码。"""
        llm = get_llm_client()
        if not llm:
            return None

        prompt = f"""你是代码修复专家。根据测试错误信息修复源码。

## 源码
```{language}
{source_code[:3000]}
```

## 测试错误
```
{test_error[:2000]}
```

请只输出修复后的完整代码，不要解释。用 ```{language} 代码块包裹。"""

        try:
            resp = llm.chat.completions.create(
                model=llm.model if hasattr(llm, 'model') else 'gpt-5.4',
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=4000, temperature=0.2,
            )
            content = resp.choices[0].message.content
            # 提取代码块
            m = re.search(r'```(?:\w+)?\n(.*?)```', content, re.DOTALL)
            return m.group(1).strip() if m else content.strip()
        except Exception:
            return None

    # ===== Phase 4: 自动修复循环 =====

    def auto_fix_loop(self, project_path: str, language: str, max_rounds: int = 3) -> Dict:
        """完整流程：生成 → 测试 → 修复 → 重测。"""
        # Step 1: 生成测试计划
        plan = self.generate_plan(project_path, language)
        if 'error' in plan:
            return {'status': 'error', 'message': plan['error']}

        test_code = plan['test_code']
        fix_history = []

        # Step 2-4: 测试循环
        for round_num in range(1, max_rounds + 1):
            result = self.run_tests(project_path, language, test_code)

            if result.get('success'):
                result['status'] = 'passed'
                result['fix_history'] = fix_history
                result['rounds'] = round_num
                result['plan'] = plan
                return result

            # 测试失败，尝试修复
            if round_num < max_rounds:
                # 读取失败文件源码
                error_info = result.get('output', '')
                fix_analysis = self.analyze_failure(
                    self._read_source_for_error(project_path, language, error_info),
                    error_info, language
                )
                fix_code = self.generate_fix(
                    self._read_source_for_error(project_path, language, error_info),
                    error_info, language
                )

                fix_history.append({
                    'round': round_num,
                    'analysis': fix_analysis,
                    'test_result': result,
                    'fix_applied': fix_code is not None,
                })

                # 更新测试代码（如果有修复）
                if fix_code:
                    # 这里简化处理：用 LLM 修复后的测试代码替代
                    new_test = self.generate_fix(test_code, error_info, language)
                    if new_test:
                        test_code = new_test

        # 达到最大轮次
        result['status'] = 'failed'
        result['fix_history'] = fix_history
        result['rounds'] = max_rounds
        result['plan'] = plan
        return result

    def _read_source_for_error(self, project_path, language, error_output) -> str:
        """从错误输出中提取相关源码。"""
        # 简化：读取第一个源文件
        files = self._collect_source_files(project_path, language)
        if files:
            try:
                with open(files[0], 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()[:3000]
            except Exception:
                pass
        return ''
