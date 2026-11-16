"""TLS certificate expiry check."""

import socket
import ssl
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Tuple

from .base import Check, CheckResult


class CertVerifyError(Exception):
    """The server presented a certificate that does not verify."""


def fetch_cert(host: str, port: int, timeout: float) -> Dict[str, Any]:
    """Connect with full verification and return ``getpeercert()``."""
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                return tls.getpeercert()
    except ssl.SSLCertVerificationError as exc:
        raise CertVerifyError(exc.verify_message or str(exc))


def parse_target(entry: str) -> Tuple[str, int]:
    host, port = entry, 443
    if entry.startswith("["):  # [v6]:port
        host, _, rest = entry[1:].partition("]")
        if rest.startswith(":"):
            port = int(rest[1:])
    elif entry.count(":") == 1:
        host, p = entry.split(":")
        port = int(p)
    return host, port


class SSLCheck(Check):
    """Alert when a domain's certificate expires within ``warn_days``."""

    name = "ssl"

    def __init__(self, config: Dict[str, Any],
                 fetch: Callable[[str, int, float], Dict[str, Any]] = fetch_cert,
                 clock: Callable[[], float] = time.time) -> None:
        super().__init__(config)
        self.fetch = fetch
        self.clock = clock

    def run(self) -> List[CheckResult]:
        results = []
        for entry in self.config["domains"]:
            host, port = parse_target(entry)
            key = "ssl:" + (host if port == 443 else "%s:%d" % (host, port))
            results.append(self._check_one(key, host, port))
        return results

    def _check_one(self, key: str, host: str, port: int) -> CheckResult:
        try:
            cert = self.fetch(host, port, self.config["timeout"])
        except CertVerifyError as exc:
            return CheckResult(key, False, "critical",
                               "%s certificate is not valid: %s" % (host, exc))
        except (OSError, ssl.SSLError) as exc:
            return CheckResult(key, False, self.config["connect_error_severity"],
                               "cannot check certificate of %s:%d: %s" % (host, port, exc))
        expires = ssl.cert_time_to_seconds(cert["notAfter"])
        days = (expires - self.clock()) / 86400.0
        date = datetime.fromtimestamp(expires, timezone.utc).strftime("%Y-%m-%d")
        whole = int(days) if days >= 0 else -int(-days)  # truncate toward zero
        if days < 0:
            return CheckResult(key, False, "critical",
                               "%s certificate EXPIRED on %s" % (host, date))
        msg = "%s certificate expires in %d day%s (%s)" % (
            host, whole, "" if whole == 1 else "s", date)
        if days <= self.config["critical_days"]:
            return CheckResult(key, False, "critical", msg)
        if days <= self.config["warn_days"]:
            return CheckResult(key, False, "warning", msg)
        return CheckResult(key, True, "info", msg)
