"""Boundary conditions for every check, with faked system inputs."""

import io
import re
import os
import ssl as ssl_mod
from collections import namedtuple
from datetime import datetime, timezone

import pytest

from qorovul.checks import REGISTRY, build_checks
from qorovul.checks.disk import DiskCheck
from qorovul.checks.memory import MemoryCheck
from qorovul.checks.ports import Listener, PortsCheck, decode_addr, parse_proc_net
from qorovul.checks.service import ServiceCheck
from qorovul.checks.ssh import SSHCheck, parse_line, parse_timestamp
from qorovul.checks.ssl import CertVerifyError, SSLCheck, parse_target
from qorovul.config import validate

import socket


def section(name, **overrides):
    return validate({"checks": {name: overrides}}, env={})["checks"][name]


# =============================================================== disk

Part = namedtuple("Part", "device mountpoint fstype opts")
Usage = namedtuple("Usage", "total used free percent")


class FakePsutil:
    def __init__(self, parts=(), usage=None, vm=None):
        self.parts = list(parts)
        self.usage = usage or {}
        self.vm = vm

    def disk_partitions(self, all=False):
        return self.parts

    def disk_usage(self, mp):
        u = self.usage[mp]
        if isinstance(u, Exception):
            raise u
        return u

    def virtual_memory(self):
        return self.vm


def usage(pct, total=100 * 2 ** 30):
    used = total * pct / 100
    return Usage(total, used, total - used, pct)


def disk(parts, usages, **cfg):
    return DiskCheck(section("disk", **cfg), FakePsutil(parts, usages)).run()


@pytest.mark.parametrize("pct,ok,sev", [
    (0, True, "info"), (84.9, True, "info"), (85.0, False, "warning"),
    (94.9, False, "warning"), (95.0, False, "critical"), (100, False, "critical")])
def test_disk_thresholds(pct, ok, sev):
    [r] = disk([Part("/dev/sda1", "/", "ext4", "rw")], {"/": usage(pct)})
    assert (r.key, r.ok, r.severity) == ("disk:/", ok, sev)
    assert "%.1f%%" % pct in r.message


def test_disk_no_critical_threshold():
    [r] = disk([Part("/dev/sda1", "/", "ext4", "rw")], {"/": usage(100)},
               critical_threshold=None)
    assert r.severity == "warning"


def test_disk_custom_threshold():
    [r] = disk([Part("/dev/sda1", "/", "ext4", "rw")], {"/": usage(70)}, threshold=70)
    assert not r.ok


def test_disk_excludes_pseudo_filesystems_and_prefixes():
    parts = [Part("/dev/sda1", "/", "ext4", ""), Part("tmpfs", "/run", "tmpfs", ""),
             Part("/dev/loop0", "/snap/core/1", "squashfs", ""),
             Part("/dev/sdb1", "/var/lib/docker/x", "ext4", ""),
             Part("/dev/sdc1", "/snapshots", "ext4", "")]
    u = {p.mountpoint: usage(50) for p in parts}
    assert [r.key for r in disk(parts, u)] == ["disk:/", "disk:/snapshots"]


def test_disk_dedupes_bind_mounts_keeping_shortest():
    parts = [Part("/dev/sda1", "/srv/data", "ext4", ""), Part("/dev/sda1", "/", "ext4", ""),
             Part("/dev/sda2", "/home", "ext4", "")]
    u = {p.mountpoint: usage(50) for p in parts}
    assert [r.key for r in disk(parts, u)] == ["disk:/", "disk:/home"]


def test_disk_explicit_mountpoints_only():
    parts = [Part("/dev/sda1", "/", "ext4", ""), Part("/dev/sda2", "/var", "ext4", "")]
    u = {"/": usage(50), "/var": usage(50), "/dev/shm": usage(90), "/mnt/nfs": usage(10)}
    # tmpfs and network mounts are not in psutil's partition list at all, but
    # must still be checked when the user names them.
    results = disk(parts, u, mountpoints=["/var", "/dev/shm", "/mnt/nfs"])
    assert [(r.key, r.ok) for r in results] == [
        ("disk:/var", True), ("disk:/dev/shm", False), ("disk:/mnt/nfs", True)]


