"""The dedupe / cooldown / recovery state machine - the core of Qorovul."""

import json
import os
from datetime import datetime

import pytest

from qorovul.checks.base import CheckResult
from qorovul.state import (ALERT, ESCALATED, RECOVERED, REMINDER, AlertEngine, Policy,
                           QuietHours, StateStore)

H = 3600
T0 = datetime(2026, 3, 10, 12, 0).timestamp()  # local noon


def fail(key="disk:/var", sev="warning", msg="full"):
    return CheckResult(key, False, sev, msg)


def ok(key="disk:/var", msg="fine"):
    return CheckResult(key, True, "info", msg)


class Harness:
    """Drives the engine like the runner does, with a fake always-up notifier."""

    def __init__(self, **policy):
        policy.setdefault("recovery_cycles", 1)
        policy.setdefault("cooldown", 6 * H)
        self.engine = AlertEngine(Policy(**policy))
        self.deliver = True

    def cycle(self, now, *results, check="disk", complete=True):
        self.engine.observe(check, results, now, complete=complete)
        events = self.engine.pending(now)
        if self.deliver:
            self.engine.commit(events, now)
            return [(e.kind, e.key, e.severity) for e in events]
        return []

    def rec(self, key="disk:/var"):
        return self.engine.records[key]


# --------------------------------------------------------------------- basics

def test_new_failure_alerts_exactly_once():
    h = Harness()
    assert h.cycle(T0, fail()) == [(ALERT, "disk:/var", "warning")]
    for i in range(1, 100):
        assert h.cycle(T0 + 30 * i, fail()) == []


def test_ok_from_the_start_never_notifies():
    h = Harness()
    for i in range(10):
        assert h.cycle(T0 + 30 * i, ok()) == []
    assert h.rec()["status"] == "ok"


def test_keys_are_independent():
    h = Harness()
    assert h.cycle(T0, fail("disk:/"), fail("disk:/var")) == [
        (ALERT, "disk:/", "warning"), (ALERT, "disk:/var", "warning")]
    assert h.cycle(T0 + 30, fail("disk:/"), fail("disk:/var"), fail("disk:/home")) == [
        (ALERT, "disk:/home", "warning")]


# ------------------------------------------------------------------- cooldown

def test_reminder_only_after_cooldown():
    h = Harness(cooldown=6 * H)
    h.cycle(T0, fail())
    assert h.cycle(T0 + 6 * H - 1, fail()) == []
    assert h.cycle(T0 + 6 * H, fail()) == [(REMINDER, "disk:/var", "warning")]
    # Next reminder is measured from the reminder, not from the first alert.
    assert h.cycle(T0 + 6 * H + 30, fail()) == []
    assert h.cycle(T0 + 12 * H - 1, fail()) == []
    assert h.cycle(T0 + 12 * H, fail()) == [(REMINDER, "disk:/var", "warning")]


def test_per_check_cooldown_override():
    h = Harness(cooldown=6 * H, per_check={"disk": {"cooldown": 1 * H}})
    h.cycle(T0, fail())
    assert h.cycle(T0 + H, fail()) == [(REMINDER, "disk:/var", "warning")]


def test_zero_cooldown_reminds_every_cycle():
    h = Harness(cooldown=0)
    h.cycle(T0, fail())
    assert h.cycle(T0 + 30, fail()) == [(REMINDER, "disk:/var", "warning")]


# ------------------------------------------------------------------- severity

def test_escalation_bypasses_cooldown():
    h = Harness()
    h.cycle(T0, fail(sev="warning"))
    assert h.cycle(T0 + 60, fail(sev="critical")) == [(ESCALATED, "disk:/var", "critical")]
    assert h.cycle(T0 + 90, fail(sev="critical")) == []


def test_deescalation_is_silent_and_reescalation_alerts_again():
    h = Harness()
    h.cycle(T0, fail(sev="critical"))
    assert h.cycle(T0 + 30, fail(sev="warning")) == []
    # Still notified as critical, so going back to critical is not news.
    assert h.cycle(T0 + 60, fail(sev="critical")) == []
    assert h.rec()["notified_severity"] == "critical"


def test_below_min_severity_is_never_sent_and_recovers_silently():
    h = Harness(min_severity="critical")
    assert h.cycle(T0, fail(sev="warning")) == []
    assert h.cycle(T0 + 7 * H, fail(sev="warning")) == []
    assert h.cycle(T0 + 8 * H, ok()) == []
    assert h.rec()["status"] == "ok"


