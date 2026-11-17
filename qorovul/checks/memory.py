"""RAM usage check."""

from typing import Any, Dict, List

from .base import Check, CheckResult


class MemoryCheck(Check):
    """Report RAM usage at/above the threshold.

    Usage is psutil's ``virtual_memory().percent`` which on Linux is
    ``(total - available) / total`` - page cache does not count as used.

    The "sustained for N cycles" requirement is deliberately not tracked
    here: it is enforced by the alert engine (``sustained_cycles`` becomes
    this check's ``confirm_cycles``), whose counter lives in state.json.  A
    counter kept in this process would reset on every restart and make an
    ongoing incident look recovered for a few cycles.
    """

    name = "memory"
    KEY = "memory:ram"

    def __init__(self, config: Dict[str, Any], psutil_module: Any = None) -> None:
        super().__init__(config)
        if psutil_module is None:
            import psutil as psutil_module  # noqa: N813
        self.psutil = psutil_module

    def run(self) -> List[CheckResult]:
        vm = self.psutil.virtual_memory()
        pct = float(vm.percent)
        warn = self.config["threshold"]
        crit = self.config["critical_threshold"]
        msg = "RAM usage %.1f%% (%.0f MB available of %.0f MB)" % (
            pct, vm.available / (1024 * 1024), vm.total / (1024 * 1024))
        if crit is not None and pct >= crit:
            return [CheckResult(self.KEY, False, "critical", msg)]
        if pct >= warn:
            return [CheckResult(self.KEY, False, "warning", msg)]
        return [CheckResult(self.KEY, True, "info", msg)]