def test_disk_explicit_mountpoint_that_cannot_be_read_is_reported():
    err = FileNotFoundError(2, "No such file or directory")
    [r] = disk([], {"/mnt/backup": err}, mountpoints=["/mnt/backup"])
    assert (r.key, r.ok, r.severity) == ("disk:/mnt/backup", False, "warning")
    assert r.message == "cannot read disk usage of /mnt/backup: No such file or directory"


def test_disk_skips_mount_that_vanished():
    parts = [Part("/dev/sda1", "/", "ext4", ""), Part("/dev/sdb1", "/mnt", "ext4", "")]
    assert [r.key for r in disk(parts, {"/": usage(1), "/mnt": OSError("gone")})] == ["disk:/"]


def test_disk_message_is_human_readable():
    [r] = disk([Part("/dev/sda1", "/var", "ext4", "")], {"/var": usage(87.25)})
    assert r.message == "/var is 87.2% full (12.8 GB free of 100.0 GB)"


# =============================================================== memory

VM = namedtuple("VM", "total available percent")


def mem_check(**cfg):
    ps = FakePsutil()
    return MemoryCheck(section("memory", **cfg), ps), ps


def set_mem(ps, pct):
    total = 8 * 2 ** 30
    ps.vm = VM(total, total * (100 - pct) / 100, pct)


@pytest.mark.parametrize("pct,ok,sev", [
    (0, True, "info"), (89.9, True, "info"), (90.0, False, "warning"), (96.9, False, "warning"),
    (97.0, False, "critical"), (100, False, "critical")])
def test_memory_thresholds(pct, ok, sev):
    check, ps = mem_check()
    set_mem(ps, pct)
    [r] = check.run()
    assert (r.key, r.ok, r.severity) == ("memory:ram", ok, sev)
    from qorovul.i18n import EN
    assert r.message == "RAM usage %.1f%% (%s available of 8.0 GB)" % (
        pct, EN.size(8 * 2 ** 30 * (100 - pct) / 100))


def test_memory_no_critical_threshold():
    check, ps = mem_check(critical_threshold=None)
    set_mem(ps, 99.9)
    assert check.run()[0].severity == "warning"


def test_memory_check_is_stateless():
    # The sustain requirement lives in the persisted alert state, not here.
    check, ps = mem_check()
    set_mem(ps, 95)
    assert [check.run()[0].ok for _ in range(3)] == [False, False, False]
    set_mem(ps, 50)
    assert check.run()[0].ok


# =============================================================== service

def svc(units, states, **cfg):
    seen = []

    def fake(us):
        seen.append(list(us))
        return states
    results = ServiceCheck(section("service", units=units, **cfg), fake).run()
    return results, seen


def test_service_states():
    results, seen = svc(["nginx", "backup.timer", "pg", "x", "y"],
                        ["active", "active", "failed", "inactive", "reloading"])
    assert seen == [["nginx.service", "backup.timer", "pg.service", "x.service", "y.service"]]
    assert [(r.key, r.ok, r.severity) for r in results] == [
        ("service:nginx.service", True, "info"),
        ("service:backup.timer", True, "info"),
        ("service:pg.service", False, "critical"),
        ("service:x.service", False, "critical"),
        ("service:y.service", True, "info"),
    ]
    assert results[2].message == "pg.service is failed"


@pytest.mark.parametrize("state", ["activating", "deactivating", "unknown", ""])
def test_service_transitional_states_are_not_ok(state):
    [r], _ = svc(["nginx"], [state])
    assert not r.ok


def test_service_no_units_runs_nothing():
    results, seen = svc([], [])
    assert results == [] and seen == []


def test_service_custom_severity():
    [r], _ = svc(["nginx"], ["failed"], severity="warning")
    assert r.severity == "warning"


