"""自定义规则加载模块。"""
import os
import fnmatch
from typing import Dict, List, Any, Optional


# 默认阈值
DEFAULT_THRESHOLDS = {
    'max_function_length': 50,
    'max_complexity': 10,
    'min_comment_ratio': 0.10,
    'max_imports': 20,
}

# 默认权重
DEFAULT_WEIGHTS = {
    'complexity': 0.20,
    'duplicates': 0.12,
    'naming': 0.10,
    'comments': 0.10,
    'function_length': 0.12,
    'security': 0.15,
    'dependencies': 0.08,
    'solid': 0.13,
}


def load_yaml_file(path: str) -> dict:
    """加载 YAML 文件。"""
    if not os.path.isfile(path):
        return {}
    try:
        import yaml
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return {}
    except Exception:
        return {}


def load_project_rules(project_path: str, config_rules: dict = None) -> Dict[str, Any]:
    """从项目目录加载 .reviewrc 配置。

    合并逻辑：项目 .reviewrc > config.yaml 中的 rules > 默认值
    """
    # 加载项目 .reviewrc
    rc_path = os.path.join(project_path, '.reviewrc')
    rc_path_yaml = rc_path + '.yaml' if not rc_path.endswith('.yaml') else rc_path
    rc_path_yml = rc_path + '.yml'

    project_rules = {}
    if os.path.isfile(rc_path):
        project_rules = load_yaml_file(rc_path)
    elif os.path.isfile(rc_path_yaml):
        project_rules = load_yaml_file(rc_path_yaml)
    elif os.path.isfile(rc_path_yml):
        project_rules = load_yaml_file(rc_path_yml)

    # 合并配置
    rules = {
        'ignore': project_rules.get('ignore', (config_rules or {}).get('ignore', [])),
        'thresholds': {**DEFAULT_THRESHOLDS, **(config_rules or {}).get('thresholds', {}), **project_rules.get('thresholds', {})},
        'weights': {**DEFAULT_WEIGHTS, **(config_rules or {}).get('weights', {}), **project_rules.get('weights', {})},
        'severity_overrides': project_rules.get('severity_overrides', (config_rules or {}).get('severity_overrides', [])),
    }

    return rules


def should_ignore(file_path: str, project_path: str, ignore_patterns: List[str]) -> bool:
    """检查文件是否应该被忽略。

    Args:
        file_path: 文件绝对路径
        project_path: 项目根目录
        ignore_patterns: 忽略模式列表（支持 glob）
    """
    rel_path = os.path.relpath(file_path, project_path)
    for pattern in ignore_patterns:
        if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(os.path.basename(file_path), pattern):
            return True
    return False


def apply_severity_override(description: str, severity_overrides: List[Dict]) -> str:
    """应用严重程度覆盖规则。"""
    import re
    for rule in severity_overrides:
        pattern = rule.get('pattern', '')
        target_severity = rule.get('severity', 'info')
        if pattern and re.search(pattern, description):
            return target_severity
    return None  # 未匹配，保持原始 severity
