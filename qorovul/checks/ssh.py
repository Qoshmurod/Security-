"""SSH brute-force detection from auth.log / secure / journald.

Counting model
--------------
sshd logs several lines per attempt, e.g. for a password guess at an unknown
user::

    Invalid user admin from 203.0.113.9 port 50122
    Failed password for invalid user admin from 203.0.113.9 port 50122 ssh2

and for a key-only server just ``Invalid user ...`` / ``Connection closed by
authenticating user root ... [preauth]``.  Counting raw lines would double
count, so lines are grouped by connection (source IP + source port): a
connection contributes the number of ``Failed ...`` lines it logged, or 1 if
it only logged a failure marker.  The per-IP total within the sliding window
is compared against ``failures``.
"""

import ipaddress
import os
import re
import shutil
import subprocess
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .base import Check, CheckResult

_IP = r"(?P<ip>[0-9A-Fa-f:.]+)"
RE_FAILED = re.compile(
    r"Failed \S+ for (?:invalid user )?(?P<user>.*?) from " + _IP + r" port (?P<port>\d+)")
RE_MARKER = re.compile(
    r"(?:Invalid user (?P<u1>.*?) from"
    r"|Connection closed by (?:authenticating|invalid) user (?P<u2>.*?)"
    r"|Disconnected from (?:authenticating|invalid) user (?P<u3>.*?)"
    r") " + _IP + r" port (?P<port>\d+)")
RE_SYSLOG_TS = re.compile(r"^(?P<mon>[A-Z][a-z]{2}) +(?P<day>\d{1,2}) (?P<h>\d\d):(?P<m>\d\d):(?P<s>\d\d) ")
RE_ISO_TS = re.compile(
    r"^(?P<ts>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?P<frac>\.\d+)?(?P<tz>Z|[+-]\d\d:?\d\d)? ")
RE_UNIX_TS = re.compile(r"^(?P<ts>\d{9,11}(?:\.\d+)?) ")
MONTHS = {m: i for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}

# Read at most this much of an existing log on first start, and per cycle.
INITIAL_TAIL_BYTES = 2 * 1024 * 1024
MAX_READ_BYTES = 16 * 1024 * 1024
MAX_CONNECTIONS = 200000


def parse_timestamp(line: str, now: float) -> Optional[float]:
    """Parse the leading timestamp of a syslog/journal line into epoch seconds."""
    m = RE_UNIX_TS.match(line)
    if m:
        return float(m.group("ts"))
    m = RE_ISO_TS.match(line)
    if m:
        tz = m.group("tz")
        try:
            dt = datetime.strptime(m.group("ts"), "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
        frac = float(m.group("frac") or 0)
        if tz:
            if tz == "Z":
                offset = timedelta(0)
            else:
                tz = tz.replace(":", "")
                sign = 1 if tz[0] == "+" else -1
                offset = sign * timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5]))
            return dt.replace(tzinfo=timezone(offset)).timestamp() + frac
        return time.mktime(dt.timetuple()) + frac
    m = RE_SYSLOG_TS.match(line)
    if m:
        # Classic syslog has no year: assume the current one, unless that
        # would put the line in the future (log from last December read in January).
        year = datetime.fromtimestamp(now).year
        try:
            dt = datetime(year, MONTHS[m.group("mon")], int(m.group("day")),
                          int(m.group("h")), int(m.group("m")), int(m.group("s")))
        except (KeyError, ValueError):
            return None
        ts = time.mktime(dt.timetuple())
        if ts > now + 86400:
            ts = time.mktime(dt.replace(year=year - 1).timetuple())
        return ts
    return None


def parse_line(line: str) -> Optional[Tuple[str, int, str, bool]]:
    """Return (ip, port, user, is_failed_line) for an sshd failure line, else None."""
    if "sshd" not in line:
        return None
    m = RE_FAILED.search(line)
    if m:
        failed = True
        user = m.group("user")
    else:
        m = RE_MARKER.search(line)
        if not m:
            return None
        failed = False
        user = m.group("u1") or m.group("u2") or m.group("u3") or ""
    ip = m.group("ip")
    try:
        ip = str(ipaddress.ip_address(ip))
    except ValueError:
        return None
    return ip, int(m.group("port")), user, failed


class FailureWindow:
    """Sliding window of failed SSH connections, grouped by (ip, port)."""

    def __init__(self) -> None:
        # (ip, port) -> [first_ts, failed_lines, users(set)]
        self.conns = OrderedDict()  # type: OrderedDict

    def add_line(self, line: str, now: float) -> None:
        parsed = parse_line(line)
        if parsed is None:
            return
        ts = parse_timestamp(line, now)
        if ts is None:
            ts = now
        ip, port, user, failed = parsed
        conn = self.conns.get((ip, port))
        if conn is None:
            conn = [ts, 0, set()]
            self.conns[(ip, port)] = conn
            if len(self.conns) > MAX_CONNECTIONS:
                self.conns.popitem(last=False)
        if failed:
            conn[1] += 1
        if user and len(conn[2]) < 5:
            conn[2].add(user)

    def prune(self, cutoff: float) -> None:
        for k in [k for k, c in self.conns.items() if c[0] < cutoff]:
            del self.conns[k]

    def counts(self) -> Dict[str, Tuple[int, List[str]]]:
        out = {}  # type: Dict[str, Tuple[int, List[str]]]
        for (ip, _port), (_ts, failed, users) in self.conns.items():
            n, u = out.get(ip, (0, []))
            for name in users:
                if name not in u and len(u) < 5:
                    u.append(name)
            out[ip] = (n + max(failed, 1), u)
        return out

    def clear(self) -> None:
        self.conns.clear()


