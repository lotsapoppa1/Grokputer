import logging
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from .task_queue import Task, TaskQueue

logger = logging.getLogger(__name__)

SPECIALIZATION_TASK_MAP = {
    "file_ops": ["file"],
    "web": ["web"],
    "email": ["email"],
    "code": ["code"],
    "monitor": ["monitor"],
    "data": ["data"],
    "general": ["general", "file", "web", "email", "code", "monitor", "data"],
}


class AgentStatus(Enum):
    IDLE = "idle"
    BUSY = "busy"
    WAITING = "waiting"
    STOPPED = "stopped"
    ERROR = "error"


class AgentSpecialization(Enum):
    GENERAL = "general"
    FILE_OPS = "file_ops"
    WEB = "web"
    EMAIL = "email"
    CODE = "code"
    MONITOR = "monitor"
    DATA = "data"


class Agent:
    def __init__(self, agent_id: str, specialization: AgentSpecialization,
                 task_queue: TaskQueue, brain=None, config=None):
        self.agent_id = agent_id
        self.specialization = specialization
        self.task_queue = task_queue
        self.brain = brain
        self.config = config or {}

        self.status = AgentStatus.IDLE
        self.current_task: Optional[Task] = None
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.started_at: Optional[datetime] = None
        self.last_active: Optional[datetime] = None

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._inbox: list = []

    def start(self):
        self.started_at = datetime.now()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True,
                                        name=f"agent-{self.agent_id}")
        self._thread.start()
        logger.info(f"Agent {self.agent_id} ({self.specialization.value}) started")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        with self._lock:
            self.status = AgentStatus.STOPPED
        logger.info(f"Agent {self.agent_id} stopped")

    def _run_loop(self):
        poll_interval = float(self.config.get("poll_interval", 0.5))
        accepted_types = SPECIALIZATION_TASK_MAP.get(self.specialization.value, ["general"])

        while not self._stop_event.is_set():
            task = None
            for t_type in accepted_types:
                task = self.task_queue.get_next_task(specialization=t_type)
                if task:
                    break

            if task:
                with self._lock:
                    self.status = AgentStatus.BUSY
                    self.current_task = task
                    task.status = "running"
                    task.assigned_to = self.agent_id
                    self.last_active = datetime.now()
                try:
                    result = self._execute_with_timeout(task)
                    self.task_queue.complete_task(task.task_id, result)
                    with self._lock:
                        self.tasks_completed += 1
                except Exception as exc:
                    logger.error(f"Agent {self.agent_id} task {task.task_id} error: {exc}")
                    with self._lock:
                        self.tasks_failed += 1
                    if task.attempts < task.max_attempts:
                        self.task_queue.retry_task(task.task_id)
                    else:
                        self.task_queue.fail_task(task.task_id, str(exc))
                finally:
                    with self._lock:
                        self.current_task = None
                        self.status = AgentStatus.IDLE
            else:
                with self._lock:
                    self.status = AgentStatus.WAITING
                time.sleep(poll_interval)

    def _execute_with_timeout(self, task: Task) -> Any:
        result_holder = [None]
        exc_holder = [None]

        def run():
            try:
                result_holder[0] = self.execute_task(task)
            except Exception as e:
                exc_holder[0] = e

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout=task.timeout)
        if t.is_alive():
            raise TimeoutError(f"Task {task.task_id} timed out after {task.timeout}s")
        if exc_holder[0]:
            raise exc_holder[0]
        return result_holder[0]

    def execute_task(self, task: Task) -> Any:
        dispatch = {
            "file": self._execute_file_task,
            "web": self._execute_web_task,
            "email": self._execute_email_task,
            "code": self._execute_code_task,
            "monitor": self._execute_monitor_task,
        }
        handler = dispatch.get(task.task_type, self._execute_general_task)
        return handler(task)

    def _execute_file_task(self, task: Task) -> Any:
        action = task.payload.get("action", "read")
        path = task.payload.get("path", "")
        if action == "read":
            with open(path, "r") as f:
                return f.read()
        elif action == "write":
            content = task.payload.get("content", "")
            with open(path, "w") as f:
                f.write(content)
            return f"Written to {path}"
        elif action == "list":
            import os
            return os.listdir(path)
        return f"Unknown file action: {action}"

    def _execute_web_task(self, task: Task) -> Any:
        import requests
        url = task.payload.get("url", "")
        method = task.payload.get("method", "GET").upper()
        headers = task.payload.get("headers", {})
        data = task.payload.get("data")
        timeout = task.payload.get("request_timeout", 30)
        resp = requests.request(method, url, headers=headers, json=data, timeout=timeout)
        return {"status_code": resp.status_code, "text": resp.text[:4096]}

    def _execute_email_task(self, task: Task) -> Any:
        # Placeholder — integrate with SMTP/email config as needed
        logger.info(f"Email task: {task.payload}")
        return {"status": "queued", "payload": task.payload}

    def _execute_code_task(self, task: Task) -> Any:
        code = task.payload.get("code", "")
        exec_globals: dict = {}
        exec(code, exec_globals)  # noqa: S102
        return exec_globals.get("result")

    def _execute_monitor_task(self, task: Task) -> Any:
        import psutil
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory": psutil.virtual_memory()._asdict(),
        }

    def _execute_general_task(self, task: Task) -> Any:
        if self.brain:
            prompt = task.payload.get("prompt", task.description)
            return self.brain(prompt)
        return {"description": task.description, "payload": task.payload}

    def get_status(self) -> dict:
        with self._lock:
            return {
                "agent_id": self.agent_id,
                "specialization": self.specialization.value,
                "status": self.status.value,
                "current_task": self.current_task.task_id if self.current_task else None,
                "tasks_completed": self.tasks_completed,
                "tasks_failed": self.tasks_failed,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "last_active": self.last_active.isoformat() if self.last_active else None,
            }

    def send_message(self, message: Any):
        with self._lock:
            self._inbox.append(message)
        logger.debug(f"Agent {self.agent_id} received message: {message}")
