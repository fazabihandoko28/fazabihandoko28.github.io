from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def execute_with_retry(
    operation: Callable[[], T],
    *,
    attempts: int = 3,
    initial_delay_seconds: float = 0.25,
    retry_exceptions: tuple[type[BaseException], ...] = (OSError, TimeoutError),
    on_attempt: Callable[[int], None] | None = None,
) -> T:
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    delay = initial_delay_seconds
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        if on_attempt:
            on_attempt(attempt)
        try:
            return operation()
        except retry_exceptions as exc:
            last_error = exc
            if attempt == attempts:
                raise
            time.sleep(delay)
            delay *= 2
    assert last_error is not None
    raise last_error