def test_systemctl_failure_reports_stderr(monkeypatch):
    import subprocess
    from qorovul.checks import service as mod

    class P:
        stdout = ""
        stderr = "Failed to connect to bus:\n  Host is down\n"
        returncode = 1
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: P())
    with pytest.raises(RuntimeError, match="systemctl is-active failed: Failed to connect to bus: Host is down"):
        mod._systemctl_is_active(["nginx.service"])


def test_systemctl_inactive_units_parse(monkeypatch):
    import subprocess
    from qorovul.checks import service as mod

    class P:
        stdout = "active\ninactive\n"
        stderr = ""
        returncode = 3
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: P())
    assert mod._systemctl_is_active(["a.service", "b.service"]) == ["active", "inactive"]


def test_service_mismatched_output_raises():
    with pytest.raises(RuntimeError):
        svc(["a", "b"], ["active"])


# =============================================================== ssh

NOW = datetime(2026, 11, 16, 12, 0, 0).timestamp()


def syslog(ts, msg, prog="sshd[1234]"):
    return "%s web-01 %s: %s" % (datetime.fromtimestamp(ts).strftime("%b %d %H:%M:%S"), prog, msg)


def iso(ts, msg, prog="sshd[1234]"):
    return "%s web-01 %s: %s" % (
        datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.123456+00:00"),
        prog, msg)


def failed(ip="203.0.113.9", port=40000, user="root"):
    return "Failed password for %s from %s port %d ssh2" % (user, ip, port)


class FakeLog:
    """A fake log file supporting append, rotation and truncation."""

    def __init__(self):
        self.data = b""
        self.ino = 1

    def append(self, *lines):
        self.data += "".join(ln + "\n" for ln in lines).encode()

    def rotate(self):
        self.data = b""
        self.ino += 1

    def stat(self, path):
        return os.stat_result((0o640, self.ino, 1, 1, 0, 0, len(self.data), 0, 0, 0))

    def open(self, path, mode="rb"):
        return io.BytesIO(self.data)


def failures(result):
    """The failure count from an (English) ssh message: "...: <count> (users: ...)"."""
    return int(re.search(r": (\d+)(?: \(|$)", result.message).group(1))


def ssh_check(log=None, clock=lambda: NOW, journal=None, readable=True, **cfg):
    log = log or FakeLog()
    return SSHCheck(section("ssh", **cfg), clock=clock, opener=log.open, stat=log.stat,
                    readable=lambda p: readable and p == "/var/log/auth.log",
                    journal=journal or (lambda since: []),
                    has_journalctl=lambda: journal is not None), log


@pytest.mark.parametrize("n,alerts", [(19, False), (20, True), (21, True)])
def test_ssh_threshold_boundary(n, alerts):
    check, log = ssh_check()
    log.append(*[syslog(NOW - 60, failed(port=40000 + i)) for i in range(n)])
    results = check.run()
    assert bool(results) is alerts
    if alerts:
        assert results[0].key == "ssh:203.0.113.9"
        assert results[0].message == ("failed SSH logins from 203.0.113.9 in the last 10m: "
                                      "%d (users: root)" % n)
        assert results[0].severity == "warning"


def test_ssh_counts_per_ip():
    check, log = ssh_check(failures=3)
    log.append(*[syslog(NOW, failed("198.51.100.1", 1000 + i)) for i in range(3)])
    log.append(*[syslog(NOW, failed("198.51.100.2", 2000 + i)) for i in range(2)])
    assert [r.key for r in check.run()] == ["ssh:198.51.100.1"]


def test_ssh_window_expiry():
    clock = [NOW]
    check, log = ssh_check(failures=3, clock=lambda: clock[0])
    log.append(*[syslog(NOW - 9 * 60, failed(port=i)) for i in range(3)])
    assert check.run()
    clock[0] = NOW + 61  # oldest events now > 10 minutes old
    assert check.run() == []


def test_ssh_old_lines_outside_window_ignored():
    check, log = ssh_check(failures=3)
    log.append(*[syslog(NOW - 11 * 60, failed(port=i)) for i in range(5)])
    assert check.run() == []


