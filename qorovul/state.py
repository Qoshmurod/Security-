"""Persistent alert state and the dedupe / cooldown / recovery state machine.

Every check result carries a stable ``key``.  For each key we keep one record
in ``state.json``::

    status            "failing" | "ok"
    severity          current severity of the condition
    message           latest message (failing or ok)
    since             when the current incident started (epoch seconds)
    ok_streak         consecutive ok observations while still "failing"
    fail_streak       consecutive failing observations (for confirm_cycles)
    last_notified     when we last told the user about this incident
    notified_severity severity of that notification (None = not yet notified)
    pending_recovery  incident cleared but RECOVERED not delivered yet

Two-phase design: ``AlertEngine.observe()`` only records what the checks saw.
``AlertEngine.pending()`` derives which notifications are due *from the
stored record*, and ``AlertEngine.commit()`` marks them delivered once Telegram
accepted them.  An alert that could not be delivered (Telegram down, quiet
hours, ...) is therefore simply still due on the next cycle - no separate
retry queue exists, and a restart cannot lose or duplicate one.

Rules:
  * new failure            -> ALERT once (if severity >= min and not quiet),
                              after ``confirm_cycles`` consecutive failing runs
  * still failing          -> nothing, until ``cooldown`` since last notice -> REMINDER
  * severity went up       -> ESCALATED immediately (ignores cooldown)
  * ok for recovery_cycles -> RECOVERED, but only if the user was alerted
  * quiet hours            -> only critical is delivered; the rest is deferred
  * fails again before a deferred RECOVERED went out -> same incident continues
"""

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional

from .checks.base import CheckResult, severity_rank

log = logging.getLogger(__name__)

STATE_VERSION = 1
PRUNE_OK_AFTER = 7 * 86400
LAST_SEEN_RESOLUTION = 3600  # only rewrite last_seen hourly to avoid needless writes

ALERT = "alert"
ESCALATED = "escalated"
REMINDER = "reminder"
RECOVERED = "recovered"


@dataclass
class Event:
    """A notification that is due."""

    key: str
    kind: str
    severity: str
    message: str
    since: Optional[float]
    at: float
    duration: Optional[float] = None


class QuietHours:
    """Local-time window (may wrap midnight) during which only critical is sent."""

    def __init__(self, enabled: bool, start: str, end: str) -> None:
        self.enabled = enabled
        self.start = self._minutes(start)
        self.end = self._minutes(end)

    @staticmethod
    def _minutes(hhmm: str) -> int:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)

    def active(self, dt: datetime) -> bool:
        if not self.enabled:
            return False
        now = dt.hour * 60 + dt.minute
        if self.start < self.end:
            return self.start <= now < self.end
        return now >= self.start or now < self.end


class Policy:
    """Alerting rules derived from the ``alerts`` config section."""

    def __init__(self, min_severity: str = "warning", cooldown: float = 6 * 3600,
                 recovery_cycles: int = 1, send_recovery: bool = True,
                 quiet_hours: Optional[QuietHours] = None,
                 per_check: Optional[Dict[str, Dict[str, Any]]] = None,
                 localtime: Callable[[float], datetime] = datetime.fromtimestamp) -> None:
        self.min_severity = min_severity
        self.cooldown = cooldown
        self.recovery_cycles = recovery_cycles
        self.send_recovery = send_recovery
        self.quiet_hours = quiet_hours or QuietHours(False, "00:00", "00:00")
        self.per_check = per_check or {}
        self.localtime = localtime

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "Policy":
        a = cfg["alerts"]
        q = a["quiet_hours"]
        return cls(
            min_severity=a["min_severity"], cooldown=a["cooldown"],
            recovery_cycles=a["recovery_cycles"], send_recovery=a["send_recovery"],
            quiet_hours=QuietHours(q["enabled"], q["start"], q["end"]),
            per_check={name: {"cooldown": c.get("cooldown"),
                              "send_recovery": c.get("send_recovery"),
                              "confirm_cycles": c.get("confirm_cycles")}
                       for name, c in cfg["checks"].items()},
        )

    def _override(self, check: str, field: str, default: Any) -> Any:
        val = self.per_check.get(check, {}).get(field)
        return default if val is None else val

    def cooldown_for(self, check: str) -> float:
        return self._override(check, "cooldown", self.cooldown)

    def recovery_enabled(self, check: str) -> bool:
        return self._override(check, "send_recovery", self.send_recovery)

    def confirm_for(self, check: str) -> int:
        """Consecutive failing runs required before the first ALERT."""
        return self._override(check, "confirm_cycles", 1)

    def held_by_quiet_hours(self, severity: str, now: float) -> bool:
        return severity != "critical" and self.quiet_hours.active(self.localtime(now))

    def deliverable(self, severity: str, now: float) -> bool:
        if severity_rank(severity) < severity_rank(self.min_severity):
            return False
        return not self.held_by_quiet_hours(severity, now)


