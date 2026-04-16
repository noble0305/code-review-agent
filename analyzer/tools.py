"""Tool wrappers for Ruff and Semgrep analysis backends."""
import json
import subprocess
import shutil
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Cache for tool availability
_tool_cache: Dict[str, Optional[str]] = {}


def is_tool_available(tool_name: str) -> bool:
    """Check if a CLI tool is available on PATH."""
    return shutil.which(tool_name) is not None


def get_tool_version(tool_name: str) -> Optional[str]:
    """Get version string for a tool, cached."""
    if tool_name in _tool_cache:
        return _tool_cache[tool_name]
    try:
        result = subprocess.run(
            [tool_name, "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            # Extract version number from output like "ruff 0.4.4"
            version = result.stdout.strip().split()[-1] if result.stdout.strip() else None
            _tool_cache[tool_name] = version
            return version
    except Exception:
        pass
    _tool_cache[tool_name] = None
    return None


def run_tool(command: List[str], timeout: int = 60) -> Tuple[Optional[str], Optional[str], int]:
    """Run a subprocess command with timeout handling.
    
    Returns (stdout, stderr, returncode). Returns (None, error_msg, -1) on failure.
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        logger.warning(f"Tool timed out after {timeout}s: {' '.join(command)}")
        return None, f"命令超时（{timeout}秒）", -1
    except FileNotFoundError:
        return None, f"工具未找到: {command[0]}", -1
    except Exception as e:
        return None, str(e), -1


def run_ruff(path: str) -> Tuple[List[dict], bool]:
    """Run Ruff check on a path, return (results_list, success).
    
    Returns parsed JSON results or empty list on failure.
    """
    if not is_tool_available("ruff"):
        return [], False

    stdout, stderr, rc = run_tool(
        ["ruff", "check", "--output-format=json", path],
        timeout=60
    )
    if stdout is None:
        return [], False

    try:
        results = json.loads(stdout) if stdout.strip() else []
        return results if isinstance(results, list) else [], True
    except json.JSONDecodeError:
        return [], False


def run_semgrep(path: str, timeout: int = 60) -> Tuple[List[dict], bool]:
    """Run Semgrep on a path, return (findings_list, success).
    
    Returns parsed findings or empty list on failure.
    """
    if not is_tool_available("semgrep"):
        return [], False

    stdout, stderr, rc = run_tool(
        ["semgrep", "--json", "--config", "auto", path],
        timeout=timeout
    )
    if stdout is None:
        return [], False

    try:
        data = json.loads(stdout)
        results = data.get("results", [])
        return results, True
    except json.JSONDecodeError:
        return [], False


# --- Ruff rule to dimension mapping ---

RUFF_DIMENSION_MAP = {
    # Complexity
    "C901": "complexity",
    "PLR0912": "complexity",  # too many branches
    "PLR0913": "complexity",  # too many arguments
    # Naming
    "N801": "naming", "N802": "naming", "N803": "naming", "N804": "naming",
    "N805": "naming", "N806": "naming", "N807": "naming", "N811": "naming",
    "N812": "naming", "N813": "naming", "N814": "naming", "N815": "naming",
    "N816": "naming", "N817": "naming", "N818": "naming",
    # Function length / complexity
    "C3001": "function_length", "C3002": "function_length",
    "PLR0915": "function_length",  # too many statements
    # Dependencies / imports
    "F401": "dependencies",  # unused import
    "F811": "dependencies",  # redefined-while-unused
    "F601": "dependencies",
    "F821": "dependencies",  # undefined name
    "F841": "dependencies",  # unused variable
}


def map_ruff_result(result: dict) -> Optional[dict]:
    """Map a single Ruff result to our dimension structure.
    Returns None if rule doesn't map to any dimension."""
    code = result.get("code", "")
    # Some ruff versions use code, others use rule
    if not code:
        code = result.get("rule", "")
    
    # Try prefix matching for rules like "N801", "N802", etc.
    dimension = None
    for rule_prefix, dim in RUFF_DIMENSION_MAP.items():
        if code.startswith(rule_prefix) or code == rule_prefix:
            dimension = dim
            break
    
    return {
        "dimension": dimension,  # None means "general" → SOLID or general advice
        "code": code,
        "message": result.get("message", ""),
        "file_path": result.get("filename", ""),
        "line": result.get("location", {}).get("row", 0),
        "end_line": result.get("end_location", {}).get("row", 0),
    }


def map_semgrep_result(result: dict) -> dict:
    """Map a Semgrep finding to our security dimension."""
    return {
        "check_id": result.get("check_id", ""),
        "message": result.get("extra", {}).get("message", ""),
        "severity": result.get("extra", {}).get("severity", "WARNING"),
        "file_path": result.get("path", ""),
        "line": result.get("start", {}).get("line", 0),
        "metadata": result.get("extra", {}).get("metadata", {}),
    }