def test_ssh_does_not_double_count_one_connection():
    # One password guess for an unknown user logs 2 lines; 3 tries on one
    # connection log 3 Failed lines. Total attempts = 1 + 3 = 4.
    check, log = ssh_check(failures=4)
    log.append(
        syslog(NOW, "Invalid user admin from 203.0.113.9 port 5000"),
        syslog(NOW, "Failed password for invalid user admin from 203.0.113.9 port 5000 ssh2"),
        syslog(NOW, failed(port=6000)), syslog(NOW, failed(port=6000)),
        syslog(NOW, failed(port=6000)),
        syslog(NOW, "Connection closed by authenticating user root 203.0.113.9 port 6000 [preauth]"),
    )
    [r] = check.run()
    assert failures(r) == 4
    assert "admin" in r.message and "root" in r.message


def test_ssh_key_only_server_markers_count():
    check, log = ssh_check(failures=3)
    log.append(
        syslog(NOW, "Invalid user oracle from 203.0.113.9 port 1"),
        syslog(NOW, "Connection closed by invalid user oracle 203.0.113.9 port 1 [preauth]"),
        syslog(NOW, "Connection closed by authenticating user root 203.0.113.9 port 2 [preauth]"),
        syslog(NOW, "Disconnected from authenticating user root 203.0.113.9 port 3 [preauth]"),
    )
    assert failures(check.run()[0]) == 3


def test_ssh_ignores_success_and_other_programs():
    check, log = ssh_check(failures=1)
    log.append(
        syslog(NOW, "Accepted publickey for deploy from 203.0.113.9 port 1 ssh2"),
        syslog(NOW, failed(), prog="sudo"),
        syslog(NOW, "pam_unix(sshd:auth): authentication failure; rhost=203.0.113.9"),
    )
    assert check.run() == []


def test_ssh_ignore_ips_and_cidr():
    check, log = ssh_check(failures=1, ignore_ips=["10.0.0.0/8", "192.0.2.5"])
    log.append(syslog(NOW, failed("10.1.2.3")), syslog(NOW, failed("192.0.2.5")),
               syslog(NOW, failed("192.0.2.6")))
    assert [r.key for r in check.run()] == ["ssh:192.0.2.6"]


def test_ssh_ipv6_and_sshd_session():
    check, log = ssh_check(failures=2)
    log.append(*[iso(NOW, failed("2001:db8::1", port=i), prog="sshd-session[99]")
                 for i in range(2)])
    assert [r.key for r in check.run()] == ["ssh:2001:db8::1"]


def test_ssh_incremental_reads_only_new_lines():
    check, log = ssh_check(failures=3)
    log.append(*[syslog(NOW, failed(port=i)) for i in range(2)])
    assert check.run() == []
    assert check.run() == []  # nothing new, still 2
    log.append(syslog(NOW, failed(port=99)))
    assert failures(check.run()[0]) == 3


def test_ssh_partial_line_is_completed_next_read():
    check, log = ssh_check(failures=1)
    line = syslog(NOW, failed())
    log.data = line[:30].encode()
    assert check.run() == []
    log.data += (line[30:] + "\n").encode()
    assert len(check.run()) == 1


def test_ssh_survives_rotation_keeping_window():
    check, log = ssh_check(failures=3)
    log.append(*[syslog(NOW, failed(port=i)) for i in range(2)])
    check.run()
    log.rotate()
    log.append(syslog(NOW, failed(port=50)))
    assert failures(check.run()[0]) == 3


def test_ssh_survives_truncation():
    check, log = ssh_check(failures=1)
    log.append(*[syslog(NOW - 3600, "noise %d" % i) for i in range(50)])
    check.run()
    log.data = b""
    log.append(syslog(NOW, failed()))  # same inode, smaller size
    assert len(check.run()) == 1


def test_ssh_first_read_only_tails_large_logs(monkeypatch):
    import qorovul.checks.ssh as ssh
    monkeypatch.setattr(ssh, "INITIAL_TAIL_BYTES", 400)
    check, log = ssh_check(failures=1)
    log.append(*[syslog(NOW, failed(port=i)) for i in range(50)])
    [r] = check.run()
    count = failures(r)
    assert 1 <= count < 50  # only the tail was read, and no torn first line