def test_suppressed_warning_that_escalates_is_sent_as_alert():
    h = Harness(min_severity="critical")
    h.cycle(T0, fail(sev="warning"))
    assert h.cycle(T0 + 30, fail(sev="critical")) == [(ALERT, "disk:/var", "critical")]


def test_info_severity_with_min_info():
    h = Harness(min_severity="info")
    assert h.cycle(T0, fail(sev="info")) == [(ALERT, "disk:/var", "info")]


# ------------------------------------------------------------------- recovery

def test_recovery_sent_once_after_alert():
    h = Harness()
    h.cycle(T0, fail())
    assert h.cycle(T0 + 300, ok()) == [(RECOVERED, "disk:/var", "warning")]
    assert h.cycle(T0 + 330, ok()) == []
    assert h.rec()["status"] == "ok"


def test_recovery_needs_consecutive_ok_cycles():
    h = Harness(recovery_cycles=3)
    h.cycle(T0, fail())
    assert h.cycle(T0 + 30, ok()) == []
    assert h.cycle(T0 + 60, ok()) == []
    assert h.rec()["status"] == "failing"
    assert h.cycle(T0 + 90, ok()) == [(RECOVERED, "disk:/var", "warning")]


def test_flapping_inside_recovery_window_produces_nothing():
    h = Harness(recovery_cycles=2)
    h.cycle(T0, fail())
    for i in range(1, 40):
        res = ok() if i % 2 else fail()
        assert h.cycle(T0 + 30 * i, res) == []
    assert h.rec()["status"] == "failing"
    assert h.rec()["since"] == T0  # still the same incident


def test_new_incident_after_recovery_alerts_again():
    h = Harness()
    h.cycle(T0, fail())
    h.cycle(T0 + 30, ok())
    assert h.cycle(T0 + 60, fail()) == [(ALERT, "disk:/var", "warning")]
    assert h.rec()["since"] == T0 + 60


def test_recovered_event_carries_incident_duration():
    h = Harness()
    h.cycle(T0, fail())
    h.engine.observe("disk", [ok(msg="/var is 40% full")], T0 + 2 * H)
    [ev] = h.engine.pending(T0 + 2 * H)
    assert ev.kind == RECOVERED
    assert ev.duration == 2 * H
    assert ev.message == "/var is 40% full"


def test_send_recovery_disabled_for_one_check():
    h = Harness(per_check={"disk": {"send_recovery": False}})
    h.cycle(T0, fail())
    assert h.cycle(T0 + 30, ok()) == []
    assert h.rec()["status"] == "ok"
    assert h.cycle(T0 + 60, fail()) == [(ALERT, "disk:/var", "warning")]


def test_send_recovery_disabled_globally():
    h = Harness(send_recovery=False)
    h.cycle(T0, fail())
    assert h.cycle(T0 + 30, ok()) == []


def test_recovery_ignores_min_severity_change():
    h = Harness()
    h.cycle(T0, fail(sev="warning"))
    h.engine.policy.min_severity = "critical"  # config changed after the alert
    assert h.cycle(T0 + 30, ok()) == [(RECOVERED, "disk:/var", "warning")]


# ----------------------------------------------------------- missing keys

def test_missing_key_after_complete_run_counts_as_cleared():
    h = Harness()
    h.cycle(T0, fail("ports:tcp/8080"), check="ports")
    assert h.cycle(T0 + 30, check="ports") == [(RECOVERED, "ports:tcp/8080", "warning")]


def test_missing_key_after_errored_run_is_not_cleared():
    h = Harness()
    h.cycle(T0, fail("ports:tcp/8080"), check="ports")
    err = CheckResult("ports:error", False, "warning", "boom")
    assert h.cycle(T0 + 30, err, check="ports", complete=False) == [
        (ALERT, "ports:error", "warning")]
    assert h.rec("ports:tcp/8080")["status"] == "failing"
    # The error key clears on the next good run.
    assert h.cycle(T0 + 60, fail("ports:tcp/8080"), check="ports") == [
        (RECOVERED, "ports:error", "warning")]


def test_missing_keys_of_other_checks_are_untouched():
    h = Harness()
    h.cycle(T0, fail("disk:/var"), check="disk")
    assert h.cycle(T0 + 30, check="ports") == []
    assert h.rec()["status"] == "failing"


# ------------------------------------------------------------- quiet hours

def quiet(**kw):
    return Harness(quiet_hours=QuietHours(True, "23:00", "07:00"), **kw)


def at(hh, mm=0, day=10):
    return datetime(2026, 3, day, hh, mm).timestamp()


