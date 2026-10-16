"""
Singleton Pattern Implementation

Provides a thread-safe, double-checked locking Singleton metaclass for controlling
the lifecycle of expensive, shared resources (e.g. Connection Pools, Model Routers,
Task Queues, and Cache Clients).

Important Architecture Note:
In Python, singletons created with this metaclass are process-local. When running
under multi-process concurrency (e.g. Uvicorn with multiple workers or Gunicorn),
each process maintains its own isolated singleton instance. For cross-process shared
state, distributed stores such as Redis or PostgreSQL are used.
"""

import threading
from typing import Any, Dict, Type, TypeVar

T = TypeVar("T")


class SingletonMeta(type):
    """
    Thread-safe Singleton metaclass using double-checked locking.
    Guarantees that exactly one instance of a class is created per process,
    even under concurrent execution across multiple threads.
    """

    _instances: Dict[Type[Any], Any] = {}
    _locks: Dict[Type[Any], threading.Lock] = {}
    _global_lock = threading.Lock()

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        # First check (lock-free) for high performance after initialization
        if cls not in cls._instances:
            with cls._get_lock_for_class(cls):
                # Second check (guarded by lock) to prevent race conditions
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]

    @classmethod
    def _get_lock_for_class(cls, target_cls: Type[Any]) -> threading.Lock:
        """Retrieves or creates a class-specific threading lock."""
        with cls._global_lock:
            if target_cls not in cls._locks:
                cls._locks[target_cls] = threading.Lock()
            return cls._locks[target_cls]

    @classmethod
    def reset_instance(cls, target_cls: Type[Any]) -> None:
        """
        Resets the singleton instance for a given class.
        Primarily used in unit tests to guarantee clean isolated state.
        """
        with cls._get_lock_for_class(target_cls):
            if target_cls in cls._instances:
                del cls._instances[target_cls]

    @classmethod
    def clear_all(cls) -> None:
        """Clears all registered singleton instances (useful in test teardown)."""
        with cls._global_lock:
            cls._instances.clear()
