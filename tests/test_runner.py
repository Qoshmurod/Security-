import json
import threading

import pytest

from qorovul.__main__ import main
from qorovul.checks.base import Check, CheckResult
from qorovul.config import validate
from qorovul.runner import Runner, run_check
from qorovul.state import ALERT, RECOVERED, StateStore


class FakeCheck(Check):
    def __init__(self, name, *script):
        super().__init__({})
        self.name = name
        self.script = list(script)
        self.calls = 0

    def run(self):
        self.calls += 1
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        return step


class FakeNotifier:
    def __init__(self):
        self.sent = []
        self.up = True

    def send_events(self, events, hostname):
        if not self.up:
            return []
        self.sent.extend((e.kind, e.key) for e in events)
        return list(events)


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def make(tmp_path, *checks, **cfg_overrides):
    data = {"hostname": "test-host", "state_file": str(tmp_path / "state.json"),
            "alerts": {"recovery_cycles": 1}}
    data.update(cfg_overrides)
    cfg = validate(data, env={})
    clock = Clock()
    notifier = FakeNotifier()
    runner = Runner(cfg, notifier, checks=list(checks), clock=clock)
    return runner, notifier, clock


BAD = [CheckResult("disk:/", False, "warning", "full")]
GOOD = [CheckResult("disk:/", True, "info", "fine")]


def test_full_lifecycle(tmp_path):
    check = FakeCheck("disk", BAD, BAD, BAD, GOOD, GOOD)
    runner, notifier, clock = make(tmp_path, check)
    for _ in range(5):
        runner.run_cycle()
        clock.t += 30
    assert notifier.sent == [(ALERT, "disk:/"), (RECOVERED, "disk:/")]
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["keys"]["disk:/"]["status"] == "ok"
    assert state["keys"]["disk:/"]["last_event"]["kind"] == RECOVERED


def test_restart_does_not_resend(tmp_path):
    runner, notifier, clock = make(tmp_path, FakeCheck("disk", BAD))
    runner.run_cycle()
    runner2, notifier2, _ = make(tmp_path, FakeCheck("disk", BAD))
    runner2.clock.t = clock.t + 60
    runner2.run_cycle()
    assert notifier.sent == [(ALERT, "disk:/")]
    assert notifier2.sent == []


def test_telegram_outage_retries_next_cycle(tmp_path):
    runner, notifier, clock = make(tmp_path, FakeCheck("disk", BAD))
    notifier.up = False
    runner.run_cycle()
    clock.t += 30
    runner.run_cycle()
    notifier.up = True
    clock.t += 30
    runner.run_cycle()
    clock.t += 30
    runner.run_cycle()
    assert notifier.sent == [(ALERT, "disk:/")]


def test_check_exception_becomes_error_alert_and_keeps_other_keys(tmp_path):
    check = FakeCheck("ports", [CheckResult("ports:tcp/8080", False, "warning", "x")],
                      RuntimeError("boom"),
                      [CheckResult("ports:tcp/8080", False, "warning", "x")])
    runner, notifier, clock = make(tmp_path, check)
    runner.run_cycle()
    clock.t += 30
    runner.run_cycle()
    assert runner.engine.records["ports:tcp/8080"]["status"] == "failing"
    clock.t += 30
    runner.run_cycle()
    assert notifier.sent == [(ALERT, "ports:tcp/8080"), (ALERT, "ports:error"),
                             (RECOVERED, "ports:error")]
    assert runner.engine.records["ports:error"]["message"] == "ports check is running normally again"
    assert runner.engine.records["ports:error"]["last_event"]["kind"] == RECOVERED


def test_error_key_cleared_message_is_not_check_specific(tmp_path):
    from qorovul.checks.ports import PortsCheck
    from qorovul.config import validate as v
    check = PortsCheck(v({}, env={})["checks"]["ports"], read_file=lambda p: None)
    msg = Runner._cleared(check)
    assert msg("ports:error") == "ports check is running normally again"
    assert msg("ports:tcp/80") == "TCP port 80 is no longer listening"


def test_error_alert_carries_exception_text(tmp_path):
    runner, notifier, _ = make(tmp_path, FakeCheck("ssh", RuntimeError("no readable log")))
    runner.run_cycle()
    assert "no readable log" in runner.engine.records["ssh:error"]["message"]


def test_run_check_wraps_exceptions():
    results, complete = run_check(FakeCheck("ssh", ValueError("nope")))
    assert complete is False
    assert results == [CheckResult("ssh:error", False, "warning", "ssh check could not run: nope")]


def test_per_check_interval(tmp_path):
    fast = FakeCheck("disk", GOOD)
    slow = FakeCheck("ssl", [])
    runner, _, clock = make(tmp_path, fast, slow)
    for _ in range(10):  # 10 cycles x 30s = 5 minutes
        runner.run_cycle()
        clock.t += 30
    assert fast.calls == 10
    assert slow.calls == 1  # ssl defaults to hourly
    clock.t += 3600
    runner.run_cycle()
    assert slow.calls == 2