@pytest.mark.parametrize("hhmm,expected", [
    ((22, 59), False), ((23, 0), True), ((2, 0), True), ((6, 59), True), ((7, 0), False)])
def test_quiet_hours_window_wraps_midnight(hhmm, expected):
    q = QuietHours(True, "23:00", "07:00")
    assert q.active(datetime(2026, 1, 1, *hhmm)) is expected


def test_quiet_hours_same_day_window():
    q = QuietHours(True, "12:00", "13:30")
    assert q.active(datetime(2026, 1, 1, 12, 0))
    assert not q.active(datetime(2026, 1, 1, 13, 30))
    assert not QuietHours(False, "00:00", "23:59").active(datetime(2026, 1, 1, 12))


def test_quiet_hours_defer_warning_until_end():
    h = quiet()
    assert h.cycle(at(23, 30), fail()) == []
    assert h.cycle(at(3, 0, day=11), fail()) == []
    assert h.cycle(at(7, 0, day=11), fail()) == [(ALERT, "disk:/var", "warning")]
    # since still reflects when it really started
    assert h.rec()["since"] == at(23, 30)


def test_quiet_hours_critical_always_sends():
    h = quiet()
    assert h.cycle(at(2), fail(sev="critical")) == [(ALERT, "disk:/var", "critical")]


def test_quiet_hours_problem_that_clears_overnight_is_never_sent():
    h = quiet()
    h.cycle(at(23, 30), fail())
    assert h.cycle(at(1, 0, day=11), ok()) == []
    assert h.cycle(at(8, 0, day=11), ok()) == []


def test_quiet_hours_defer_warning_recovery():
    h = quiet()
    h.cycle(at(22, 0), fail())  # alerted before quiet hours
    assert h.cycle(at(23, 30), ok()) == []
    assert h.rec()["pending_recovery"] is True
    assert h.cycle(at(7, 0, day=11), ok()) == [(RECOVERED, "disk:/var", "warning")]


def test_quiet_hours_critical_recovery_sends_immediately():
    h = quiet()
    h.cycle(at(23, 30), fail(sev="critical"))
    assert h.cycle(at(23, 45), ok()) == [(RECOVERED, "disk:/var", "critical")]


def test_quiet_hours_suppress_reminders():
    h = quiet(cooldown=1 * H)
    h.cycle(at(22, 0), fail())
    assert h.cycle(at(23, 30), fail()) == []
    assert h.cycle(at(7, 0, day=11), fail()) == [(REMINDER, "disk:/var", "warning")]


def test_refail_before_deferred_recovery_continues_incident():
    h = quiet()
    h.cycle(at(22, 0), fail())
    h.cycle(at(23, 30), ok())       # recovery deferred
    assert h.cycle(at(23, 45), fail()) == []  # no new ALERT
    rec = h.rec()
    assert rec["pending_recovery"] is False
    assert rec["since"] == at(22, 0)
    assert rec["notified_severity"] == "warning"
    # Cooldown (6h from 22:00) ended at 04:00, inside quiet hours: the reminder
    # is held until quiet hours end, then sent once.
    assert h.cycle(at(4, 30, day=11), fail()) == []
    assert h.cycle(at(7, 0, day=11), fail()) == [(REMINDER, "disk:/var", "warning")]
    assert h.cycle(at(7, 1, day=11), fail()) == []


# ------------------------------------------------------ delivery failures

def test_undelivered_alert_is_retried_next_cycle():
    h = Harness()
    h.deliver = False
    h.cycle(T0, fail())
    h.cycle(T0 + 30, fail())
    h.deliver = True
    assert h.cycle(T0 + 60, fail()) == [(ALERT, "disk:/var", "warning")]
    assert h.cycle(T0 + 90, fail()) == []


def test_undelivered_recovery_is_retried():
    h = Harness()
    h.cycle(T0, fail())
    h.deliver = False
    h.cycle(T0 + 30, ok())
    h.deliver = True
    assert h.cycle(T0 + 60, ok()) == [(RECOVERED, "disk:/var", "warning")]


def test_undelivered_escalation_is_retried():
    h = Harness()
    h.cycle(T0, fail())
    h.deliver = False
    h.cycle(T0 + 30, fail(sev="critical"))
    h.deliver = True
    assert h.cycle(T0 + 60, fail(sev="critical")) == [(ESCALATED, "disk:/var", "critical")]


def test_pending_does_not_mutate_state():
    h = Harness()
    h.engine.observe("disk", [fail()], T0)
    before = json.dumps(h.engine.records, sort_keys=True)
    h.engine.pending(T0)
    h.engine.pending(T0 + 10 * H)
    assert json.dumps(h.engine.records, sort_keys=True) == before