def test_ssh_journal_fallback():
    calls = []

    def journal(since):
        calls.append(since)
        return ["%d.000000 web-01 sshd[1]: %s" % (NOW, failed(port=i)) for i in range(20)]
    check, _ = ssh_check(journal=journal, readable=False)
    [r] = check.run()
    assert r.key == "ssh:203.0.113.9"
    assert calls == [NOW - 600]
    assert len(check.run()) == 1  # rebuilt each run, not accumulated
    assert failures(check.run()[0]) == 20


def test_ssh_no_source_raises():
    check, _ = ssh_check(readable=False)
    with pytest.raises(RuntimeError, match="no readable SSH log source"):
        check.run()


def test_ssh_source_file_does_not_fall_back_to_journal():
    check, _ = ssh_check(readable=False, journal=lambda s: [], source="file")
    with pytest.raises(RuntimeError, match="none of the SSH log files are readable"):
        check.run()


def test_ssh_cleared_message():
    check, _ = ssh_check()
    assert check.cleared_message("ssh:1.2.3.4") == "failed logins from 1.2.3.4 dropped below 20 per 10m"


def test_parse_timestamp_formats():
    ts = datetime(2026, 11, 16, 11, 59, 30).timestamp()
    assert parse_timestamp("Nov 16 11:59:30 host sshd[1]: x", NOW) == ts
    assert parse_timestamp("Nov  6 11:59:30 host x", NOW) == datetime(2026, 11, 6, 11, 59, 30).timestamp()
    assert parse_timestamp("2026-11-16T10:00:00.5+00:00 host x", NOW) == \
        datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc).timestamp() + 0.5
    assert parse_timestamp("2026-11-16T10:00:00Z host x", NOW) == \
        datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc).timestamp()
    assert parse_timestamp("1763290000.250000 host x", NOW) == 1763290000.25
    assert parse_timestamp("garbage", NOW) is None


def test_parse_timestamp_year_rollover():
    jan = datetime(2027, 1, 1, 0, 5).timestamp()
    assert parse_timestamp("Dec 31 23:59:00 host x", jan) == datetime(2026, 12, 31, 23, 59).timestamp()


def test_parse_line_rejects_bad_ip():
    assert parse_line("sshd[1]: Failed password for root from 999.1.1.1 port 22 ssh2") is None
    assert parse_line("sshd[1]: Failed password for root from 1.2.3.4 port 22 ssh2") == \
        ("1.2.3.4", 22, "root", 1)


def test_ssh_user_with_spaces_from_attacker_input():
    line = "sshd[1]: Failed password for invalid user a b from 1.2.3.4 port 7 ssh2"
    assert parse_line(line) == ("1.2.3.4", 7, "a b", 1)


@pytest.mark.parametrize("line,real_ip", [
    ("sshd[1]: Failed password for invalid user root from 10.0.0.1 port 22 from 203.0.113.9 "
     "port 51022 ssh2", "203.0.113.9"),
    ("sshd[1]: Invalid user x from 10.0.0.1 port 22 from 203.0.113.9 port 51022", "203.0.113.9"),
    ("sshd[1]: Connection closed by invalid user a 10.0.0.1 port 22 203.0.113.9 port 51022 "
     "[preauth]", "203.0.113.9"),
    ("sshd[1]: Failed publickey for git from 203.0.113.9 port 51022 ssh2: ED25519 SHA256:abc",
     "203.0.113.9"),
])
def test_ssh_user_name_cannot_spoof_source_ip(line, real_ip):
    ip, port, _user, _failed = parse_line(line)
    assert (ip, port) == (real_ip, 51022)


def test_ssh_failed_none_probe_is_not_a_password_guess():
    check, log = ssh_check(failures=1)
    log.append(
        syslog(NOW, "Invalid user admin from 203.0.113.9 port 5000"),
        syslog(NOW, "Failed none for invalid user admin from 203.0.113.9 port 5000 ssh2"),
        syslog(NOW, "Failed password for invalid user admin from 203.0.113.9 port 5000 ssh2"),
        syslog(NOW, "Failed none for invalid user guest from 203.0.113.9 port 5001 ssh2"),
    )
    # port 5000: one real guess; port 5001: a failed connection without a guess
    assert failures(check.run()[0]) == 2


