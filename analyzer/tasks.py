"""异步任务管理模块 - 使用线程实现简单异步。"""
import threading
import uuid
import time
from typing import Dict, Optional, Any, Callable


class TaskManager:
    """简单的线程任务管理器。"""

    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def submit(self, func: Callable, kwargs: dict = None) -> str:
        """提交任务，返回 task_id。"""
        task_id = str(uuid.uuid4())[:8]
        with self._lock:
            self._tasks[task_id] = {
                'id': task_id,
                'status': 'pending',
                'result': None,
                'error': None,
                'created_at': time.time(),
                'completed_at': None,
            }

        def _run():
            with self._lock:
                self._tasks[task_id]['status'] = 'running'
            try:
                result = func(**(kwargs or {}))
                with self._lock:
                    self._tasks[task_id]['status'] = 'completed'
                    self._tasks[task_id]['result'] = result
                    self._tasks[task_id]['completed_at'] = time.time()
            except Exception as e:
                with self._lock:
                    self._tasks[task_id]['status'] = 'failed'
                    self._tasks[task_id]['error'] = str(e)
                    self._tasks[task_id]['completed_at'] = time.time()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """查询任务状态。"""
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> list:
        """列出所有任务。"""
        with self._lock:
            return list(self._tasks.values())


# 全局任务管理器
task_manager = TaskManager()