def test_partial_commit_only_marks_delivered_events():
    h = Harness()
    h.engine.observe("disk", [fail("disk:/a"), fail("disk:/b")], T0)
    events = h.engine.pending(T0)
    h.engine.commit(events[:1], T0)
    assert [e.key for e in h.engine.pending(T0 + 30)] == ["disk:/b"]


def test_event_ordering_most_severe_first_recoveries_last():
    h = Harness()
    h.cycle(T0, fail("disk:/r"))
    h.engine.observe("disk", [ok("disk:/r"), fail("disk:/w"), fail("disk:/c", sev="critical")],
                     T0 + 30)
    assert [(e.kind, e.key) for e in h.engine.pending(T0 + 30)] == [
        (ALERT, "disk:/c"), (ALERT, "disk:/w"), (RECOVERED, "disk:/r")]


# ---------------------------------------------------------- persistence

def test_restart_does_not_respam(tmp_path):
    path = str(tmp_path / "state.json")
    h = Harness()
    h.cycle(T0, fail())
    StateStore(path).save(h.engine.records)

    # "restart": fresh engine from disk
    engine = AlertEngine(Policy(recovery_cycles=1), StateStore(path).load())
    engine.observe("disk", [fail()], T0 + 60)
    assert engine.pending(T0 + 60) == []
    engine.observe("disk", [fail()], T0 + 6 * H)
    assert [e.kind for e in engine.pending(T0 + 6 * H)] == [REMINDER]


def test_restart_preserves_pending_recovery(tmp_path):
    path = str(tmp_path / "state.json")
    h = Harness()
    h.cycle(T0, fail())
    h.deliver = False
    h.cycle(T0 + 30, ok())
    StateStore(path).save(h.engine.records)
    engine = AlertEngine(Policy(recovery_cycles=1), StateStore(path).load())
    assert [e.kind for e in engine.pending(T0 + 60)] == [RECOVERED]


def test_state_file_roundtrip_and_format(tmp_path):
    path = str(tmp_path / "sub" / "state.json")  # directory is created
    store = StateStore(path)
    assert store.load() == {}
    h = Harness()
    h.cycle(T0, fail())
    assert store.save(h.engine.records)
    with open(path) as fh:
        data = json.load(fh)
    assert data["version"] == 1
    assert data["keys"]["disk:/var"]["status"] == "failing"
    assert StateStore(path).load() == h.engine.records