class StateError(Exception):
    """The state file exists but cannot be used."""


class StateStore:
    """JSON file persistence with atomic replace."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._last_written = None  # type: Optional[str]

    def load(self, strict: bool = False) -> Dict[str, Dict[str, Any]]:
        """Read the state file.

        The daemon must keep monitoring whatever happens to this file, so by
        default problems are logged and an empty state is returned.  With
        ``strict`` (used by ``qorovul status``) they raise ``StateError``.
        """
        try:
            with open(self.path) as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return {}
        except OSError as exc:
            # Unreadable (permissions, I/O error): leave the file alone.
            if strict:
                raise StateError("cannot read state %s: %s" % (self.path, exc.strerror or exc))
            log.error("cannot read state %s (%s); starting with empty state", self.path, exc)
            return {}
        except ValueError as exc:
            if strict:
                raise StateError("state %s is not valid JSON: %s" % (self.path, exc))
            backup = self.path + ".corrupt"
            log.error("state %s is corrupt (%s); starting fresh, old file kept as %s",
                      self.path, exc, backup)
            try:
                os.replace(self.path, backup)
            except OSError:
                pass
            return {}
        if not isinstance(data, dict) or not isinstance(data.get("keys"), dict):
            if strict:
                raise StateError("state %s has an unexpected format" % self.path)
            log.error("state %s has unexpected format; starting fresh", self.path)
            return {}
        return data["keys"]

    def save(self, records: Dict[str, Dict[str, Any]]) -> bool:
        """Write state if it changed.  Returns False (and logs) on failure."""
        payload = json.dumps({"version": STATE_VERSION, "keys": records},
                             indent=1, sort_keys=True)
        if payload == self._last_written:
            return True
        directory = os.path.dirname(self.path) or "."
        tmp = None
        try:
            os.makedirs(directory, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".state.", dir=directory)
            with os.fdopen(fd, "w") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
            tmp = None
        except OSError as exc:
            # E.g. the disk we are alerting about is full.  Keep running on the
            # in-memory state; dedupe still works until the next restart.
            log.error("cannot write state %s: %s", self.path, exc)
            return False
        finally:
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        self._last_written = payload
        return True


class AlertEngine:
    """Applies check results to stored records and decides what to send."""

    def __init__(self, policy: Policy, records: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self.policy = policy
        self.records = records if records is not None else {}

    # ------------------------------------------------------------------ observe

    def observe(self, check: str, results: Iterable[CheckResult], now: float,
                complete: bool = True,
                cleared_message: Callable[[str], str] = lambda key: "condition no longer present",
                ) -> None:
        """Record one run of ``check``.

        ``complete`` means the check ran normally; previously failing keys of
        this check that it did not report are then treated as cleared.
        """
        seen = set()
        for r in results:
            seen.add(r.key)
            if r.ok:
                self._observe_ok(check, r.key, r.message, now)
            else:
                self._observe_fail(check, r, now)
        if complete:
            for key, rec in list(self.records.items()):
                if rec.get("check") == check and key not in seen and rec["status"] == "failing":
                    self._observe_ok(check, key, cleared_message(key), now)

    def _new_record(self, check: str) -> Dict[str, Any]:
        return {
            "check": check, "status": "ok", "severity": "info", "message": "",
            "since": None, "last_seen": None, "ok_streak": 0, "fail_streak": 0,
            "last_notified": None, "notified_severity": None, "notify_count": 0,
            "pending_recovery": False, "last_event": None,
        }

    def _touch(self, rec: Dict[str, Any], now: float) -> None:
        if rec["last_seen"] is None or now - rec["last_seen"] >= LAST_SEEN_RESOLUTION:
            rec["last_seen"] = now

    def _observe_fail(self, check: str, r: CheckResult, now: float) -> None:
        rec = self.records.get(r.key)
        if rec is None:
            rec = self.records[r.key] = self._new_record(check)
        if rec["status"] != "failing":
            if rec["pending_recovery"]:
                # It came back before we managed to announce the recovery: from
                # the user's point of view the incident never ended.
                rec["pending_recovery"] = False
            else:
                rec["since"] = now
                rec["last_notified"] = None
                rec["notified_severity"] = None
                rec["notify_count"] = 0
            rec["status"] = "failing"
        rec["check"] = check
        rec["severity"] = r.severity
        rec["message"] = r.message
        rec["ok_streak"] = 0
        rec["fail_streak"] = rec.get("fail_streak", 0) + 1
        rec["last_seen"] = now

    def _observe_ok(self, check: str, key: str, message: str, now: float) -> None:
        rec = self.records.get(key)
        if rec is None:
            rec = self.records[key] = self._new_record(check)
            rec["message"] = message
            rec["last_seen"] = now
            return
        rec["check"] = check
        rec["fail_streak"] = 0
        if rec["status"] == "failing":
            rec["ok_streak"] += 1
            if rec["ok_streak"] < self.policy.recovery_cycles:
                self._touch(rec, now)
                return  # not convinced yet; keep the incident open
            rec["status"] = "ok"
            rec["ok_streak"] = 0
            rec["recovered_at"] = now
            if rec["notified_severity"] is not None and self.policy.recovery_enabled(check):
                rec["pending_recovery"] = True
            else:
                # User never heard about it (or does not want recoveries).
                rec["last_notified"] = None
                rec["notified_severity"] = None
                rec["notify_count"] = 0
        rec["message"] = message
        self._touch(rec, now)

    # ------------------------------------------------------------------ decide

    def pending(self, now: float) -> List[Event]:
        """Notifications that are due right now (pure: does not mutate state)."""
        events = []
        for key in sorted(self.records):
            ev = self._due(key, self.records[key], now)
            if ev is not None:
                events.append(ev)
        # Most severe first, recoveries last.
        events.sort(key=lambda e: (e.kind == RECOVERED, -severity_rank(e.severity), e.key))
        return events

    def _due(self, key: str, rec: Dict[str, Any], now: float) -> Optional[Event]:
        p = self.policy
        if rec["status"] == "failing":
            sev = rec["severity"]
            if not p.deliverable(sev, now):
                return None
            notified = rec["notified_severity"]
            if notified is None:
                # Records written before fail_streak existed count as confirmed.
                if rec.get("fail_streak", 1 << 30) < p.confirm_for(rec["check"]):
                    return None  # seen failing, but not for long enough yet
                kind = ALERT
            elif severity_rank(sev) > severity_rank(notified):
                kind = ESCALATED
            elif now - rec["last_notified"] >= p.cooldown_for(rec["check"]):
                kind = REMINDER
            else:
                return None
            return Event(key, kind, sev, rec["message"], rec["since"], now,
                         duration=now - rec["since"] if rec["since"] else None)
        if rec.get("pending_recovery"):
            # The user saw the alert, so always tell them it cleared - only
            # quiet hours may delay it (min_severity may have changed since).
            sev = rec["notified_severity"] or rec["severity"]
            if p.held_by_quiet_hours(sev, now):
                return None
            end = rec.get("recovered_at") or now
            return Event(key, RECOVERED, sev, rec["message"], rec["since"], now,
                         duration=end - rec["since"] if rec["since"] else None)
        return None

    # ------------------------------------------------------------------ commit

    def commit(self, events: Iterable[Event], now: float) -> None:
        """Mark events as delivered."""
        for ev in events:
            rec = self.records.get(ev.key)
            if rec is None:
                continue
            if ev.kind == RECOVERED:
                rec["pending_recovery"] = False
                rec["last_notified"] = None
                rec["notified_severity"] = None
                rec["notify_count"] = 0
            else:
                rec["last_notified"] = now
                rec["notified_severity"] = ev.severity
                rec["notify_count"] = rec.get("notify_count", 0) + 1
            rec["last_event"] = {"kind": ev.kind, "at": now, "severity": ev.severity,
                                 "message": ev.message}

    # ------------------------------------------------------------------ housekeeping

    def prune(self, now: float, active_checks: Optional[Iterable[str]] = None) -> None:
        """Drop stale ok records and records of checks that are no longer enabled."""
        active = set(active_checks) if active_checks is not None else None
        for key, rec in list(self.records.items()):
            if active is not None and rec.get("check") not in active:
                del self.records[key]
                continue
            if rec["status"] == "ok" and not rec.get("pending_recovery") \
                    and now - (rec.get("last_seen") or 0) > PRUNE_OK_AFTER:
                del self.records[key]
