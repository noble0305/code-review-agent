"""SQLite 存储模块 - 分析结果持久化和增量分析支持。"""
import os
import json
import hashlib
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any


# 数据库文件路径
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
DB_PATH = os.path.join(DB_DIR, 'reviews.db')


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接。"""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """初始化数据库表。"""
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_path TEXT NOT NULL,
                language TEXT NOT NULL,
                total_score REAL NOT NULL,
                file_count INTEGER NOT NULL,
                total_lines INTEGER NOT NULL,
                dimensions_json TEXT NOT NULL,
                llm_summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_analyses_project ON analyses(project_path);
            CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at);

            CREATE TABLE IF NOT EXISTS file_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER NOT NULL,
                project_path TEXT NOT NULL,
                file_path TEXT NOT NULL,
                md5_hash TEXT NOT NULL,
                FOREIGN KEY (analysis_id) REFERENCES analyses(id)
            );
            CREATE INDEX IF NOT EXISTS idx_file_hashes_project ON file_hashes(project_path);

            CREATE TABLE IF NOT EXISTS webhooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    finally:
        conn.close()


def save_analysis(project_path: str, language: str, result_dict: dict, llm_summary: str = None) -> int:
    """保存分析结果，返回记录 ID。"""
    init_db()
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO analyses (project_path, language, total_score, file_count, total_lines, dimensions_json, llm_summary) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_path, language, result_dict.get('total_score', 0), result_dict.get('file_count', 0),
             result_dict.get('total_lines', 0), json.dumps(result_dict.get('dimensions', []), ensure_ascii=False), llm_summary)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_analyses(limit: int = 50, project_path: str = None) -> List[Dict[str, Any]]:
    """列出分析历史。"""
    init_db()
    conn = _get_conn()
    try:
        if project_path:
            rows = conn.execute(
                "SELECT id, project_path, language, total_score, file_count, total_lines, llm_summary, created_at FROM analyses WHERE project_path = ? ORDER BY created_at DESC LIMIT ?",
                (project_path, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, project_path, language, total_score, file_count, total_lines, llm_summary, created_at FROM analyses ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_analysis(analysis_id: int) -> Optional[Dict[str, Any]]:
    """获取单次分析详情。"""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, project_path, language, total_score, file_count, total_lines, dimensions_json, llm_summary, created_at FROM analyses WHERE id = ?",
            (analysis_id,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result['dimensions'] = json.loads(result['dimensions_json'])
        del result['dimensions_json']
        return result
    finally:
        conn.close()


def compare_analyses(id1: int, id2: int) -> Optional[Dict[str, Any]]:
    """对比两次分析结果。"""
    a1 = get_analysis(id1)
    a2 = get_analysis(id2)
    if not a1 or not a2:
        return None

    # 对比维度分数
    dims1 = {d['name']: d['score'] for d in a1.get('dimensions', [])}
    dims2 = {d['name']: d['score'] for d in a2.get('dimensions', [])}
    dim_diff = {}
    for name in set(list(dims1.keys()) + list(dims2.keys())):
        s1 = dims1.get(name, 0)
        s2 = dims2.get(name, 0)
        dim_diff[name] = {'before': s1, 'after': s2, 'change': round(s2 - s1, 1)}

    return {
        'before': {'id': id1, 'total_score': a1['total_score'], 'created_at': a1['created_at']},
        'after': {'id': id2, 'total_score': a2['total_score'], 'created_at': a2['created_at']},
        'score_change': round(a2['total_score'] - a1['total_score'], 1),
        'file_count_change': a2['file_count'] - a1['file_count'],
        'lines_change': a2['total_lines'] - a1['total_lines'],
        'dimension_diff': dim_diff,
    }


def save_file_hashes(analysis_id: int, project_path: str, file_hashes: Dict[str, str]):
    """保存文件哈希缓存。"""
    init_db()
    conn = _get_conn()
    try:
        # 清除该项目的旧哈希
        conn.execute("DELETE FROM file_hashes WHERE project_path = ?", (project_path,))
        for fpath, md5 in file_hashes.items():
            conn.execute(
                "INSERT INTO file_hashes (analysis_id, project_path, file_path, md5_hash) VALUES (?, ?, ?, ?)",
                (analysis_id, project_path, fpath, md5)
            )
        conn.commit()
    finally:
        conn.close()


def get_file_hashes(project_path: str) -> Dict[str, str]:
    """返回项目上次分析的文件哈希。"""
    init_db()
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT file_path, md5_hash FROM file_hashes WHERE project_path = ?",
            (project_path,)
        ).fetchall()
        return {r['file_path']: r['md5_hash'] for r in rows}
    finally:
        conn.close()


def get_changed_files_since_last(project_path: str, current_files: Dict[str, str] = None) -> Optional[List[str]]:
    """对比当前文件哈希，返回变更文件列表。第一次分析返回 None。"""
    old_hashes = get_file_hashes(project_path)
    if not old_hashes:
        return None  # 第一次分析，全量扫描

    if current_files is None:
        # 计算当前哈希需要调用者传入，这里只做对比
        return list(old_hashes.keys())  # 降级：全部重新分析

    changed = []
    for fpath, md5 in current_files.items():
        if fpath not in old_hashes or old_hashes[fpath] != md5:
            changed.append(fpath)
    # 删除的文件不需要重新分析
    return changed if changed else []


def compute_file_md5(file_path: str) -> str:
    """计算文件 MD5。"""
    h = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
    except Exception:
        return ''
    return h.hexdigest()


# Webhook 持久化
def register_webhook(url: str, description: str = '') -> int:
    init_db()
    conn = _get_conn()
    try:
        cursor = conn.execute("INSERT INTO webhooks (url, description) VALUES (?, ?)", (url, description))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def delete_webhook(webhook_id: int) -> bool:
    init_db()
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def list_webhooks() -> List[Dict[str, Any]]:
    init_db()
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT id, url, description, created_at FROM webhooks").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
