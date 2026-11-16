"""Telegram delivery and message formatting."""

import html
import logging
import time
from datetime import datetime
from typing import Any, Callable, List, Optional, Sequence

from .state import ALERT, ESCALATED, RECOVERED, REMINDER, Event

log = logging.getLogger(__name__)

MAX_MESSAGE = 4000  # Telegram's hard limit is 4096; leave headroom for markup
ICONS = {"critical": "\U0001F534", "warning": "\U0001F7E0", "info": "\U0001F535"}
ICON_RECOVERED = "✅"
ICON_REMINDER = "\U0001F501"
ICON_HOST = "\U0001F6E1"


def human_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "?"
    seconds = int(max(0, seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return "%dd %dh" % (days, hours)
    if hours:
        return "%dh %dm" % (hours, minutes)
    if minutes:
        return "%dm" % minutes
    return "%ds" % secs


def _clock(ts: Optional[float]) -> str:
    if ts is None:
        return "?"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def format_event(ev: Event) -> str:
    """Render one event as a Telegram HTML block."""
    key = html.escape(ev.key)
    msg = html.escape(ev.message)
    sev = ev.severity.upper()
    if ev.kind == RECOVERED:
        head = "%s <b>RECOVERED</b> <code>%s</code>" % (ICON_RECOVERED, key)
        foot = "was %s for %s" % (sev, human_duration(ev.duration))
    elif ev.kind == REMINDER:
        head = "%s <b>STILL %s</b> <code>%s</code>" % (ICON_REMINDER, sev, key)
        foot = "failing for %s (since %s)" % (human_duration(ev.duration), _clock(ev.since))
    elif ev.kind == ESCALATED:
        head = "%s <b>%s</b> <code>%s</code> ↑ escalated" % (ICONS[ev.severity], sev, key)
        foot = "since %s" % _clock(ev.since)
    else:
        head = "%s <b>%s</b> <code>%s</code>" % (ICONS[ev.severity], sev, key)
        foot = "since %s" % _clock(ev.since)
    return "%s\n%s\n<i>%s</i>" % (head, msg, foot)


def format_header(hostname: str) -> str:
    return "%s <b>%s</b>" % (ICON_HOST, html.escape(hostname))


def chunk_events(events: Sequence[Event], hostname: str,
                 limit: Optional[int] = None) -> List[List[Event]]:
    """Group events into messages that each fit Telegram's size limit."""
    limit = limit or MAX_MESSAGE
    header_len = len(format_header(hostname)) + 2
    chunks = []  # type: List[List[Event]]
    current = []  # type: List[Event]
    size = header_len
    for ev in events:
        block = len(format_event(ev)) + 2
        if current and size + block > limit:
            chunks.append(current)
            current, size = [], header_len
        current.append(ev)
        size += block
    if current:
        chunks.append(current)
    return chunks


def render(events: Sequence[Event], hostname: str, limit: Optional[int] = None) -> str:
    limit = limit or MAX_MESSAGE
    text = "\n\n".join([format_header(hostname)] + [format_event(e) for e in events])
    if len(text) > limit:  # a single gigantic message: truncate rather than fail
        text = text[: limit - 1] + "…"
    return text


class TelegramNotifier:
    """Sends messages via the Bot API with bounded retries."""

    def __init__(self, token: str, chat_id: str, timeout: float = 10,
                 api_url: str = "https://api.telegram.org", attempts: int = 3,
                 session: Any = None, sleep: Callable[[float], None] = time.sleep) -> None:
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout
        self.url = "%s/bot%s/sendMessage" % (api_url.rstrip("/"), token)
        self.attempts = attempts
        self.sleep = sleep
        if session is None:
            import requests
            session = requests.Session()
            session.headers["User-Agent"] = "qorovul"
        self.session = session

    def _redact(self, text: Any) -> str:
        return str(text).replace(self.token, "<token>") if self.token else str(text)

    def send_text(self, text: str) -> bool:
        """Send one message. Returns True when Telegram accepted it."""
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
                   "disable_web_page_preview": True}
        for attempt in range(1, self.attempts + 1):
            delay = float(2 ** (attempt - 1))
            try:
                resp = self.session.post(self.url, json=payload, timeout=self.timeout)
            except Exception as exc:  # requests.RequestException and friends
                log.warning("telegram send failed (attempt %d/%d): %s",
                            attempt, self.attempts, self._redact(exc))
            else:
                if resp.status_code == 200:
                    return True
                desc = self._describe(resp)
                if resp.status_code == 429:
                    delay = min(float(self._retry_after(resp) or delay), 60.0)
                elif 400 <= resp.status_code < 500:
                    # Bad token, wrong chat id, bot blocked: retrying will not help.
                    log.error("telegram rejected message (HTTP %d): %s",
                              resp.status_code, desc)
                    return False
                log.warning("telegram send failed (attempt %d/%d, HTTP %d): %s",
                            attempt, self.attempts, resp.status_code, desc)
            if attempt < self.attempts:
                self.sleep(delay)
        return False

    @staticmethod
    def _json(resp: Any) -> dict:
        try:
            data = resp.json()
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    def _describe(self, resp: Any) -> str:
        return self._redact(self._json(resp).get("description") or resp.reason or "")

    def _retry_after(self, resp: Any) -> Optional[float]:
        params = self._json(resp).get("parameters") or {}
        try:
            return float(params.get("retry_after"))
        except (TypeError, ValueError):
            return None

    def send_events(self, events: Sequence[Event], hostname: str) -> List[Event]:
        """Send events batched into as few messages as possible.

        Returns the events that were actually delivered, so the caller only
        commits those (undelivered ones stay due and are retried next cycle).
        """
        delivered = []  # type: List[Event]
        for chunk in chunk_events(events, hostname):
            if self.send_text(render(chunk, hostname)):
                delivered.extend(chunk)
            else:
                break  # keep ordering; try the rest next cycle
        return delivered


__all__ = ["TelegramNotifier", "format_event", "render", "chunk_events", "human_duration",
           "ALERT", "ESCALATED", "REMINDER", "RECOVERED"]
