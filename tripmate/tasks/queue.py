"""
Async Task Queue & Background Worker Architecture

Provides an asynchronous task queue managing long-running agent workflows,
watchlist batch evaluations, and background jobs with status tracking and cancellation.
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger("tripmate.tasks")

# Handler function type
TaskHandler = Callable[[Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]]


class AsyncTaskQueue:
    """In-memory async background task queue with Redis-ready interface."""

    def __init__(self, max_concurrent_workers: int = 4):
        self._handlers: Dict[str, TaskHandler] = {}
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._running_asyncio_tasks: Dict[str, asyncio.Task] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_loop_task: Optional[asyncio.Task] = None
        self._is_running: bool = False
        self._max_concurrent = max_concurrent_workers
        self._semaphore: Optional[asyncio.Semaphore] = None

    def register_handler(self, task_name: str, handler: TaskHandler) -> None:
        """Registers an asynchronous callable handler for a specific task name."""
        self._handlers[task_name] = handler
        logger.info(f"Registered task handler: '{task_name}'")

    async def start(self) -> None:
        """Starts the background queue consumer worker loop."""
        if self._is_running:
            return
        self._is_running = True
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._worker_loop_task = asyncio.create_task(self._process_queue_loop())
        logger.info("Background task queue worker started.")

    async def stop(self) -> None:
        """Gracefully stops worker loop and cancels active running tasks."""
        self._is_running = False
        if self._worker_loop_task:
            self._worker_loop_task.cancel()
            try:
                await self._worker_loop_task
            except asyncio.CancelledError:
                pass
        
        # Cancel any active running task futures
        for tid, task_obj in list(self._running_asyncio_tasks.items()):
            if not task_obj.done():
                task_obj.cancel()
        self._running_asyncio_tasks.clear()
        logger.info("Background task queue worker stopped.")

    async def submit_task(
        self,
        task_name: str,
        payload: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Enqueues a new background task for execution."""
        if task_name not in self._handlers:
            raise ValueError(f"Unknown task type '{task_name}'. Available handlers: {list(self._handlers.keys())}")

        task_id = f"task_{uuid.uuid4().hex[:12]}"
        record = {
            "id": task_id,
            "name": task_name,
            "user_id": user_id,
            "status": "PENDING",
            "payload": payload,
            "progress_percent": 0,
            "result": None,
            "error": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "finished_at": None,
        }
        self._tasks[task_id] = record
        await self._queue.put(task_id)
        logger.info(f"Enqueued background task {task_id} ('{task_name}')")
        return record

    def get_task(self, task_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves a task record by ID, optionally verifying ownership."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        if user_id and task.get("user_id") and task["user_id"] != user_id:
            return None
        return task

    def list_tasks(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Lists tasks filtered by user or status."""
        results = []
        for t in reversed(list(self._tasks.values())):
            if user_id and t.get("user_id") and t["user_id"] != user_id:
                continue
            if status and t["status"] != status.upper():
                continue
            results.append(t)
            if len(results) >= limit:
                break
        return results

    async def cancel_task(self, task_id: str, user_id: Optional[str] = None) -> bool:
        """Cancels a pending or running task."""
        task = self.get_task(task_id, user_id=user_id)
        if not task:
            return False
        if task["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            return False

        task["status"] = "CANCELLED"
        task["finished_at"] = datetime.now(timezone.utc).isoformat()
        
        # If currently running in asyncio task, cancel it
        if task_id in self._running_asyncio_tasks:
            self._running_asyncio_tasks[task_id].cancel()
            del self._running_asyncio_tasks[task_id]
            
        logger.info(f"Task {task_id} cancelled.")
        return True

    def update_task_progress(self, task_id: str, progress_percent: int) -> None:
        """Updates numeric completion progress percentage (0 - 100)."""
        if task_id in self._tasks:
            self._tasks[task_id]["progress_percent"] = max(0, min(100, progress_percent))

    async def _process_queue_loop(self) -> None:
        """Internal worker loop consuming from the queue."""
        while self._is_running:
            try:
                task_id = await self._queue.get()
                if not self._is_running:
                    break
                
                # Spawn a concurrent worker task
                worker_task = asyncio.create_task(self._execute_single_task(task_id))
                self._running_asyncio_tasks[task_id] = worker_task
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Task queue processing error: {exc}")
                await asyncio.sleep(0.5)

    async def _execute_single_task(self, task_id: str) -> None:
        """Executes a single task with error handling and lifecycle updates."""
        task_record = self._tasks.get(task_id)
        if not task_record or task_record["status"] == "CANCELLED":
            return

        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)

        async with self._semaphore:
            task_record["status"] = "RUNNING"
            task_record["started_at"] = datetime.now(timezone.utc).isoformat()
            task_record["progress_percent"] = 10
            handler = self._handlers.get(task_record["name"])

            try:
                if not handler:
                    raise RuntimeError(f"No handler registered for task '{task_record['name']}'")
                
                result = await handler(task_record["payload"])
                task_record["result"] = result
                task_record["status"] = "COMPLETED"
                task_record["progress_percent"] = 100
                logger.info(f"Task {task_id} completed successfully.")
            except asyncio.CancelledError:
                task_record["status"] = "CANCELLED"
                logger.info(f"Task {task_id} execution was cancelled.")
            except Exception as exc:
                task_record["status"] = "FAILED"
                task_record["error"] = str(exc)
                logger.error(f"Task {task_id} execution failed: {exc}", exc_info=True)
            finally:
                task_record["finished_at"] = datetime.now(timezone.utc).isoformat()
                self._running_asyncio_tasks.pop(task_id, None)


    def get_stats(self) -> Dict[str, Any]:
        """Returns diagnostic telemetry stats for the task queue."""
        total_tasks = len(self._tasks)
        pending = sum(1 for t in self._tasks.values() if t.get("status") == "PENDING")
        running = sum(1 for t in self._tasks.values() if t.get("status") == "RUNNING")
        completed = sum(1 for t in self._tasks.values() if t.get("status") == "COMPLETED")
        failed = sum(1 for t in self._tasks.values() if t.get("status") == "FAILED")
        cancelled = sum(1 for t in self._tasks.values() if t.get("status") == "CANCELLED")

        return {
            "is_running": self._is_running,
            "max_concurrent_workers": self._max_concurrent,
            "active_workers": len(self._running_asyncio_tasks),
            "total_tasks": total_tasks,
            "pending_tasks": pending,
            "running_tasks": running,
            "completed_tasks": completed,
            "failed_tasks": failed,
            "cancelled_tasks": cancelled,
            "registered_handlers": list(self._handlers.keys()),
        }


# Global task queue singleton
task_queue = AsyncTaskQueue(max_concurrent_workers=4)
