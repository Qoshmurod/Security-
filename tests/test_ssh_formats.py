"""SSH parsing against log samples in each distribution's real format."""

import os
import subprocess
from datetime import datetime

import pytest

import ssh_samples as samples
from qorovul.checks import ssh as ssh_mod
from qorovul.checks.ssh import FailureWindow, LogTail, SSHCheck, parse_timestamp
from qorovul.config import validate

NOW = datetime(2026, 11, 16, 12, 0, 0).timestamp()


def counts(text, now=None):
    lines = text.splitlines()
    if now is None:  # samples with absolute timestamps: "now" is just after the last line
        now = max(parse_timestamp(ln, NOW) for ln in lines) + 30
    window = FailureWindow()
    for line in lines:
        window.add_line(line, now)
    window.prune(now - 600)
    return {ip: (n, sorted(users)) for ip, (n, users) in window.counts().items()}


def test_ubuntu_2204_classic_syslog():
    assert counts(samples.UBUNTU_2204_AUTH_LOG, NOW) == {
        # port 51022: one guess for an unknown user (3 lines) = 1
        # port 51040: "Failed password" + "message repeated 2 times" = 3
        "203.0.113.9": (4, ["admin", "root"]),
        # one aborted login; the bare "Connection closed by <ip>" probe is not a failure
        "192.0.2.44": (1, ["root"]),
    }


def test_ubuntu_2404_iso_timestamps_and_spoofed_user():
    assert counts(samples.UBUNTU_2404_AUTH_LOG) == {
        "2001:db8::bad": (1, ["oracle"]),
        # includes the attempt whose user name claims to come from 10.0.0.1
        "198.51.100.23": (2, ["git", "root from 10.0.0.1 port 22"]),
    }


def test_almalinux_secure():
    assert counts(samples.ALMALINUX_9_SECURE, NOW) == {"203.0.113.77": (3, ["root", "test"])}


def test_journald_short_unix_with_sshd_session():
    assert counts(samples.JOURNAL_SHORT_UNIX_OPENSSH_10) == {
        "203.0.113.200": (2, ["root", "ubnt"])}


def test_successful_logins_never_count():
    for text in (samples.UBUNTU_2204_AUTH_LOG, samples.UBUNTU_2404_AUTH_LOG,
                 samples.ALMALINUX_9_SECURE, samples.JOURNAL_SHORT_UNIX_OPENSSH_10):
        seen = counts(text, NOW if text[0].isalpha() else None)
        assert not {"198.51.100.7", "192.0.2.10"} & set(seen)


def test_check_end_to_end_on_almalinux_sample():
    cfg = validate({"checks": {"ssh": {"failures": 3, "log_paths": ["/var/log/secure"]}}},
                   env={})["checks"]["ssh"]
    data = samples.ALMALINUX_9_SECURE.encode()

    class Fh:
        def __init__(self):
            import io
            self.b = io.BytesIO(data)

        def __enter__(self):
            return self.b

        def __exit__(self, *a):
            return False
    check = SSHCheck(cfg, clock=lambda: NOW, opener=lambda p, m: Fh(),
                     stat=lambda p: os.stat_result((0, 7, 1, 1, 0, 0, len(data), 0, 0, 0)),
                     readable=lambda p: True)
    [r] = check.run()
    assert r.key == "ssh:203.0.113.77"
    assert r.message == ("3 failed SSH logins from 203.0.113.77 in the last 10m "
                         "(users: root, test)")


# ------------------------------------------------------------- rotation

class Files:
    """Several fake files with inodes, enough to model logrotate."""

    def __init__(self):
        self.files = {}  # path -> [inode, bytes]

    def stat(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        ino, data = self.files[path]
        return os.stat_result((0o640, ino, 1, 1, 0, 0, len(data), 0, 0, 0))

    def open(self, path, mode="rb"):
        import io
        return io.BytesIO(self.files[path][1])


def test_lines_written_just_before_rotation_are_not_lost():
    fs = Files()
    fs.files["/var/log/auth.log"] = [1, b"one\ntwo\n"]
    tail = LogTail("/var/log/auth.log", fs.open, fs.stat)
    assert tail.read_new() == ["one", "two"]
    # "three" is appended, then logrotate renames the file and creates a new one.
    fs.files["/var/log/auth.log.1"] = [1, b"one\ntwo\nthree\n"]
    fs.files["/var/log/auth.log"] = [2, b"four\n"]
    assert tail.read_new() == ["three", "four"]
    assert tail.read_new() == []


def test_rotation_with_compressed_or_missing_old_file():
    fs = Files()
    fs.files["/var/log/auth.log"] = [1, b"one\n"]
    tail = LogTail("/var/log/auth.log", fs.open, fs.stat)
    tail.read_new()
    fs.files["/var/log/auth.log"] = [2, b"two\n"]  # no .1 (already gzipped)
    assert tail.read_new() == ["two"]
    fs.files["/var/log/auth.log.1"] = [9, b"unrelated older file\n"]
    fs.files["/var/log/auth.log"] = [3, b"three\n"]
    assert tail.read_new() == ["three"]  # .1 is not the file we were reading


def test_rotation_joins_a_line_split_across_reads():
    fs = Files()
    fs.files["/var/log/auth.log"] = [1, b"complete\npart"]
    tail = LogTail("/var/log/auth.log", fs.open, fs.stat)
    assert tail.read_new() == ["complete"]
    fs.files["/var/log/auth.log.1"] = [1, b"complete\npartial line\n"]
    fs.files["/var/log/auth.log"] = [2, b""]
    assert tail.read_new() == ["partial line"]


# ------------------------------------------------------------- journalctl

def test_journalctl_invocation(monkeypatch):
    seen = {}

    class P:
        returncode = 0
        stdout = samples.JOURNAL_SHORT_UNIX_OPENSSH_10
        stderr = ""

    def run(argv, **kw):
        seen["argv"] = argv
        seen["timeout"] = kw.get("timeout")
        return P()
    monkeypatch.setattr(subprocess, "run", run)
    lines = ssh_mod._journal_lines(1794829400.7)
    assert len(lines) == 6
    argv = seen["argv"]
    assert argv[0] == "journalctl" and "--since=@1794829400" in argv
    assert "--output=short-unix" in argv and "--no-pager" in argv
    # matched by identifier, so it works for ssh.service, sshd.service and OpenSSH 10
    assert [a for a in argv if a.startswith("--identifier=")] == [
        "--identifier=sshd", "--identifier=sshd-session", "--identifier=sshd-auth"]
    assert seen["timeout"]


def test_journalctl_failure_is_an_error(monkeypatch):
    class P:
        returncode = 1
        stdout = ""
        stderr = "No journal files were opened due to insufficient permissions.\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: P())
    with pytest.raises(RuntimeError, match="insufficient permissions"):
        ssh_mod._journal_lines(0)