def test_corrupt_state_file_is_set_aside(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json")
    assert StateStore(str(path)).load() == {}
    assert (tmp_path / "state.json.corrupt").read_text() == "{not json"


def test_unexpected_state_shape_is_ignored(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("[1, 2, 3]")
    assert StateStore(str(path)).load() == {}


def test_save_failure_is_reported_not_raised(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    store = StateStore(str(blocker / "state.json"))  # parent is a file
    assert store.save({"a": {}}) is False


def test_save_skips_unchanged_payload(tmp_path, monkeypatch):
    store = StateStore(str(tmp_path / "state.json"))
    assert store.save({"k": {"status": "ok"}})
    calls = []
    monkeypatch.setattr(os, "replace", lambda *a: calls.append(a))
    assert store.save({"k": {"status": "ok"}})
    assert calls == []


def test_save_leaves_no_temp_files(tmp_path):
    store = StateStore(str(tmp_path / "state.json"))
    store.save({"k": {"status": "ok"}})
    store.save({"k": {"status": "failing"}})
    assert sorted(p.name for p in tmp_path.iterdir()) == ["state.json"]


# ---------------------------------------------------------- housekeeping

def test_prune_drops_stale_ok_records_only():
    h = Harness()
    h.cycle(T0, ok("disk:/old"), fail("disk:/bad"))
    h.engine.prune(T0 + 8 * 86400)
    assert list(h.engine.records) == ["disk:/bad"]


def test_prune_keeps_pending_recoveries():
    h = Harness()
    h.cycle(T0, fail())
    h.deliver = False
    h.cycle(T0 + 30, ok())
    h.engine.prune(T0 + 30 * 86400)
    assert "disk:/var" in h.engine.records


def test_prune_drops_records_of_disabled_checks():
    h = Harness()
    h.cycle(T0, fail("disk:/var"), check="disk")
    h.cycle(T0, fail("ports:tcp/1"), check="ports")
    h.engine.prune(T0, active_checks=["ports"])
    assert list(h.engine.records) == ["ports:tcp/1"]


def test_policy_from_config():
    from qorovul.config import validate
    cfg = validate({"alerts": {"cooldown": "1h", "min_severity": "critical",
                               "quiet_hours": {"enabled": True}},
                    "checks": {"ssh": {"send_recovery": False, "cooldown": "5m"}}}, env={})
    p = Policy.from_config(cfg)
    assert p.cooldown == 3600 and p.min_severity == "critical"
    assert p.cooldown_for("ssh") == 300 and p.cooldown_for("disk") == 3600
    assert p.recovery_enabled("ssh") is False and p.recovery_enabled("disk") is True
    assert p.quiet_hours.enabled


# ---------------------------------------------------- confirm_cycles

def confirm(n, **kw):
    return Harness(per_check={"service": {"confirm_cycles": n}}, **kw)


def test_confirm_cycles_delays_first_alert():
    h = confirm(2)
    assert h.cycle(T0, fail("service:nginx"), check="service") == []
    assert h.cycle(T0 + 30, fail("service:nginx"), check="service") == [
        (ALERT, "service:nginx", "warning")]
    assert h.rec("service:nginx")["since"] == T0  # incident started at first sighting
    assert h.cycle(T0 + 60, fail("service:nginx"), check="service") == []


def test_confirm_cycles_blip_is_never_reported():
    # e.g. a unit caught "activating" during a routine restart, or at boot
    h = confirm(2)
    assert h.cycle(T0, fail("service:nginx"), check="service") == []
    assert h.cycle(T0 + 30, ok("service:nginx"), check="service") == []
    assert h.cycle(T0 + 60, ok("service:nginx"), check="service") == []
    assert h.rec("service:nginx")["status"] == "ok"


def test_confirm_cycles_needs_consecutive_failures():
    h = confirm(3, recovery_cycles=2)
    seq = [fail, fail, ok, fail, fail]
    for i, f in enumerate(seq):
        assert h.cycle(T0 + 30 * i, f("service:x"), check="service") == []
    assert h.cycle(T0 + 150, fail("service:x"), check="service") == [
        (ALERT, "service:x", "warning")]


def test_confirm_cycles_only_applies_to_its_check():
    h = confirm(5)
    assert h.cycle(T0, fail("disk:/"), check="disk") == [(ALERT, "disk:/", "warning")]


def test_confirm_cycles_does_not_delay_escalation_or_recovery():
    h = confirm(2)
    h.cycle(T0, fail("service:x"), check="service")
    h.cycle(T0 + 30, fail("service:x"), check="service")
    assert h.cycle(T0 + 60, fail("service:x", sev="critical"), check="service") == [
        (ESCALATED, "service:x", "critical")]
    assert h.cycle(T0 + 90, ok("service:x"), check="service") == [
        (RECOVERED, "service:x", "critical")]


def test_records_from_older_versions_without_fail_streak_still_work():
    h = confirm(3)
    h.engine.observe("service", [fail("service:x")], T0)
    del h.engine.records["service:x"]["fail_streak"]  # state.json written by 0.1.0
    assert [e.kind for e in h.engine.pending(T0)] == [ALERT]


def test_policy_confirm_defaults_from_config():
    from qorovul.config import validate
    p = Policy.from_config(validate({"checks": {"ports": {"confirm_cycles": 4}}}, env={}))
    assert (p.confirm_for("service"), p.confirm_for("disk"), p.confirm_for("ports")) == (2, 1, 4)
    assert p.confirm_for("memory") == 3


# ---------------------------------------------------- strict loading

def test_unreadable_state_is_not_renamed(tmp_path, monkeypatch):
    import builtins
    path = tmp_path / "state.json"
    path.write_text('{"version": 1, "keys": {}}')
    real_open = builtins.open

    def deny(file, *a, **k):
        if str(file) == str(path):
            raise PermissionError(13, "Permission denied")
        return real_open(file, *a, **k)
    monkeypatch.setattr(builtins, "open", deny)
    assert StateStore(str(path)).load() == {}
    assert path.exists() and not (tmp_path / "state.json.corrupt").exists()
    from qorovul.state import StateError
    with pytest.raises(StateError, match="Permission denied"):
        StateStore(str(path)).load(strict=True)


def test_strict_load_reports_corruption_without_touching_the_file(tmp_path):
    from qorovul.state import StateError
    path = tmp_path / "state.json"
    path.write_text("{oops")
    with pytest.raises(StateError, match="not valid JSON"):
        StateStore(str(path)).load(strict=True)
    assert path.read_text() == "{oops"
    path.write_text("[]")
    with pytest.raises(StateError, match="unexpected format"):
        StateStore(str(path)).load(strict=True)
