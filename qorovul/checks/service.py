"""systemd unit state check."""

import subprocess
from typing import Any, Callable, Dict, List, Sequence

from .base import Check, CheckResult

OK_STATES = ("active", "reloading")


def _systemctl_is_active(units: Sequence[str]) -> List[str]:
    """Return one state string per unit using a single systemctl call."""
    proc = subprocess.run(
        ["systemctl", "is-active", "--"] + list(units),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True, timeout=15, check=False,
    )
    # is-active exits non-zero when any unit is inactive; stdout is still valid.
    states = proc.stdout.splitlines()
    if len(states) != len(units):
        err = " ".join(proc.stderr.split()) or "exit code %d" % proc.returncode
        raise RuntimeError("systemctl is-active failed: %s" % err)
    return states


class ServiceCheck(Check):
    """Alert when a configured systemd unit is not active."""

    name = "service"

    def __init__(self, config: Dict[str, Any],
                 is_active: Callable[[Sequence[str]], List[str]] = _systemctl_is_active) -> None:
        super().__init__(config)
        self.is_active = is_active

    @staticmethod
    def _unit_name(unit: str) -> str:
        return unit if "." in unit else unit + ".service"

    def run(self) -> List[CheckResult]:
        units = [self._unit_name(u) for u in self.config["units"]]
        if not units:
            return []
        states = self.is_active(units)
        if len(states) != len(units):
            raise RuntimeError("systemctl returned %d states for %d units" % (len(states), len(units)))
        severity = self.config["severity"]
        results = []
        for unit, state in zip(units, states):
            state = state.strip() or "unknown"
            key = "service:" + unit
            if state in OK_STATES:
                results.append(CheckResult(key, True, "info", "%s is %s" % (unit, state)))
            else:
                results.append(CheckResult(key, False, severity, "%s is %s" % (unit, state)))
        return results
