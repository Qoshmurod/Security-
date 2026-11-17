"""Telegram delivery and message formatting."""

import html
import logging
import re
import time
from datetime import datetime
from typing import Any, Callable, List, Optional, Sequence

from .i18n import EN, Translator
from .state import ALERT, ESCALATED, RECOVERED, REMINDER, Event

log = logging.getLogger(__name__)

MAX_MESSAGE = 4000  # Telegram's hard limit is 4096; leave headroom
# Caps on untrusted/variable text.  Escaping can grow text up to 5x ("&" ->
# "&amp;"), so these keep even a worst-case single event within MAX_MESSAGE
# without ever cutting through an HTML tag or entity.
MAX_EVENT_TEXT = 500
MAX_KEY_TEXT = 120
MAX_HOST_TEXT = 64
_TAG_RE = re.compile(r"<[^>]+>")
ICONS = {"critical": "\U0001F534", "warning": "\U0001F7E0", "info": "\U0001F535"}
ICON_RECOVERED = "✅"
ICON_REMINDER = "\U0001F501"
ICON_HOST = "\U0001F6E1"


def human_duration(seconds: Optional[float], tr: Translator = EN) -> str:
    return tr.duration(seconds)


def _clock(ts: Optional[float]) -> str:
    if ts is None:
        return "?"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())  # one line, no control characters
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def _esc(text: str, limit: int) -> str:
    return html.escape(_clip(text, limit), quote=False)


def to_plain(text: str) -> str:
    """Strip our HTML markup (fallback when Telegram refuses to parse it)."""
    return html.unescape(_TAG_RE.sub("", text))


def format_event(ev: Event, tr: Translator = EN) -> str:
    """Render one event as a Telegram HTML block in the given language."""
    def e(text: str) -> str:  # translations are trusted, but never let them break markup
        return html.escape(text, quote=False)

    key = _esc(ev.key, MAX_KEY_TEXT)
    msg = _esc(ev.message, MAX_EVENT_TEXT)
    sev = tr.severity(ev.severity)
    if ev.kind == RECOVERED:
        head = "%s <b>%s</b> <code>%s</code>" % (ICON_RECOVERED, e(tr("event.recovered")), key)
        foot = tr("footer.was", severity=sev, duration=tr.duration(ev.duration))
    elif ev.kind == REMINDER:
        head = "%s <b>%s</b> <code>%s</code>" % (
            ICON_REMINDER, e(tr("event.still", severity=sev)), key)
        foot = tr("footer.failing_for", duration=tr.duration(ev.duration),
                  time=_clock(ev.since))
    elif ev.kind == ESCALATED:
        head = "%s <b>%s</b> <code>%s</code> \u2191 %s" % (
            ICONS[ev.severity], e(sev), key, e(tr("event.escalated")))
        foot = tr("footer.since", time=_clock(ev.since))
    else:
        head = "%s <b>%s</b> <code>%s</code>" % (ICONS[ev.severity], e(sev), key)
        foot = tr("footer.since", time=_clock(ev.since))
    return "%s\n%s\n<i>%s</i>" % (head, msg, e(foot))


def format_header(hostname: str) -> str:
    return "%s <b>%s</b>" % (ICON_HOST, _esc(hostname, MAX_HOST_TEXT))


def chunk_events(events: Sequence[Event], hostname: str,
                 limit: Optional[int] = None, tr: Translator = EN) -> List[List[Event]]:
    """Group events into messages that each fit Telegram's size limit."""
    limit = limit or MAX_MESSAGE
    header_len = len(format_header(hostname)) + 2
    chunks = []  # type: List[List[Event]]
    current = []  # type: List[Event]
    size = header_len
    for ev in events:
        block = len(format_event(ev, tr)) + 2
        if current and size + block > limit:
            chunks.append(current)
            current, size = [], header_len
        current.append(ev)
        size += block
    if current:
        chunks.append(current)
    return chunks


def render(events: Sequence[Event], hostname: str, tr: Translator = EN) -> str:
    return "\n\n".join([format_header(hostname)] + [format_event(e, tr) for e in events])


class TelegramNotifier:
    """Sends messages via the Bot API with bounded retries."""

    def __init__(self, token: str, chat_id: str, timeout: float = 10,
                 api_url: str = "https://api.telegram.org", attempts: int = 3,
                 session: Any = None, sleep: Callable[[float], None] = time.sleep,
                 tr: Translator = EN) -> None:
        self.token = token
        self.tr = tr
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
        """Send one HTML message. Returns True when Telegram accepted it."""
        status = self._post({"chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
                             "disable_web_page_preview": True})
        if status == "unparsable":
            # Should not happen (everything is escaped), but an alert that
            # arrives without formatting beats one that never arrives.
            log.warning("telegram could not parse the message markup; resending as plain text")
            status = self._post({"chat_id": self.chat_id, "text": to_plain(text)[:4096],
                                 "disable_web_page_preview": True})
        return status == "ok"

    def _post(self, payload: dict) -> str:
        """POST with retries. Returns "ok", "unparsable" or "failed"."""
        for attempt in range(1, self.attempts + 1):
            delay = float(2 ** (attempt - 1))
            try:
                resp = self.session.post(self.url, json=payload, timeout=self.timeout)
            except Exception as exc:  # requests.RequestException and friends
                log.warning("telegram send failed (attempt %d/%d): %s",
                            attempt, self.attempts, self._redact(exc))
            else:
                if resp.status_code == 200:
                    return "ok"
                desc = self._describe(resp)
                if resp.status_code == 429:
                    delay = min(float(self._retry_after(resp) or delay), 60.0)
                elif 400 <= resp.status_code < 500:
                    if resp.status_code == 400 and "parse" in desc.lower() \
                            and "parse_mode" in payload:
                        return "unparsable"
                    # Bad token, wrong chat id, bot blocked: retrying will not help.
                    log.error("telegram rejected message (HTTP %d): %s",
                              resp.status_code, desc)
                    return "failed"
                log.warning("telegram send failed (attempt %d/%d, HTTP %d): %s",
                            attempt, self.attempts, resp.status_code, desc)
            if attempt < self.attempts:
                self.sleep(delay)
        return "failed"

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
        for chunk in chunk_events(events, hostname, tr=self.tr):
            if self.send_text(render(chunk, hostname, self.tr)):
                delivered.extend(chunk)
            else:
                break  # keep ordering; try the rest next cycle
        return delivered


__all__ = ["TelegramNotifier", "format_event", "render", "chunk_events", "human_duration",
           "to_plain",
           "ALERT", "ESCALATED", "REMINDER", "RECOVERED"]