def test_skipped_check_does_not_clear_its_keys(tmp_path):
    slow = FakeCheck("ssl", [CheckResult("ssl:a.com", False, "warning", "soon")])
    runner, notifier, clock = make(tmp_path, slow)
    runner.run_cycle()
    for _ in range(5):
        clock.t += 30
        runner.run_cycle()
    assert notifier.sent == [(ALERT, "ssl:a.com")]
    assert runner.engine.records["ssl:a.com"]["status"] == "failing"


def test_disabled_check_records_are_dropped_on_start(tmp_path):
    runner, _, _ = make(tmp_path, FakeCheck("disk", BAD))
    runner.run_cycle()
    runner2, _, _ = make(tmp_path, FakeCheck("ports", []))
    assert "disk:/" not in runner2.engine.records


def test_state_write_failure_keeps_running(tmp_path, monkeypatch):
    runner, notifier, clock = make(tmp_path, FakeCheck("disk", BAD))
    monkeypatch.setattr(StateStore, "save", lambda self, records: False)
    runner.run_cycle()
    clock.t += 30
    runner.run_cycle()
    assert notifier.sent == [(ALERT, "disk:/")]  # in-memory dedupe still works


def test_run_forever_stops_on_event(tmp_path):
    check = FakeCheck("disk", GOOD)
    runner, _, _ = make(tmp_path, check)
    stop = threading.Event()
    t = threading.Thread(target=runner.run_forever, args=(stop,))
    t.start()
    stop.set()
    t.join(5)
    assert not t.is_alive()
    assert check.calls >= 1
    assert (tmp_path / "state.json").exists()


# ------------------------------------------------------------------ CLI

def test_cli_version(capsys):
    assert main(["version"]) == 0
    assert capsys.readouterr().out.startswith("qorovul ")


def test_cli_no_command_prints_help(capsys):
    assert main([]) == 2


def test_cli_config_error_exit_code(tmp_path, capsys):
    p = tmp_path / "c.yml"
    p.write_text("checks: {disk: {threshold: 500}}\n")
    assert main(["test", "-c", str(p)]) == 2
    assert "checks.disk.threshold" in capsys.readouterr().err


