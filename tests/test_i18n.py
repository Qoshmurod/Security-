"""Every language must be complete, well-formed and actually used everywhere."""

import importlib
import string
from datetime import datetime

import pytest

from qorovul.checks import build_checks
from qorovul.checks.base import CheckResult
from qorovul.config import ConfigError, validate
from qorovul.i18n import (EN, LANGUAGES, Translator, detect_language, display_width,
                          get_translator, ljust)
from qorovul.notifier import chunk_events, format_event, render
from qorovul.state import ALERT, ESCALATED, RECOVERED, REMINDER, Event

REFERENCE = importlib.import_module("qorovul.locales.en").MESSAGES
NON_EN = [code for code in LANGUAGES if code != "en"]
SAMPLE = {"severity": "WARNING", "time": "2026-11-16 14:03", "duration": "2h 5m",
          "mount": "/var", "percent": "87%", "free": "1 GB", "total": "8 GB",
          "error": "boom", "available": "1 GB", "unit": "nginx.service", "state": "failed",
          "ip": "203.0.113.9", "window": "10m", "count": 48, "users": "root",
          "limit": 20, "host": "example.com", "date": "2026-11-26", "days": 9,
          "reason": "self-signed certificate", "port": 8080, "addresses": "0.0.0.0",
          "processes": "nginx (pid 1)", "check": "ssh", "version": "1.1.0",
          "checks": 6, "failing": 1, "errors": 0, "path": "/var/lib/qorovul/state.json",
          "keys": 9}


def placeholders(template):
    return sorted({field for _, field, _, _ in string.Formatter().parse(template) if field})


def catalog(code):
    return importlib.import_module("qorovul.locales." + code)


# ------------------------------------------------------------- catalogs

def test_supported_languages():
    assert LANGUAGES[0] == "en"
    assert {"en", "uz", "ru", "tr", "ko"} <= set(LANGUAGES)
    assert len(LANGUAGES) == len(set(LANGUAGES)) >= 14


@pytest.mark.parametrize("code", NON_EN)
def test_catalog_has_exactly_the_reference_keys(code):
    messages = catalog(code).MESSAGES
    assert sorted(set(REFERENCE) - set(messages)) == [], "untranslated"
    assert sorted(set(messages) - set(REFERENCE)) == [], "unknown keys"


@pytest.mark.parametrize("code", NON_EN)
def test_catalog_placeholders_match_english(code):
    messages = catalog(code).MESSAGES
    wrong = {k: (placeholders(messages[k]), placeholders(REFERENCE[k]))
             for k in REFERENCE if placeholders(messages[k]) != placeholders(REFERENCE[k])}
    assert wrong == {}


@pytest.mark.parametrize("code", LANGUAGES)
def test_every_message_formats(code):
    tr = get_translator(code)
    for key in REFERENCE:
        text = tr(key, **SAMPLE)
        assert text.strip() and "{" not in text and "}" not in text, key


@pytest.mark.parametrize("code", NON_EN)
def test_catalog_is_really_translated(code):
    messages = catalog(code).MESSAGES
    # Short labels such as "INFO" or "ok" may legitimately match English.
    same = [k for k in REFERENCE if messages[k] == REFERENCE[k] and len(REFERENCE[k]) > 8]
    assert same == []


@pytest.mark.parametrize("code", LANGUAGES)
def test_catalog_metadata(code):
    mod = catalog(code)
    assert mod.NAME.strip()
    tr = get_translator(code)
    assert tr.decimal in (".", ",")
    assert "{n}" in tr.percent_pattern
    assert len(tr.size_units) == 5
    assert set(tr.duration_units) == {"d", "h", "m", "s"}


def test_partial_catalog_falls_back_to_english(monkeypatch):
    import qorovul.locales.uz as uz
    monkeypatch.setattr(uz, "MESSAGES", {"severity.critical": "KRITIK"})
    tr = Translator("uz")
    assert tr("severity.critical") == "KRITIK"
    assert tr("test.nothing") == "nothing to report"


def test_unknown_language_is_rejected():
    with pytest.raises(ValueError, match="unsupported language"):
        Translator("xx")


# ------------------------------------------------------------ formatting

@pytest.mark.parametrize("code,percent,size,duration", [
    ("en", "87.2%", "13.7 GB", "2h 5m"),
    ("uz", "87,2%", "13,7 GB", "2 soat 5 daq"),
    ("ru", "87,2%", "13,7 ГБ", "2 ч 5 мин"),
    ("tr", "%87,2", "13,7 GB", "2 sa 5 dk"),
    ("ko", "87.2%", "13.7 GB", "2시간 5분"),
    ("zh", "87.2%", "13.7 GB", "2小时5分"),
    ("fr", "87,2 %", "13,7 Go", "2 h 5 min"),
    ("de", "87,2 %", "13,7 GB", "2 Std. 5 Min."),
])
def test_locale_number_formats(code, percent, size, duration):
    tr = get_translator(code)
    assert tr.percent(87.25) == percent
    assert tr.size(13.7 * 2 ** 30) == size
    assert tr.duration(7500) == duration


