import uuid
import queue
import logging
import threading
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Priority(Enum):
    LOW = 3
    NORMAL = 2
    HIGH = 1
    CRITICAL = 0


@dataclass
class Task:
    task_id: str
    task_type: str
    description: str
    payload: dict
    priority: Priority
    created_at: datetime
    assigned_to: Optional[str] = None
    status: str = "pending"
    result: Optional[Any] = None
    error: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3
    timeout: int = 60

    def __lt__(self, other):
        return self.priority.value < other.priority.value


class TaskQueue:
    def __init__(self):
        self._queue = queue.PriorityQueue()
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()

    def add_task(self, task_type: str, description: str, payload: dict,
                 priority: Priority = Priority.NORMAL, timeout: int = 60,
                 max_attempts: int = 3) -> Task:
        task = Task(
            task_id=str(uuid.uuid4()),
            task_type=task_type,
            description=description,
            payload=payload,
            priority=priority,
            created_at=datetime.now(),
            timeout=timeout,
            max_attempts=max_attempts,
        )
        with self._lock:
            self._tasks[task.task_id] = task
        self._queue.put((priority.value, task))
        logger.info(f"Task {task.task_id} ({task_type}) queued with priority {priority.name}")
        return task

    def get_next_task(self, specialization=None) -> Optional[Task]:
        temp = []
        result = None
        try:
            while True:
                try:
                    _, task = self._queue.get_nowait()
                except queue.Empty:
                    break
                with self._lock:
                    current = self._tasks.get(task.task_id)
                if current and current.status == "pending":
                    if specialization is None or task.task_type == specialization or specialization == "general":
                        result = task
                        break
                    else:
                        temp.append((task.priority.value, task))
                # Skip stale entries
        finally:
            for item in temp:
                self._queue.put(item)
        return result

    def complete_task(self, task_id: str, result: Any):
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = "completed"
                task.result = result
                logger.info(f"Task {task_id} completed")

    def fail_task(self, task_id: str, error: str):
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = "failed"
                task.error = error
                logger.warning(f"Task {task_id} failed: {error}")

    def retry_task(self, task_id: str):
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.attempts < task.max_attempts:
                task.status = "pending"
                task.attempts += 1
                task.assigned_to = None
                task.error = None
        if task:
            self._queue.put((task.priority.value, task))
            logger.info(f"Task {task_id} requeued (attempt {task.attempts})")

    def get_task_status(self, task_id: str) -> dict:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return {}
            return {
                "task_id": task.task_id,
                "status": task.status,
                "assigned_to": task.assigned_to,
                "attempts": task.attempts,
                "error": task.error,
            }

    def get_all_tasks(self) -> list:
        with self._lock:
            return list(self._tasks.values())

    def get_pending_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._tasks.values() if t.status == "pending")

    def get_completed_tasks(self) -> list:
        with self._lock:
            return [t for t in self._tasks.values() if t.status == "completed"]

    def get_failed_tasks(self) -> list:
        with self._lock:
            return [t for t in self._tasks.values() if t.status == "failed"]

    def clear_completed(self):
        with self._lock:
            self._tasks = {k: v for k, v in self._tasks.items() if v.status != "completed"}
        logger.debug("Cleared completed tasks")
