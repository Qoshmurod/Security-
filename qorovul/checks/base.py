"""Check interface shared by every built-in check."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List

SEVERITIES = ("info", "warning", "critical")


def severity_rank(severity: str) -> int:
    """Return an orderable rank for a severity name (info < warning < critical)."""
    return SEVERITIES.index(severity)


@dataclass(frozen=True)
class CheckResult:
    """Outcome of evaluating one check instance.

    ``key`` is stable across cycles (e.g. ``"disk:/var"``) and is what alerts
    are deduplicated on.  ``ok`` is False while the alert condition holds.
    """

    key: str
    ok: bool
    severity: str
    message: str

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError("invalid severity %r" % (self.severity,))


class Check(ABC):
    """A single kind of check (disk, memory, ...).

    ``run()`` returns one result per instance it evaluated.  When a check
    completes normally, any previously failing key it did *not* report is
    treated as cleared (e.g. a port that stopped listening).
    """

    name = "base"

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config

    @abstractmethod
    def run(self) -> List[CheckResult]:
        raise NotImplementedError

    def cleared_message(self, key: str) -> str:
        """Message used when a failing key is no longer reported."""
        return "condition no longer present"
