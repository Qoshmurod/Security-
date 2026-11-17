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
        """Auto-discovered local filesystems (used when none are configured).

        psutil lists only disk-backed filesystems here, so network mounts
        (NFS, CIFS) and pseudo filesystems are left out: a stalled NFS server
        would otherwise block ``statvfs`` and with it the whole watchdog.
        """
        exclude_fs = set(self.config["exclude_fstypes"])
        exclude_mp = self.config["exclude_mountpoints"]
        parts = sorted(self.psutil.disk_partitions(all=False),
                       key=lambda p: (len(p.mountpoint), p.mountpoint))
        seen_devices = set()
        result = []
        for part in parts:
            mp = part.mountpoint
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
        # Paths the user listed are checked as given, whatever their type.
        explicit = list(self.config["mountpoints"])
        results = []
        for mp in explicit or self._mountpoints():
            try:
                usage = self.psutil.disk_usage(mp)
            except OSError as exc:
                if explicit:
                    # The user asked for this path: not being able to look is
                    # a monitoring gap they need to hear about.
                    results.append(CheckResult(
                        "disk:" + mp, False, "warning",
                        "cannot read disk usage of %s: %s" % (mp, exc.strerror or exc)))
                continue  # auto-discovered: unmounted between listing and stat
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
