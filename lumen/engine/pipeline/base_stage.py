"""
Base stage — shared implementation for all pipeline stages.

Concrete stages inherit from :class:`BaseStage` to get consistent
logging, error handling, and precondition checking.  Stages override
:meth:`execute` and return a :class:`~core.result.StageResult`.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import List

from ..core.context import GenerationContext
from ..core.contracts import PipelineStage
from ..core.result import StageResult
from ..logging import get_logger


class BaseStage(PipelineStage):
    """Convenience base class for pipeline stages.

    Subclasses set ``requires`` and ``provides`` and implement
    :meth:`execute`.  The :meth:`run` method handles logging and wraps
    unexpected exceptions into a failed :class:`StageResult`.
    """

    requires: List[str] = []
    provides: List[str] = []

    def __init__(self) -> None:
        super().__init__(
            name=getattr(self, "stage_name", self.__class__.__name__),
            version="1.0.0",
            description=self.__doc__ or "",
        )
        self._log = get_logger(f"pipeline.{self.name}")

    @abstractmethod
    def execute(self, context: GenerationContext) -> StageResult:
        """Perform the stage work and return a :class:`StageResult`."""
        raise NotImplementedError

    def run(self, context: GenerationContext) -> StageResult:
        self._log.info("Stage starting", {"stage": self.name})
        if not self.check_preconditions(context):
            missing = [k for k in self.requires if not context.has(k)]
            self._log.error("Stage preconditions not met",
                            {"stage": self.name, "missing": missing})
            return StageResult.failed(
                self.name,
                [f"Missing required artefacts: {missing}"],
            )
        try:
            result = self.execute(context)
        except Exception as exc:  # noqa: BLE001
            self._log.exception("Stage crashed", {"stage": self.name})
            return StageResult.failed(
                self.name,
                [f"Stage '{self.name}' raised an exception: {exc}"],
            )
        if result.success:
            self._log.info("Stage completed",
                           {"stage": self.name, "outputs": list(result.outputs.keys())})
        else:
            self._log.error("Stage failed",
                            {"stage": self.name, "errors": result.errors})
        return result


__all__ = ["BaseStage"]
