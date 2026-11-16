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
    assert "1 failing" in out and "disk:/" in out and "FAILING" in out and "alert" in out
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
    monkeypatch.setattr(cli, "_oneshot_checks", lambda cfg: [FakeCheck("disk", result)])
    p = tmp_path / "c.yml"
    p.write_text("state_file: %s\n" % (tmp_path / "s.json"))
    assert main(["test", "-c", str(p)]) == expected
    out = capsys.readouterr().out
    assert "disk:/" in out
    assert "Qorovul test message" in N.texts[-1]
    assert "<b>" not in N.texts[-1].split("\n", 2)[-1]  # check messages are escaped
    assert not (tmp_path / "s.json").exists()  # test never touches state


def test_oneshot_checks_disable_memory_sustain():
    from qorovul.__main__ import _oneshot_checks
    cfg = validate({"checks": {n: {"enabled": n == "memory"}
                               for n in ("disk", "memory", "service", "ssh", "ssl", "ports")}},
                   env={})
    [mem] = _oneshot_checks(cfg)
    assert mem.config["sustained_cycles"] == 1
    assert cfg["checks"]["memory"]["sustained_cycles"] == 3  # original untouched


def test_persistent_error_logs_traceback_once(caplog):
    import logging
    errors = {}
    check = FakeCheck("ssh", RuntimeError("same"))
    with caplog.at_level(logging.DEBUG, logger="qorovul.runner"):
        for _ in range(3):
            run_check(check, errors)
    assert sum(1 for r in caplog.records if r.exc_info) == 1
    check.script = [[]]
    with caplog.at_level(logging.INFO, logger="qorovul.runner"):
        run_check(check, errors)
    assert "running normally again" in caplog.text and errors == {}
