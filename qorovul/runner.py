"""Scheduler loop: run due checks, update state, dispatch alerts."""

import logging
import os
import socket
import threading
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .checks import Check, CheckResult, build_checks
from .i18n import EN, Translator, get_translator
from .state import AlertEngine, Event, Policy, StateStore

log = logging.getLogger(__name__)

# After a failed delivery wait this long before trying again, doubling up to
# the maximum.  Pending alerts are never dropped, only delayed.
RETRY_BACKOFF_START = 30.0
RETRY_BACKOFF_MAX = 300.0


def sd_notify(message: str, env: Optional[Mapping[str, str]] = None) -> bool:
    """Send a notification to systemd (READY=1, WATCHDOG=1, STATUS=...).

    A no-op outside systemd.  Implemented directly on the notify socket so no
    extra dependency is needed.
    """
    addr = (os.environ if env is None else env).get("NOTIFY_SOCKET")
    if not addr:
        return False
    if addr.startswith("@"):  # abstract namespace socket
        addr = "\0" + addr[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(addr)
            sock.sendall(message.encode("utf-8"))
        return True
    except OSError as exc:
        log.debug("sd_notify failed: %s", exc)
        return False


def watchdog_interval(env: Optional[Mapping[str, str]] = None) -> Optional[float]:
    """Seconds between WATCHDOG=1 pings (half of WatchdogSec), or None."""
    env = os.environ if env is None else env
    try:
        usec = int(env.get("WATCHDOG_USEC", "0"))
    except ValueError:
        return None
    return usec / 2e6 if usec > 0 else None


def _http_get(url: str, timeout: float) -> int:
    import requests
    return requests.get(url, timeout=timeout, headers={"User-Agent": "qorovul"}).status_code


def run_check(check: Check, last_errors: Optional[Dict[str, str]] = None,
              tr: Translator = EN) -> Tuple[List[CheckResult], bool]:
    """Run one check, converting exceptions into a failing ``<name>:error`` result.

    Returns (results, complete).  ``complete`` is False when the check raised,
    so the engine does not mistake "could not look" for "all clear".
    ``last_errors`` (check name -> message) keeps a persistent error from
    writing a traceback to the journal every cycle.
    """
    try:
        results = list(check.run())
    except Exception as exc:  # a broken check must never kill the watchdog
        msg = tr("check.error", check=check.name, error=exc)
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
                 clock: Callable[[], float] = time.time,
                 monotonic: Optional[Callable[[], float]] = None,
                 http_get: Callable[[str, float], int] = _http_get,
                 notify: Callable[[str], bool] = sd_notify) -> None:
        self.config = config
        self.notifier = notifier
        self.tr = get_translator(config.get("language", "en"))
        self.checks = list(checks) if checks is not None else build_checks(config)
        self.store = store or StateStore(config["state_file"])
        # Wall clock for timestamps shown to people; monotonic clock for
        # scheduling, so an NTP step or a manual date change cannot stall checks.
        self.clock = clock
        self.monotonic = monotonic or (time.monotonic if clock is time.time else clock)
        self.http_get = http_get
        self.notify = notify
        self.engine = AlertEngine(Policy.from_config(config), self.store.load())
        self.engine.prune(clock(), active_checks=[c.name for c in self.checks])
        self.last_run = {}  # type: Dict[str, float]
        self.last_errors = {}  # type: Dict[str, str]
        self.retry_at = 0.0
        self.retry_backoff = RETRY_BACKOFF_START
        self.last_heartbeat = None  # type: Optional[float]
        self.heartbeat_failing = False

    def _interval(self, check: Check) -> float:
        section = self.config["checks"].get(check.name, {})
        return section.get("interval") or self.config["interval"]

    def due_checks(self, mono: float) -> List[Check]:
        due = []
        for check in self.checks:
            last = self.last_run.get(check.name)
            # 1s slack so a 30s interval does not drift to every 60s.
            if last is None or mono - last >= self._interval(check) - 1:
                due.append(check)
        return due

    @staticmethod
    def _cleared(check: Check, tr: Translator = EN) -> Callable[[str], str]:
        def message(key: str) -> str:
            if key == "%s:error" % check.name:
                return tr("check.recovered", check=check.name)
            return check.cleared_message(key)
        return message

    def run_cycle(self) -> List[Event]:
        """One iteration. Returns the events delivered."""
        now = self.clock()
        mono = self.monotonic()
        for check in self.due_checks(mono):
            results, complete = run_check(check, self.last_errors, self.tr)
            self.last_run[check.name] = mono
            self.engine.observe(check.name, results, now, complete=complete,
                                cleared_message=self._cleared(check, self.tr))
        delivered = self._dispatch(now, mono)
        self.engine.prune(now)
        self.store.save(self.engine.records)
        self._heartbeat(mono)
        return delivered

    def _dispatch(self, now: float, mono: float) -> List[Event]:
        events = self.engine.pending(now)
        if not events:
            return []
        if mono < self.retry_at:
            log.debug("%d notification(s) waiting for delivery retry", len(events))
            return []
        delivered = self.notifier.send_events(events, self.config["hostname"])
        self.engine.commit(delivered, now)
        for ev in delivered:
            log.info("sent %s %s [%s] %s", ev.kind, ev.key, ev.severity, ev.message)
        if len(delivered) < len(events):
            log.warning("%d notification(s) not delivered; retrying in %ds",
                        len(events) - len(delivered), int(self.retry_backoff))
            self.retry_at = mono + self.retry_backoff
            self.retry_backoff = min(self.retry_backoff * 2, RETRY_BACKOFF_MAX)
        else:
            self.retry_at = 0.0
            self.retry_backoff = RETRY_BACKOFF_START
        return delivered

    def _heartbeat(self, mono: float) -> None:
        """Ping the optional dead-man's-switch URL.

        The ping means "this host and Qorovul are alive", independent of what
        the checks found; the external service alerts when pings *stop*.
        """
        hb = self.config.get("heartbeat") or {}
        url = hb.get("url")
        if not url:
            return
        if self.last_heartbeat is not None and mono - self.last_heartbeat < hb["interval"] - 1:
            return
        self.last_heartbeat = mono
        try:
            status = self.http_get(url, hb["timeout"])
            problem = None if 200 <= status < 300 else "HTTP %d" % status
        except Exception as exc:
            problem = type(exc).__name__
        if problem and not self.heartbeat_failing:
            log.warning("heartbeat ping failed: %s", problem)
        elif not problem and self.heartbeat_failing:
            log.info("heartbeat ping is working again")
        self.heartbeat_failing = bool(problem)

    def status_line(self) -> str:
        failing = sum(1 for r in self.engine.records.values() if r["status"] == "failing")
        return "%d key(s) tracked, %d failing" % (len(self.engine.records), failing)

    def run_forever(self, stop: Optional[threading.Event] = None,
                    watchdog: Optional[float] = None) -> None:
        stop = stop or threading.Event()
        watchdog = watchdog_interval() if watchdog is None else watchdog
        tick = min([self._interval(c) for c in self.checks] + [self.config["interval"]])
        log.info("qorovul started: %d check(s) [%s], interval %ss",
                 len(self.checks), ", ".join(c.name for c in self.checks), int(tick))
        self.notify("READY=1")
        while not stop.is_set():
            started = time.monotonic()
            try:
                self.run_cycle()
            except Exception:  # pragma: no cover - last-resort guard
                log.exception("cycle failed")
            self.notify("WATCHDOG=1\nSTATUS=%s" % self.status_line())
            # Sleep until the next tick, but keep petting the systemd watchdog
            # even when the configured interval is longer than its timeout.
            deadline = max(started + tick, time.monotonic() + 1.0)
            while not stop.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                stop.wait(min(remaining, watchdog) if watchdog else remaining)
                if watchdog:
                    self.notify("WATCHDOG=1")
        self.notify("STOPPING=1")
        self.store.save(self.engine.records)
        log.info("qorovul stopped")
