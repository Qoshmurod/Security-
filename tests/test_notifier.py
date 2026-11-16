import logging

from qorovul.notifier import (TelegramNotifier, chunk_events, format_event, human_duration,
                              render)
from qorovul.state import ALERT, ESCALATED, RECOVERED, REMINDER, Event

TOKEN = "123456789:AAEsecretsecretsecretsecretsecret"


class Resp:
    def __init__(self, status=200, body=None, reason="OK"):
        self.status_code = status
        self._body = body if body is not None else {"ok": status == 200}
        self.reason = reason

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json, timeout))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def notifier(*responses):
    sleeps = []
    n = TelegramNotifier(TOKEN, "-100123", timeout=7, session=Session(*responses),
                         sleep=sleeps.append)
    return n, n.session, sleeps


def ev(kind=ALERT, key="disk:/var", sev="warning", msg="/var is 91.0% full", dur=None):
    return Event(key, kind, sev, msg, since=1_700_000_000, at=1_700_000_000, duration=dur)


def test_human_duration():
    assert human_duration(None) == "?"
    assert human_duration(5) == "5s"
    assert human_duration(125) == "2m"
    assert human_duration(2 * 3600 + 300) == "2h 5m"
    assert human_duration(3 * 86400 + 7200) == "3d 2h"
    assert human_duration(-4) == "0s"


def test_format_alert():
    text = format_event(ev())
    assert text.startswith("\U0001F7E0 <b>WARNING</b> <code>disk:/var</code>\n/var is 91.0% full\n")
    assert "<i>since " in text


def test_format_kinds():
    assert format_event(ev(sev="critical")).startswith("\U0001F534 <b>CRITICAL</b>")
    assert "escalated" in format_event(ev(ESCALATED, sev="critical"))
    rem = format_event(ev(REMINDER, dur=6 * 3600))
    assert "<b>STILL WARNING</b>" in rem and "failing for 6h 0m" in rem
    rec = format_event(ev(RECOVERED, msg="/var is 40.0% full", dur=7500))
    assert rec.startswith("✅ <b>RECOVERED</b> <code>disk:/var</code>")
    assert "was WARNING for 2h 5m" in rec


def test_format_escapes_html_from_untrusted_input():
    # SSH user names come from attackers.
    text = format_event(ev(key="ssh:1.2.3.4", msg="5 failed (users: <script>&)"))
    assert "<script>" not in text
    assert "&lt;script&gt;&amp;" in text


def test_render_has_host_header():
    text = render([ev(), ev(key="disk:/")], "web-<01>")
    assert text.startswith("\U0001F6E1 <b>web-&lt;01&gt;</b>\n\n")
    assert text.count("<code>disk:") == 2


def test_chunking_respects_limit():
    events = [ev(key="disk:/m%d" % i, msg="x" * 300) for i in range(40)]
    chunks = chunk_events(events, "host", limit=1000)
    assert sum(len(c) for c in chunks) == 40
    assert all(len(render(c, "host")) <= 1000 for c in chunks)
    assert len(chunks) > 1


def test_render_truncates_single_oversized_event():
    text = render([ev(msg="y" * 10000)], "host", limit=500)
    assert len(text) == 500 and text.endswith("…")


def test_send_success_payload():
    n, s, _ = notifier(Resp(200))
    assert n.send_text("hi") is True
    url, payload, timeout = s.calls[0]
    assert url == "https://api.telegram.org/bot%s/sendMessage" % TOKEN
    assert payload == {"chat_id": "-100123", "text": "hi", "parse_mode": "HTML",
                       "disable_web_page_preview": True}
    assert timeout == 7


def test_retry_on_server_error_then_success():
    n, s, sleeps = notifier(Resp(502, reason="Bad Gateway"), Resp(200))
    assert n.send_text("hi") is True
    assert len(s.calls) == 2 and sleeps == [1.0]


def test_retry_on_network_error_with_backoff():
    n, s, sleeps = notifier(OSError("down"), OSError("down"), OSError("down"))
    assert n.send_text("hi") is False
    assert len(s.calls) == 3 and sleeps == [1.0, 2.0]


def test_rate_limit_honours_retry_after():
    n, _, sleeps = notifier(Resp(429, {"ok": False, "parameters": {"retry_after": 17}}), Resp(200))
    assert n.send_text("hi") is True
    assert sleeps == [17.0]


def test_rate_limit_retry_after_is_capped():
    n, _, sleeps = notifier(Resp(429, {"parameters": {"retry_after": 9999}}), Resp(200))
    n.send_text("hi")
    assert sleeps == [60.0]


def test_client_error_is_not_retried(caplog):
    n, s, sleeps = notifier(Resp(400, {"ok": False, "description": "Bad Request: chat not found"}))
    with caplog.at_level(logging.ERROR):
        assert n.send_text("hi") is False
    assert len(s.calls) == 1 and sleeps == []
    assert "chat not found" in caplog.text


def test_non_json_error_body():
    n, _, _ = notifier(Resp(500, ValueError("no json"), reason="Oops"),
                       Resp(500, ValueError(), reason="Oops"), Resp(500, ValueError()))
    assert n.send_text("hi") is False


def test_token_never_logged(caplog):
    err = OSError("Max retries exceeded with url: /bot%s/sendMessage" % TOKEN)
    n, _, _ = notifier(err, err, Resp(401, {"description": "Unauthorized " + TOKEN}))
    with caplog.at_level(logging.DEBUG):
        n.send_text("hi")
    assert TOKEN not in caplog.text
    assert "<token>" in caplog.text


def test_send_events_batches_into_one_message():
    n, s, _ = notifier(Resp(200))
    events = [ev(), ev(RECOVERED, key="disk:/")]
    assert n.send_events(events, "web-01") == events
    assert len(s.calls) == 1


def test_send_events_partial_failure_returns_delivered_prefix(monkeypatch):
    import qorovul.notifier as mod
    monkeypatch.setattr(mod, "MAX_MESSAGE", 600)
    events = [ev(key="disk:/m%d" % i, msg="x" * 250) for i in range(6)]
    n, s, _ = notifier(Resp(200), Resp(400, {"description": "nope"}))
    delivered = n.send_events(events, "h")
    assert 0 < len(delivered) < len(events)
    assert delivered == events[:len(delivered)]
    assert len(s.calls) == 2  # stopped after the failure