def test_size_and_duration_edges():
    assert EN.size(512) == "512 B"
    assert EN.size(5 * 2 ** 50) == "5120.0 TB"
    assert get_translator("ru").size(10) == "10 Б"
    assert EN.duration(None) == "?"
    assert EN.duration(-5) == "0s"
    assert EN.duration(3 * 86400 + 7200) == "3d 2h"
    assert get_translator("ko").duration(600) == "10분"
    assert get_translator("uz").duration(600) == "10 daq"


# ------------------------------------------------------------ language choice

@pytest.mark.parametrize("env,expected", [
    ({}, "en"),
    ({"LANG": "ru_RU.UTF-8"}, "ru"),
    ({"LANG": "uz_UZ.UTF-8"}, "uz"),
    ({"LANG": "uz_UZ@cyrillic"}, "uz"),
    ({"LANG": "ko_KR.UTF-8"}, "ko"),
    ({"LANG": "zh_CN.UTF-8"}, "zh"),
    ({"LANG": "pt_BR.UTF-8"}, "pt"),
    ({"LANG": "C.UTF-8"}, "en"),
    ({"LANG": "sv_SE.UTF-8"}, "en"),
    ({"LC_ALL": "C", "LANG": "ru_RU.UTF-8"}, "en"),
    ({"LC_MESSAGES": "tr_TR.UTF-8", "LANG": "en_US.UTF-8"}, "tr"),
])
def test_detect_language(env, expected):
    assert detect_language(env) == expected


def test_config_language_default_and_auto():
    assert validate({}, env={})["language"] == "en"
    assert validate({"language": "uz"}, env={})["language"] == "uz"
    assert validate({"language": "auto"}, env={"LANG": "ko_KR.UTF-8"})["language"] == "ko"
    assert validate({"language": "auto"}, env={})["language"] == "en"


def test_config_language_env_override():
    assert validate({"language": "en"}, env={"QOROVUL_LANG": "tr"})["language"] == "tr"
    with pytest.raises(ConfigError, match="QOROVUL_LANG"):
        validate({}, env={"QOROVUL_LANG": "klingon"})


def test_config_language_validation():
    with pytest.raises(ConfigError, match="language: must be one of: en, uz, ru"):
        validate({"language": "english"}, env={})


# ------------------------------------------------------------ used everywhere

def test_checks_speak_the_configured_language():
    cfg = validate({"language": "uz",
                    "checks": {"service": {"units": ["nginx"]}}}, env={})
    checks = {c.name: c for c in build_checks(cfg)}
    assert all(c.tr.language == "uz" for c in checks.values())
    service = checks["service"]
    service.is_active = lambda units: ["failed"]
    [r] = service.run()
    assert r.message == "nginx.service holati: failed"
    assert checks["ports"].cleared_message("ports:tcp/8080") == "TCP 8080-port endi tinglanmayapti"


def test_ssh_window_uses_localized_duration():
    import os
    from qorovul.checks.ssh import SSHCheck
    cfg = validate({"language": "ko", "checks": {"ssh": {"failures": 1}}}, env={})
    check = SSHCheck(cfg["checks"]["ssh"], clock=lambda: 1_800_000_000.0,
                     opener=lambda p, m: __import__("io").BytesIO(b""),
                     stat=lambda p: os.stat_result((0, 1, 1, 1, 0, 0, 0, 0, 0, 0)),
                     readable=lambda p: True)
    check.tr = get_translator("ko")
    assert check.cleared_message("ssh:1.2.3.4") == "1.2.3.4의 로그인 실패가 10분당 1회 미만으로 감소"


T = datetime(2026, 11, 16, 14, 3).timestamp()


def event(kind, sev="critical", duration=None):
    return Event("disk:/var", kind, sev, "/var is full", T, T, duration=duration)


@pytest.mark.parametrize("code,alert,recovered,reminder", [
    ("uz", "<b>KRITIK</b>", "<b>TIKLANDI</b>", "<b>HAMON OGOHLANTIRISH</b>"),
    ("ru", "<b>КРИТИЧНО</b>", "<b>ВОССТАНОВЛЕНО</b>", "<b>ВСЁ ЕЩЁ ВНИМАНИЕ</b>"),
    ("tr", "<b>KRİTİK</b>", "<b>DÜZELDİ</b>", "<b>HÂLÂ UYARI</b>"),
    ("ko", "<b>심각</b>", "<b>복구됨</b>", "<b>여전히 경고</b>"),
])
def test_telegram_messages_in_language(code, alert, recovered, reminder):
    tr = get_translator(code)
    assert alert in format_event(event(ALERT), tr)
    rec = format_event(event(RECOVERED, duration=7500), tr)
    assert recovered in rec and tr.duration(7500) in rec
    assert reminder in format_event(event(REMINDER, sev="warning", duration=6 * 3600), tr)
    assert tr("event.escalated") in format_event(event(ESCALATED), tr)


