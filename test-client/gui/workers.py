from __future__ import annotations

import asyncio
import traceback
from collections.abc import Callable, Coroutine
from typing import Any

from PyQt5.QtCore import QThread, pyqtSignal


class AsyncWorker(QThread):
    """Runs an async coroutine factory in a background thread."""

    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(
        self,
        coro_factory: Callable[[], Coroutine[Any, Any, Any]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.coro_factory = coro_factory

    def run(self) -> None:
        try:
            result = asyncio.run(self.coro_factory())
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(f"{exc}\n{traceback.format_exc()}")


class ProgressAsyncWorker(AsyncWorker):
    """Async worker that injects a progress callback into coroutine kwargs."""

    def __init__(
        self,
        coro_factory: Callable[..., Coroutine[Any, Any, Any]],
        *,
        kwargs: dict[str, Any] | None = None,
        parent=None,
    ) -> None:
        self._coro_factory = coro_factory
        self._kwargs = kwargs or {}
        super().__init__(self._make_coro, parent)

    def _make_coro(self) -> Coroutine[Any, Any, Any]:
        async def runner() -> Any:
            return await self._coro_factory(on_progress=self._emit_progress, **self._kwargs)

        return runner()

    def _emit_progress(self, message: str) -> None:
        self.progress.emit(message)
