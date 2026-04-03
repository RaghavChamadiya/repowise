"""Progress reporting protocol for the repowise pipeline.

Decouples pipeline execution from UI concerns. The CLI implements this
with Rich progress bars; Modal uses structured logging; tests pass None.

Phase names (stable strings used across all implementations):
    traverse, parse, graph, git, co_change, dead_code, decisions, generation
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import structlog

logger = structlog.get_logger(__name__)


@runtime_checkable
class ProgressCallback(Protocol):
    """Protocol for pipeline progress reporting."""

    def on_phase_start(self, phase: str, total: int | None) -> None:
        """Called when a pipeline phase begins. *total* may be None for indeterminate phases."""
        ...

    def on_item_done(self, phase: str) -> None:
        """Called after one unit of work completes within a phase."""
        ...

    def on_message(self, level: str, text: str) -> None:
        """Emit a free-form message. *level* is 'info', 'warning', or 'error'."""
        ...


class LoggingProgressCallback:
    """Emits progress as structured log messages. Suitable for headless workers (Modal)."""

    def on_phase_start(self, phase: str, total: int | None) -> None:
        logger.info("phase_start", phase=phase, total=total)

    def on_item_done(self, phase: str) -> None:
        logger.debug("item_done", phase=phase)

    def on_message(self, level: str, text: str) -> None:
        getattr(logger, level, logger.info)(text)