@pytest.mark.parametrize("code", LANGUAGES)
def test_every_language_renders_valid_markup(code):
    tr = get_translator(code)
    events = [event(k, duration=60) for k in (ALERT, ESCALATED, REMINDER, RECOVERED)]
    text = render(events, "web-01", tr)
    assert text.count("<b>") == text.count("</b>") == 5
    assert text.count("<i>") == text.count("</i>") == 4
    assert text.count("<code>") == text.count("</code>") == 4
    assert chunk_events(events, "web-01", tr=tr) == [events]


def test_runner_error_messages_are_translated(tmp_path):
    from qorovul.checks.base import Check
    from qorovul.runner import Runner, run_check

    class Broken(Check):
        name = "ssh"

        def run(self):
            raise RuntimeError("no log")

    tr = get_translator("ru")
    [r], complete = run_check(Broken({}), tr=tr)
    assert r.message == "проверку ssh не удалось выполнить: no log" and not complete
    assert Runner._cleared(Broken({}), tr)("ssh:error") == "проверка ssh снова работает нормально"


def test_check_result_messages_are_plain_data():
    # Messages are stored in state.json as rendered text; a language change
    # takes effect for new results without touching old records.
    r = CheckResult("disk:/", False, "warning", "/ ist zu 91 % belegt")
    assert r.message.endswith("belegt")


# ------------------------------------------------------------ CLI

def test_display_width_and_ljust():
    assert display_width("abc") == 3
    assert display_width("상태") == 4
    assert display_width("状态ok") == 6
    assert display_width("é") == 1  # combining accent
    assert ljust("키", 4) == "키  "
    assert ljust("toolong", 3) == "toolong"


def test_cli_status_in_korean_lines_up(tmp_path, capsys):
    from qorovul.__main__ import main
    from qorovul.state import StateStore
    StateStore(str(tmp_path / "s.json")).save({
        "disk:/": {"check": "disk", "status": "failing", "severity": "warning",
                   "message": "/ 사용률 91%", "since": T, "last_seen": T,
                   "last_event": {"kind": "alert", "at": T, "severity": "warning",
                                  "message": "x"}},
        "memory:ram": {"check": "memory", "status": "ok", "severity": "info",
                       "message": "RAM", "since": None, "last_seen": T, "last_event": None},
    })
    cfg = tmp_path / "c.yml"
    cfg.write_text("state_file: %s\n" % (tmp_path / "s.json"))
    assert main(["status", "-c", str(cfg), "--lang", "ko"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "키: 2, 문제: 1" in lines[0]
    header, row1, row2 = lines[2], lines[3], lines[4]
    assert header.startswith("키") and "심각도" in header and "마지막 알림" in header
    assert "문제" in row1 and "경고" in row1 and "알림 2026-11-16 14:03" in row1
    assert "정상" in row2
    # columns line up in terminal cells
    col = display_width(header[: header.index("상태")])
    assert display_width(row1[: row1.index("문제")]) == col


def test_cli_lang_flag_validation(tmp_path, capsys):
    from qorovul.__main__ import main
    cfg = tmp_path / "c.yml"
    cfg.write_text("interval: 30\n")
    assert main(["status", "-c", str(cfg), "--lang", "xx"]) == 2
    assert "unsupported language 'xx'" in capsys.readouterr().err


def test_cli_test_in_uzbek(tmp_path, capsys, monkeypatch):
    import qorovul.__main__ as cli
    import qorovul.checks as checks_mod
    from qorovul.checks.base import Check

    class Disk(Check):
        name = "disk"

        def run(self):
            return [CheckResult("disk:/", False, "warning", "/ 91% toʻlgan")]

    sent = []

    class N:
        def send_text(self, text):
            sent.append(text)
            return True
    monkeypatch.setattr(cli, "_notifier", lambda cfg: N())
    monkeypatch.setattr(checks_mod, "build_checks", lambda cfg: [Disk({})])
    cfg = tmp_path / "c.yml"
    cfg.write_text("language: uz\nstate_file: %s\n" % (tmp_path / "s.json"))
    assert cli.main(["test", "-c", str(cfg)]) == 1
    out = capsys.readouterr().out
    assert "bajarilgan tekshiruvlar: 1, muammoli: 1, xatolar: 0" in out
    assert "telegram: sinov xabari yuborildi" in out
    assert "Qorovul sinov xabari (v" in sent[0]