def test_cli_run_requires_telegram(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("QOROVUL_BOT_TOKEN", raising=False)
    monkeypatch.delenv("QOROVUL_CHAT_ID", raising=False)
    p = tmp_path / "c.yml"
    p.write_text("state_file: %s\n" % (tmp_path / "s.json"))
    assert main(["-c", str(p), "run", "--once"]) == 2
    assert "missing telegram.bot_token" in capsys.readouterr().err


def test_cli_status(tmp_path, capsys):
    runner, _, clock = make(tmp_path, FakeCheck("disk", BAD))
    runner.run_cycle()
    cfg = tmp_path / "c.yml"
    cfg.write_text("state_file: %s\n" % (tmp_path / "state.json"))
    assert main(["status", "-c", str(cfg)]) == 0
    out = capsys.readouterr().out
    assert "failing: 1" in out and "disk:/" in out and "FAILING" in out and "alert" in out
    assert main(["status", "--json", "-c", str(cfg)]) == 0
    assert json.loads(capsys.readouterr().out)["disk:/"]["status"] == "failing"


def test_cli_status_without_state(tmp_path, capsys):
    cfg = tmp_path / "c.yml"
    cfg.write_text("state_file: %s\n" % (tmp_path / "none.json"))
    assert main(["status", "-c", str(cfg)]) == 0
    assert "no state yet" in capsys.readouterr().out


@pytest.mark.parametrize("sent,failing,expected", [
    (True, False, 0), (True, True, 1), (False, False, 3)])
def test_cli_test_exit_codes(tmp_path, capsys, monkeypatch, sent, failing, expected):
    import qorovul.__main__ as cli

    class N:
        texts = []

        def send_text(self, text):
            N.texts.append(text)
            return sent

    result = [CheckResult("disk:/", not failing, "warning", "msg <b>")]
    monkeypatch.setattr(cli, "_notifier", lambda cfg: N())
    import qorovul.checks as checks_mod
    monkeypatch.setattr(checks_mod, "build_checks", lambda cfg: [FakeCheck("disk", result)])
    p = tmp_path / "c.yml"
    p.write_text("state_file: %s\n" % (tmp_path / "s.json"))
    assert main(["test", "-c", str(p)]) == expected
    out = capsys.readouterr().out
    assert "disk:/" in out
    assert "Qorovul test message" in N.texts[-1]
    assert "<b>" not in N.texts[-1].split("\n", 2)[-1]  # check messages are escaped
    assert not (tmp_path / "s.json").exists()  # test never touches state


# ----------------------------------------------- memory sustain (persisted)

HIGH = [CheckResult("memory:ram", False, "warning", "RAM usage 95.0%")]
LOW = [CheckResult("memory:ram", True, "info", "RAM usage 40.0%")]


def test_memory_alerts_only_after_sustained_cycles(tmp_path):
    runner, notifier, clock = make(tmp_path, FakeCheck("memory", HIGH))
    for expected in ([], [], [(ALERT, "memory:ram")], [(ALERT, "memory:ram")]):
        runner.run_cycle()
        clock.t += 30
        assert notifier.sent == expected


def test_memory_dip_resets_the_sustain_count(tmp_path):
    runner, notifier, clock = make(tmp_path, FakeCheck("memory", HIGH, HIGH, LOW, HIGH, HIGH, HIGH))
    for _ in range(5):
        runner.run_cycle()
        clock.t += 30
    assert notifier.sent == []
    runner.run_cycle()
    assert notifier.sent == [(ALERT, "memory:ram")]


def test_memory_sustain_count_survives_restart(tmp_path):
    runner, notifier, clock = make(tmp_path, FakeCheck("memory", HIGH))
    runner.run_cycle()
    clock.t += 30
    runner.run_cycle()
    assert notifier.sent == []
    runner2, notifier2, clock2 = make(tmp_path, FakeCheck("memory", HIGH))
    clock2.t = clock.t + 30
    runner2.run_cycle()  # third consecutive high reading, across the restart
    assert notifier2.sent == [(ALERT, "memory:ram")]


def test_restart_during_memory_incident_neither_recovers_nor_realerts(tmp_path):
    runner, notifier, clock = make(tmp_path, FakeCheck("memory", HIGH),
                                   alerts={"recovery_cycles": 2})
    for _ in range(4):
        runner.run_cycle()
        clock.t += 30
    assert notifier.sent == [(ALERT, "memory:ram")]
    runner2, notifier2, clock2 = make(tmp_path, FakeCheck("memory", HIGH),
                                      alerts={"recovery_cycles": 2})
    clock2.t = clock.t
    for _ in range(6):
        runner2.run_cycle()
        clock2.t += 30
    assert notifier2.sent == []


def test_sustained_cycles_config_drives_confirmation():
    cfg = validate({"checks": {"memory": {"sustained_cycles": 5}}}, env={})
    assert cfg["checks"]["memory"]["confirm_cycles"] == 5
    cfg = validate({"checks": {"memory": {"sustained_cycles": 5, "confirm_cycles": 2}}}, env={})
    assert cfg["checks"]["memory"]["confirm_cycles"] == 2


# ------------------------------------------------- scheduling / delivery

def test_wall_clock_jump_backwards_does_not_stall_checks(tmp_path):
    check = FakeCheck("disk", GOOD)
    cfg = validate({"state_file": str(tmp_path / "s.json")}, env={})
    wall, mono = Clock(1_800_000_000.0), Clock(5000.0)
    runner = Runner(cfg, FakeNotifier(), checks=[check], clock=wall, monotonic=mono)
    runner.run_cycle()
    wall.t -= 7 * 86400  # NTP correction / someone ran `date -s`
    mono.t += 30
    runner.run_cycle()
    assert check.calls == 2


def test_delivery_backoff_grows_and_resets(tmp_path):
    import qorovul.runner as mod

    class CountingNotifier(FakeNotifier):
        attempts = 0

        def send_events(self, events, hostname):
            CountingNotifier.attempts += 1
            return super().send_events(events, hostname)

    runner, _, clock = make(tmp_path, FakeCheck("disk", BAD))
    runner.notifier = notifier = CountingNotifier()
    notifier.up = False
    for _ in range(40):  # 20 minutes of outage, one cycle every 30s
        runner.run_cycle()
        clock.t += 30
    # 30s, 60s, 120s, 240s, then every 300s: far fewer than 40 attempts
    assert 5 <= CountingNotifier.attempts <= 9
    assert runner.retry_backoff == mod.RETRY_BACKOFF_MAX
    notifier.up = True
    clock.t += mod.RETRY_BACKOFF_MAX
    runner.run_cycle()
    assert notifier.sent == [(ALERT, "disk:/")]
    assert runner.retry_backoff == mod.RETRY_BACKOFF_START and runner.retry_at == 0.0


def test_service_restart_blip_is_not_alerted(tmp_path):
    blip = [CheckResult("service:nginx.service", False, "critical", "nginx.service is activating")]
    fine = [CheckResult("service:nginx.service", True, "info", "nginx.service is active")]
    runner, notifier, clock = make(tmp_path, FakeCheck("service", fine, blip, fine, fine))
    for _ in range(4):
        runner.run_cycle()
        clock.t += 30
    assert notifier.sent == []


# ------------------------------------------------------------ heartbeat

def hb_runner(tmp_path, get, **hb):
    cfg = validate({"state_file": str(tmp_path / "s.json"),
                    "heartbeat": dict({"url": "https://hc.example/ping/abc"}, **hb)}, env={})
    clock = Clock()
    return Runner(cfg, FakeNotifier(), checks=[FakeCheck("disk", BAD)], clock=clock,
                  http_get=get), clock


def test_heartbeat_pings_on_its_own_interval(tmp_path):
    calls = []

    def get(url, timeout):
        calls.append((url, timeout))
        return 200
    runner, clock = hb_runner(tmp_path, get, interval="2m", timeout=4)
    for _ in range(9):  # 4 minutes
        runner.run_cycle()
        clock.t += 30
    assert calls == [("https://hc.example/ping/abc", 4.0)] * 3  # t=0, 2m, 4m


def test_heartbeat_is_sent_even_while_checks_fail_and_telegram_is_down(tmp_path):
    calls = []
    runner, _ = hb_runner(tmp_path, lambda u, t: calls.append(u) or 200)
    runner.notifier.up = False
    runner.run_cycle()
    assert len(calls) == 1


def test_heartbeat_failure_is_logged_once_and_never_alerts(tmp_path, caplog):
    import logging
    results = [OSError("dns"), 503, 200]

    def get(url, timeout):
        r = results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    runner, clock = hb_runner(tmp_path, get, interval="30s")
    with caplog.at_level(logging.INFO, logger="qorovul.runner"):
        for _ in range(3):
            runner.run_cycle()
            clock.t += 30
    assert caplog.text.count("heartbeat ping failed") == 1
    assert "heartbeat ping is working again" in caplog.text
    assert "hc.example" not in caplog.text  # the URL is a secret
    assert not [k for k in runner.engine.records if "heartbeat" in k]


def test_heartbeat_disabled_by_default(tmp_path):
    calls = []
    cfg = validate({"state_file": str(tmp_path / "s.json")}, env={})
    runner = Runner(cfg, FakeNotifier(), checks=[], clock=Clock(),
                    http_get=lambda u, t: calls.append(u))
    runner.run_cycle()
    assert calls == []


# ------------------------------------------------------- systemd notify

def test_sd_notify_writes_to_notify_socket(tmp_path):
    import socket
    from qorovul.runner import sd_notify
    path = str(tmp_path / "notify.sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    server.bind(path)
    try:
        assert sd_notify("READY=1", env={"NOTIFY_SOCKET": path}) is True
        assert server.recv(64) == b"READY=1"
    finally:
        server.close()


def test_sd_notify_outside_systemd_is_a_noop(tmp_path):
    from qorovul.runner import sd_notify
    assert sd_notify("READY=1", env={}) is False
    assert sd_notify("READY=1", env={"NOTIFY_SOCKET": str(tmp_path / "missing")}) is False


def test_watchdog_interval_is_half_of_watchdogsec():
    from qorovul.runner import watchdog_interval
    assert watchdog_interval({"WATCHDOG_USEC": "600000000"}) == 300.0
    assert watchdog_interval({}) is None
    assert watchdog_interval({"WATCHDOG_USEC": "junk"}) is None


def test_run_forever_reports_ready_status_and_pets_watchdog(tmp_path):
    sent = []
    cfg = validate({"state_file": str(tmp_path / "s.json"), "interval": 60}, env={})
    runner = Runner(cfg, FakeNotifier(), checks=[FakeCheck("disk", BAD)], clock=Clock(),
                    notify=sent.append)
    stop = threading.Event()
    t = threading.Thread(target=runner.run_forever, args=(stop,), kwargs={"watchdog": 0.05})
    t.start()
    try:
        deadline = threading.Event()
        for _ in range(100):
            if sent.count("WATCHDOG=1") >= 3:
                break
            deadline.wait(0.05)
    finally:
        stop.set()
        t.join(5)
    assert sent[0] == "READY=1"
    assert sent[1] == "WATCHDOG=1\nSTATUS=1 key(s) tracked, 1 failing"
    # pinged repeatedly although the 60s interval never elapsed
    assert sent.count("WATCHDOG=1") >= 3
    assert sent[-1] == "STOPPING=1"


def test_cli_status_permission_denied(tmp_path, capsys, monkeypatch):
    from qorovul.state import StateError, StateStore as Store

    def boom(self, strict=False):
        raise StateError("cannot read state /var/lib/qorovul/state.json: Permission denied")
    monkeypatch.setattr(Store, "load", boom)
    cfg = tmp_path / "c.yml"
    cfg.write_text("interval: 30\n")
    assert main(["status", "-c", str(cfg)]) == 1
    err = capsys.readouterr().err
    assert "Permission denied" in err and "sudo qorovul status" in err