def test_ssh_rsyslog_repeated_message_counts_each_attempt():
    line = ("Nov 16 11:51:24 web-01 sshd[2305]: message repeated 2 times: "
            "[ Failed password for root from 203.0.113.9 port 51040 ssh2]")
    assert parse_line(line) == ("203.0.113.9", 51040, "root", 2)


# =============================================================== ssl

def cert_expiring(days, now):
    exp = datetime.fromtimestamp(now + days * 86400, timezone.utc)
    return {"notAfter": exp.strftime("%b %d %H:%M:%S %Y GMT")}


def ssl_check(fetch, sleeps=None, **cfg):
    cfg.setdefault("domains", ["example.com"])
    sleeps = [] if sleeps is None else sleeps
    return SSLCheck(section("ssl", **cfg), fetch=fetch, clock=lambda: NOW,
                    sleep=sleeps.append).run()


@pytest.mark.parametrize("days,ok,sev", [
    (90, True, "info"), (14.01, True, "info"), (14, False, "warning"), (3.01, False, "warning"),
    (3, False, "critical"), (0.5, False, "critical")])
def test_ssl_expiry_boundaries(days, ok, sev):
    [r] = ssl_check(lambda h, p, t: cert_expiring(days, NOW))
    assert (r.key, r.ok, r.severity) == ("ssl:example.com", ok, sev)


def test_ssl_message():
    [r] = ssl_check(lambda h, p, t: cert_expiring(9.5, NOW))
    assert re.match(r"example\.com certificate expires on \d{4}-\d\d-\d\d, days left: 9$",
                    r.message)


def test_ssl_expired_certificate():
    [r] = ssl_check(lambda h, p, t: cert_expiring(-2, NOW))
    assert (r.ok, r.severity) == (False, "critical")
    assert "EXPIRED" in r.message


def test_ssl_verification_failure_is_critical():
    def fetch(h, p, t):
        raise CertVerifyError("certificate has expired")
    [r] = ssl_check(fetch)
    assert (r.ok, r.severity) == (False, "critical")
    assert "certificate has expired" in r.message


@pytest.mark.parametrize("exc", [socket.timeout("timed out"), ConnectionRefusedError("refused"),
                                 socket.gaierror("no such host"), ssl_mod.SSLError("handshake")])
def test_ssl_connection_errors(exc):
    def fetch(h, p, t):
        raise exc
    [r] = ssl_check(fetch)
    assert (r.ok, r.severity) == (False, "warning")
    assert r.message.startswith("cannot check certificate of example.com:443")


def test_ssl_connection_error_is_retried_once_before_alerting():
    calls, sleeps = [], []

    def fetch(h, p, t):
        calls.append(h)
        raise ConnectionResetError("reset")
    [r] = ssl_check(fetch, sleeps)
    assert not r.ok and len(calls) == 2 and sleeps == [3.0]


def test_ssl_transient_connection_error_does_not_alert():
    calls = []

    def fetch(h, p, t):
        calls.append(h)
        if len(calls) == 1:
            raise socket.timeout("blip")
        return cert_expiring(60, NOW)
    [r] = ssl_check(fetch)
    assert r.ok and len(calls) == 2


def test_ssl_verification_failure_is_not_retried():
    calls = []

    def fetch(h, p, t):
        calls.append(h)
        raise CertVerifyError("self-signed certificate")
    [r] = ssl_check(fetch)
    assert r.severity == "critical" and len(calls) == 1


def test_ssl_custom_port_and_thresholds():
    seen = []

    def fetch(h, p, t):
        seen.append((h, p, t))
        return cert_expiring(20, NOW)
    [r] = ssl_check(fetch, domains=["mail.example.com:993"], warn_days=30, timeout=5)
    assert seen == [("mail.example.com", 993, 5.0)]
    assert r.key == "ssl:mail.example.com:993" and not r.ok