class LogTail:
    """Incrementally read new lines from a log file, surviving rotation."""

    def __init__(self, path: str, opener: Callable[..., Any] = open,
                 stat: Callable[[str], Any] = os.stat) -> None:
        self.path = path
        self.opener = opener
        self.stat = stat
        self.inode = None  # type: Optional[Tuple[int, int]]
        self.offset = 0
        self.partial = b""

    def read_new(self) -> List[str]:
        st = self.stat(self.path)
        ident = (st.st_dev, st.st_ino)
        first = self.inode is None
        if ident != self.inode or st.st_size < self.offset:
            # New file (first run, or rotated/truncated).
            self.offset = max(0, st.st_size - INITIAL_TAIL_BYTES) if first else 0
            self.partial = b""
            self.inode = ident
        if st.st_size == self.offset:
            return []
        with self.opener(self.path, "rb") as fh:
            fh.seek(self.offset)
            data = fh.read(MAX_READ_BYTES)
        skip_first = first and self.offset > 0
        self.offset += len(data)
        data = self.partial + data
        lines = data.split(b"\n")
        self.partial = lines.pop()  # incomplete trailing line (or b"")
        if skip_first and lines:
            lines = lines[1:]  # we started mid-line
        return [ln.decode("utf-8", "replace") for ln in lines]


def _journal_lines(since: float) -> List[str]:
    proc = subprocess.run(
        ["journalctl", "--no-pager", "--quiet", "--output=short-unix",
         "--since=@%d" % int(since), "--unit=ssh.service", "--unit=sshd.service"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True, timeout=30, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("journalctl failed: %s" % (proc.stderr.strip() or proc.returncode))
    return proc.stdout.splitlines()


class SSHCheck(Check):
    """Alert when one IP reaches ``failures`` failed logins within ``window``."""

    name = "ssh"

    def __init__(self, config: Dict[str, Any],
                 clock: Callable[[], float] = time.time,
                 opener: Callable[..., Any] = open,
                 stat: Callable[[str], Any] = os.stat,
                 readable: Callable[[str], bool] = lambda p: os.access(p, os.R_OK),
                 journal: Callable[[float], List[str]] = _journal_lines,
                 has_journalctl: Optional[Callable[[], bool]] = None) -> None:
        super().__init__(config)
        self.clock = clock
        self.opener = opener
        self.stat = stat
        self.readable = readable
        self.journal = journal
        self.has_journalctl = has_journalctl or (lambda: shutil.which("journalctl") is not None)
        self.window = FailureWindow()
        self.tail = None  # type: Optional[LogTail]
        self.ignore = [ipaddress.ip_network(n, strict=False) for n in config["ignore_ips"]]

    def _source(self) -> Tuple[str, Optional[str]]:
        """Return ("file", path) or ("journal", None)."""
        src = self.config["source"]
        if src in ("auto", "file"):
            for path in self.config["log_paths"]:
                if self.readable(path):
                    return "file", path
            if src == "file":
                raise RuntimeError("none of the SSH log files are readable: %s"
                                   % ", ".join(self.config["log_paths"]))
        if src in ("auto", "journal") and self.has_journalctl():
            return "journal", None
        raise RuntimeError("no readable SSH log source (tried %s and journald)"
                           % ", ".join(self.config["log_paths"]))

    def _feed(self, lines: Iterable[str], now: float) -> None:
        for line in lines:
            self.window.add_line(line, now)

    def run(self) -> List[CheckResult]:
        now = self.clock()
        cutoff = now - self.config["window"]
        kind, path = self._source()
        if kind == "file":
            if self.tail is None or self.tail.path != path:
                self.tail = LogTail(path, self.opener, self.stat)
                self.window.clear()
            self._feed(self.tail.read_new(), now)
        else:
            self.tail = None
            self.window.clear()
            self._feed(self.journal(cutoff), now)
        self.window.prune(cutoff)

        limit = self.config["failures"]
        minutes = int(self.config["window"] // 60)
        span = "%dm" % minutes if minutes else "%ds" % self.config["window"]
        results = []
        for ip, (count, users) in sorted(self.window.counts().items()):
            if count < limit or self._ignored(ip):
                continue
            msg = "%d failed SSH logins from %s in the last %s" % (count, ip, span)
            if users:
                msg += " (users: %s)" % ", ".join(sorted(users))
            results.append(CheckResult("ssh:" + ip, False, self.config["severity"], msg))
        return results

    def _ignored(self, ip: str) -> bool:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in self.ignore)

    def cleared_message(self, key: str) -> str:
        return "failed logins from %s dropped below %d per %s" % (
            key.split(":", 1)[1], self.config["failures"],
            "%dm" % (self.config["window"] // 60))
