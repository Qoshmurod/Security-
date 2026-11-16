"""Filesystem usage check."""

from typing import Any, Dict, List

from .base import Check, CheckResult


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return "%.1f %s" % (n, unit) if unit != "B" else "%d B" % n
        n /= 1024.0
    return "%.1f PB" % n  # pragma: no cover


class DiskCheck(Check):
    """Alert when a mounted filesystem's usage reaches the threshold."""

    name = "disk"

    def __init__(self, config: Dict[str, Any], psutil_module: Any = None) -> None:
        super().__init__(config)
        if psutil_module is None:
            import psutil as psutil_module  # noqa: N813
        self.psutil = psutil_module

    def _mountpoints(self) -> List[str]:
        exclude_fs = set(self.config["exclude_fstypes"])
        exclude_mp = self.config["exclude_mountpoints"]
        only = self.config["mountpoints"]
        parts = sorted(self.psutil.disk_partitions(all=False),
                       key=lambda p: (len(p.mountpoint), p.mountpoint))
        seen_devices = set()
        result = []
        for part in parts:
            mp = part.mountpoint
            if only:
                if mp not in only:
                    continue
            else:
                if part.fstype in exclude_fs:
                    continue
                if any(mp == p or mp.startswith(p.rstrip("/") + "/") for p in exclude_mp):
                    continue
                # Bind mounts / btrfs subvolumes of one device report the same
                # usage: keep only the shortest mountpoint per block device.
                if part.device.startswith("/dev/"):
                    if part.device in seen_devices:
                        continue
                    seen_devices.add(part.device)
            result.append(mp)
        return result

    def run(self) -> List[CheckResult]:
        warn = self.config["threshold"]
        crit = self.config["critical_threshold"]
        results = []
        for mp in self._mountpoints():
            try:
                usage = self.psutil.disk_usage(mp)
            except OSError:
                continue  # unmounted or unreadable between listing and stat
            pct = float(usage.percent)
            msg = "%s is %.1f%% full (%s free of %s)" % (
                mp, pct, _human(usage.free), _human(usage.total))
            if crit is not None and pct >= crit:
                results.append(CheckResult("disk:" + mp, False, "critical", msg))
            elif pct >= warn:
                results.append(CheckResult("disk:" + mp, False, "warning", msg))
            else:
                results.append(CheckResult("disk:" + mp, True, "info", msg))
        return results

    def cleared_message(self, key: str) -> str:
        return "%s is no longer mounted" % key.split(":", 1)[1]