def test_ssl_context_verifies_but_not_python_strict_mode():
    import ssl as ssl_mod
    from qorovul.checks.ssl import make_context
    ctx = make_context()
    assert ctx.verify_mode == ssl_mod.CERT_REQUIRED
    assert ctx.check_hostname is True
    assert not ctx.verify_flags & ssl_mod.VERIFY_X509_STRICT


def test_ssl_parse_target():
    assert parse_target("a.com") == ("a.com", 443)
    assert parse_target("a.com:8443") == ("a.com", 8443)
    assert parse_target("[2001:db8::1]:8443") == ("2001:db8::1", 8443)


# =============================================================== ports

PROC_TCP = """\
  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 1 1
   1: 0100007F:1538 00000000:0000 0A 00000000:00000000 00:00000000 00000000   113        0 2 1
   2: 00000000:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 3 1
   3: 0A00000A:0016 0B00000A:D431 01 00000000:00000000 02:0009FB4B 00000000     0        0 4 1
   4: 3500007F:0035 00000000:0000 0A 00000000:00000000 00:00000000 00000000   101        0 5 1
"""
PROC_TCP6 = """\
  sl  local_address                         remote_address                        st
   0: 00000000000000000000000000000000:0016 00000000000000000000000000000000:0000 0A 0
   1: 00000000000000000000000001000000:18EB 00000000000000000000000000000000:0000 0A 0
   2: 00000000000000000000000000000000:01BB 00000000000000000000000000000000:0000 0A 0
"""


USERS = {0: "root", 113: "postgres", 1000: "deploy", 101: "systemd-resolve"}


def ports(tcp=PROC_TCP, tcp6=PROC_TCP6, owners=None, **cfg):
    files = {"/proc/net/tcp": tcp, "/proc/net/tcp6": tcp6}
    return PortsCheck(section("ports", **cfg), read_file=files.get,
                      user_name=lambda uid: USERS.get(uid, "uid %d" % uid),
                      find_owners=lambda inodes: {i: v for i, v in (owners or {}).items()
                                                  if i in inodes}).run()


def test_ports_decode_addr():
    assert decode_addr("0100007F:0035", socket.AF_INET) == ("127.0.0.1", 53)
    assert decode_addr("00000000000000000000000001000000:18EB", socket.AF_INET6) == ("::1", 6379)
    v6 = "B80D0120000000000000000001000000:0050"
    assert decode_addr(v6, socket.AF_INET6) == ("2001:db8::1", 80)


def test_ports_parse_only_listen_state():
    assert parse_proc_net(PROC_TCP, socket.AF_INET) == {
        Listener("0.0.0.0", 22, 0, 1), Listener("127.0.0.1", 5432, 113, 2),
        Listener("0.0.0.0", 8080, 1000, 3), Listener("127.0.0.53", 53, 101, 5)}


def test_ports_parse_accepts_line_iterators_and_garbage():
    lines = iter(PROC_TCP.splitlines() + ["garbage", "   9: ZZZZ:0016 0:0 0A x"])
    assert len(parse_proc_net(lines, socket.AF_INET)) == 4


def test_ports_parse_short_lines_have_no_owner():
    assert parse_proc_net(PROC_TCP6, socket.AF_INET6) == {
        Listener("::", 22), Listener("::1", 6379), Listener("::", 443)}


def test_ports_default_allowlist_ignores_loopback():
    results = ports()
    assert [(r.key, r.ok, r.severity) for r in results] == [
        ("ports:tcp/443", False, "warning"), ("ports:tcp/8080", False, "warning")]
    assert results[1].message == "unexpected TCP listener on port 8080 (0.0.0.0), user deploy"
    assert results[0].message == "unexpected TCP listener on port 443 (::)"


def test_ports_reports_process_when_resolvable():
    [_, r] = ports(owners={3: "python3 (pid 4242)"})
    assert r.message == ("unexpected TCP listener on port 8080 (0.0.0.0), user deploy, "
                         "process python3 (pid 4242)")


