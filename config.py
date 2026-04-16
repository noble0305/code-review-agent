"""Configuration management for code review agent."""
import os
from pathlib import Path


class Config:
    """Configuration manager with environment variable and file support."""

    def __init__(self):
        # Load YAML config if exists
        self._yaml_config = self._load_yaml_config()

    def _load_yaml_config(self):
        """Load config.yaml if it exists."""
        config_path = Path(__file__).parent / "config.yaml"
        if not config_path.exists():
            return {}
        try:
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except ImportError:
            return {}
        except Exception:
            return {}

    def get(self, key, default=None):
        """Get config value: env var > yaml > default."""
        # Check environment variable first
        env_key = key.upper()
        if env_key in os.environ:
            return os.environ[env_key]

        # Check nested YAML keys with dot notation
        keys = key.split('.')
        value = self._yaml_config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value if value is not None else default

    def get_llm_config(self):
        """Get LLM-specific configuration."""
        return {
            'provider': self.get('llm.provider', 'openai'),
            'model': self.get('llm.model', 'gpt-4o-mini'),
            'api_key': os.getenv('LLM_API_KEY', self.get('llm.api_key', '')),
            'base_url': os.getenv('LLM_BASE_URL', self.get('llm.base_url', '')),
            'max_tokens': int(self.get('llm.max_tokens', 2048)),
            'temperature': float(self.get('llm.temperature', 0.3)),
            'timeout': int(self.get('llm.timeout', 60)),
            'features': self.get('llm.features', {
                'smart_suggestion': True,
                'overall_summary': True,
                'interactive_chat': True,
                'code_explain': True,
                'max_issues_to_enhance': 10,
                'context_lines': 10
            })
        }

    def get_tools_config(self):
        """Get tools-specific configuration."""
        return self.get('tools', {
            'ruff': {'timeout': 60},
            'semgrep': {'timeout': 60, 'config': 'auto'}
        })

    def get_project_config(self):
        """Get project-specific configuration."""
        return self.get('project', {
            'max_file_size': 500000,
            'skip_dirs': [
                '.git', 'node_modules', '__pycache__',
                'venv', '.venv', 'dist', 'build', 'vendor', 'target'
            ]
        })


# Global config instance
config = Config()
