"""RAM usage check with a sustain requirement."""

from typing import Any, Dict, List

from .base import Check, CheckResult


class MemoryCheck(Check):
    """Alert when RAM usage stays at/above the threshold for N consecutive cycles.

    Usage is psutil's ``virtual_memory().percent`` which on Linux is
    ``(total - available) / total`` - page cache does not count as used.
    """

    name = "memory"
    KEY = "memory:ram"

    def __init__(self, config: Dict[str, Any], psutil_module: Any = None) -> None:
        super().__init__(config)
        if psutil_module is None:
            import psutil as psutil_module  # noqa: N813
        self.psutil = psutil_module
        self.high_cycles = 0

    def run(self) -> List[CheckResult]:
        vm = self.psutil.virtual_memory()
        pct = float(vm.percent)
        warn = self.config["threshold"]
        crit = self.config["critical_threshold"]
        need = self.config["sustained_cycles"]
        avail_mb = vm.available / (1024 * 1024)
        total_mb = vm.total / (1024 * 1024)

        if pct >= warn:
            self.high_cycles += 1
        else:
            self.high_cycles = 0

        if self.high_cycles >= need:
            severity = "critical" if crit is not None and pct >= crit else "warning"
            msg = "RAM usage %.1f%% for %d consecutive checks (%.0f MB available of %.0f MB)" % (
                pct, self.high_cycles, avail_mb, total_mb)
            return [CheckResult(self.KEY, False, severity, msg)]
        msg = "RAM usage %.1f%% (%.0f MB available of %.0f MB)" % (pct, avail_mb, total_mb)
        return [CheckResult(self.KEY, True, "info", msg)]
