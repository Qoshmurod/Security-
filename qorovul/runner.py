"""Scheduler loop: run due checks, update state, dispatch alerts."""

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .checks import Check, CheckResult, build_checks
from .state import AlertEngine, Event, Policy, StateStore

log = logging.getLogger(__name__)


def run_check(check: Check, last_errors: Optional[Dict[str, str]] = None
              ) -> Tuple[List[CheckResult], bool]:
    """Run one check, converting exceptions into a failing ``<name>:error`` result.

    Returns (results, complete).  ``complete`` is False when the check raised,
    so the engine does not mistake "could not look" for "all clear".
    ``last_errors`` (check name -> message) keeps a persistent error from
    writing a traceback to the journal every cycle.
    """
    try:
        results = list(check.run())
    except Exception as exc:  # a broken check must never kill the watchdog
        msg = "%s check could not run: %s" % (check.name, exc)
        if last_errors is None or last_errors.get(check.name) != msg:
            log.exception("check %s failed", check.name)
        else:
            log.debug("check %s still failing: %s", check.name, exc)
        if last_errors is not None:
            last_errors[check.name] = msg
        return [CheckResult("%s:error" % check.name, False, "warning", msg)], False
    if last_errors is not None and last_errors.pop(check.name, None):
        log.info("check %s is running normally again", check.name)
    return results, True


class Runner:
    def __init__(self, config: Dict[str, Any], notifier: Any,
                 checks: Optional[Sequence[Check]] = None,
                 store: Optional[StateStore] = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.config = config
        self.notifier = notifier
        self.checks = list(checks) if checks is not None else build_checks(config)
        self.store = store or StateStore(config["state_file"])
        self.clock = clock
        self.engine = AlertEngine(Policy.from_config(config), self.store.load())
        self.engine.prune(clock(), active_checks=[c.name for c in self.checks])
        self.last_run = {}  # type: Dict[str, float]
        self.last_errors = {}  # type: Dict[str, str]

    def _interval(self, check: Check) -> float:
        section = self.config["checks"].get(check.name, {})
        return section.get("interval") or self.config["interval"]

    def due_checks(self, now: float) -> List[Check]:
        due = []
        for check in self.checks:
            last = self.last_run.get(check.name)
            # 1s slack so a 30s interval does not drift to every 60s.
            if last is None or now - last >= self._interval(check) - 1:
                due.append(check)
        return due

    @staticmethod
    def _cleared(check: Check) -> Callable[[str], str]:
        def message(key: str) -> str:
            if key == "%s:error" % check.name:
                return "%s check is running normally again" % check.name
            return check.cleared_message(key)
        return message

    def run_cycle(self) -> List[Event]:
        """One iteration. Returns the events delivered."""
        now = self.clock()
        for check in self.due_checks(now):
            results, complete = run_check(check, self.last_errors)
            self.last_run[check.name] = now
            self.engine.observe(check.name, results, now, complete=complete,
                                cleared_message=self._cleared(check))
        events = self.engine.pending(now)
        delivered = []  # type: List[Event]
        if events:
            delivered = self.notifier.send_events(events, self.config["hostname"])
            self.engine.commit(delivered, now)
            if len(delivered) < len(events):
                log.warning("%d notification(s) not delivered; will retry next cycle",
                            len(events) - len(delivered))
            for ev in delivered:
                log.info("sent %s %s [%s] %s", ev.kind, ev.key, ev.severity, ev.message)
        self.engine.prune(now)
        self.store.save(self.engine.records)
        return delivered

    def run_forever(self, stop: Optional[threading.Event] = None) -> None:
        stop = stop or threading.Event()
        tick = min([self._interval(c) for c in self.checks] or [self.config["interval"]])
        tick = min(tick, self.config["interval"])
        log.info("qorovul started: %d check(s) [%s], interval %ss",
                 len(self.checks), ", ".join(c.name for c in self.checks), int(tick))
        while not stop.is_set():
            started = time.monotonic()
            try:
                self.run_cycle()
            except Exception:  # pragma: no cover - last-resort guard
                log.exception("cycle failed")
            elapsed = time.monotonic() - started
            stop.wait(max(1.0, tick - elapsed))
        self.store.save(self.engine.records)
        log.info("qorovul stopped")