def test_ports_process_lookup_is_cached_per_socket():
    calls = []

    def find(inodes):
        calls.append(set(inodes))
        return {}
    files = {"/proc/net/tcp": PROC_TCP, "/proc/net/tcp6": None}
    check = PortsCheck(section("ports"), read_file=files.get, find_owners=find,
                       user_name=str)
    check.run()
    check.run()
    assert calls == [{3}]  # scanned once, although permission was denied
    files["/proc/net/tcp"] = PROC_TCP.replace("1000        0 3 1", "1000        0 77 1")
    check.run()
    assert calls == [{3}, {77}]  # a new socket on the port is looked up again
    assert set(check._owners) == {77}


def test_find_socket_owners(tmp_path):
    from qorovul.checks.ports import find_socket_owners
    for pid, comm, links in (("10", "nginx", {"3": "socket:[555]", "4": "/dev/null"}),
                             ("11", "sshd", {"3": "socket:[777]"})):
        fd = tmp_path / pid / "fd"
        fd.mkdir(parents=True)
        (tmp_path / pid / "comm").write_text(comm + "\n")
        for name, target in links.items():
            os.symlink(target, str(fd / name))
    (tmp_path / "self").mkdir()
    (tmp_path / "12").mkdir()  # process without readable fd dir
    assert find_socket_owners({555, 999}, proc=str(tmp_path)) == {555: "nginx (pid 10)"}
    assert find_socket_owners({1}, proc=str(tmp_path / "missing")) == {}


def test_ports_unknown_uid_is_shown_numerically():
    from qorovul.checks.ports import _user_name
    assert _user_name(4000000000) == "uid 4000000000"


def test_ports_fully_allowed():
    assert ports(allowed=[22, 443, "8080"]) == []


def test_ports_loopback_watched_when_enabled():
    keys = [r.key for r in ports(allowed=[22, 443, 8080], ignore_loopback=False)]
    assert keys == ["ports:tcp/53", "ports:tcp/5432", "ports:tcp/6379"]


def test_ports_address_specific_allow():
    keys = [r.key for r in ports(allowed=[22, 443, 8080, "127.0.0.1:5432", "[::1]:6379"],
                                 ignore_loopback=False)]
    assert keys == ["ports:tcp/53"]


def test_ports_address_allow_does_not_cover_other_addresses():
    tcp = PROC_TCP.replace("0100007F:1538", "00000000:1538")  # 5432 on 0.0.0.0
    keys = [r.key for r in ports(tcp=tcp, allowed=[22, 443, 8080, "127.0.0.1:5432"])]
    assert keys == ["ports:tcp/5432"]


def test_ports_groups_addresses_per_port():
    tcp6 = PROC_TCP6.replace(":01BB", ":1F90")  # 8080 on :: as well
    [r] = ports(tcp6=tcp6, allowed=[22])
    assert r.message == "unexpected TCP listener on port 8080 (0.0.0.0, ::), user deploy"


def test_ports_ipv4_mapped_loopback_is_loopback():
    tcp6 = PROC_TCP6 + "   3: 0000000000000000FFFF00000100007F:2382 0000:0000 0A 0\n"
    assert [r.key for r in ports(tcp6=tcp6)] == ["ports:tcp/443", "ports:tcp/8080"]


def test_ports_without_ipv6():
    assert [r.key for r in ports(tcp6=None)] == ["ports:tcp/8080"]


def test_ports_unreadable_proc_raises():
    with pytest.raises(RuntimeError):
        ports(tcp=None, tcp6=None)


def test_ports_cleared_message():
    check = PortsCheck(section("ports"), read_file=lambda p: None)
    assert check.cleared_message("ports:tcp/8080") == "TCP port 8080 is no longer listening"


# =============================================================== registry

def test_registry_has_exactly_the_six_checks():
    assert sorted(REGISTRY) == ["disk", "memory", "ports", "service", "ssh", "ssl"]


def test_build_checks_respects_enabled(monkeypatch):
    cfg = validate({"checks": {n: {"enabled": n in ("service", "ssl")} for n in REGISTRY}}, env={})
    assert sorted(c.name for c in build_checks(cfg)) == ["service", "ssl"]
