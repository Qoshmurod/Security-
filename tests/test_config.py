import os

import pytest

from qorovul.config import ConfigError, load, parse_duration, require_telegram, validate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = "123456789:AAEabcdefghijklmnopqrstuvwxyz012345"


def test_defaults():
    cfg = validate({}, env={})
    assert cfg["interval"] == 30
    assert cfg["alerts"]["cooldown"] == 6 * 3600
    assert cfg["alerts"]["min_severity"] == "warning"
    assert cfg["checks"]["disk"]["threshold"] == 85
    assert cfg["checks"]["memory"]["threshold"] == 90
    assert cfg["checks"]["memory"]["sustained_cycles"] == 3
    assert cfg["checks"]["ssh"]["failures"] == 20
    assert cfg["checks"]["ssh"]["window"] == 600
    assert cfg["checks"]["ssl"]["warn_days"] == 14
    assert cfg["checks"]["ports"]["allowed"] == [22]
    assert cfg["checks"]["disk"]["interval"] == 30
    assert cfg["checks"]["ssl"]["interval"] == 3600
    assert cfg["hostname"]  # filled from the system


def test_example_config_is_valid_and_matches_defaults():
    cfg = load(os.path.join(ROOT, "config.example.yml"), env={})
    defaults = validate({}, env={})
    cfg["hostname"] = defaults["hostname"]
    assert cfg == defaults


@pytest.mark.parametrize("value,secs", [
    (30, 30), (1.5, 1.5), ("45", 45), ("30s", 30), ("10m", 600), ("6h", 21600), ("1d", 86400),
    (" 2 h ", 7200)])
def test_parse_duration(value, secs):
    assert parse_duration(value) == secs


@pytest.mark.parametrize("value", ["", "10x", "-5s", "h", True, [1]])
def test_parse_duration_rejects(value):
    with pytest.raises(ValueError):
        parse_duration(value)


def errors_of(data):
    with pytest.raises(ConfigError) as exc:
        validate(data, env={})
    return str(exc.value)


def test_unknown_key_is_an_error():
    msg = errors_of({"checks": {"disk": {"treshold": 80}}})
    assert "checks.disk.treshold: unknown key" in msg


def test_unknown_check_is_an_error():
    assert "checks.cpu: unknown key" in errors_of({"checks": {"cpu": {}}})


def test_all_errors_reported_together():
    msg = errors_of({"interval": "fast", "checks": {"disk": {"threshold": 150},
                                                    "ssh": {"failures": 0}}})
    assert "interval:" in msg
    assert "checks.disk.threshold: must be between 1 and 100" in msg
    assert "checks.ssh.failures: must be between" in msg


@pytest.mark.parametrize("data,needle", [
    ({"interval": 1}, "interval: must be at least 5s"),
    ({"alerts": {"min_severity": "urgent"}}, "must be one of: info, warning, critical"),
    ({"alerts": {"quiet_hours": {"start": "25:00"}}}, "expected HH:MM"),
    ({"alerts": {"quiet_hours": {"enabled": True, "start": "07:00", "end": "07:00"}}},
     "start and end must differ"),
    ({"checks": {"disk": {"enabled": "yes"}}}, "expected true or false"),
    ({"checks": {"disk": {"threshold": 90, "critical_threshold": 80}}}, "must be >= threshold"),
    ({"checks": {"ssl": {"warn_days": 5, "critical_days": 10}}}, "must be <= warn_days"),
    ({"checks": {"ssl": {"domains": ["https://example.com/"]}}}, "bare host name"),
    ({"checks": {"ports": {"allowed": [70000]}}}, "out of range"),
    ({"checks": {"ports": {"allowed": ["localhost:80"]}}}, "is not a port"),
    ({"checks": {"ports": {"allowed": "22"}}}, "expected a list"),
    ({"checks": {"ssh": {"ignore_ips": ["10.0.0.0/33"]}}}, "not an IP address or CIDR"),
    ({"checks": {"ssh": {"window": "10s"}}}, "must be at least 60s"),
    ({"checks": {"service": {"units": [""]}}}, "item 1: must not be empty"),
    ({"telegram": {"bot_token": "nope"}}, "does not look like a bot token"),
    ({"telegram": {"chat_id": "my chat"}}, "telegram.chat_id"),
    ({"checks": []}, "checks: expected a mapping"),
    ({"heartbeat": {"url": "hc-ping.com/abc"}}, "heartbeat.url: expected an http:// or https://"),
    ({"heartbeat": {"interval": "5s"}}, "heartbeat.interval: must be at least 30s"),
    ({"checks": {"service": {"confirm_cycles": 0}}}, "checks.service.confirm_cycles"),
])
def test_validation_errors(data, needle):
    assert needle in errors_of(data)


def test_heartbeat_and_confirm_defaults():
    cfg = validate({}, env={})
    assert cfg["heartbeat"] == {"url": "", "interval": 300, "timeout": 10}
    assert cfg["checks"]["service"]["confirm_cycles"] == 2
    assert cfg["checks"]["memory"]["confirm_cycles"] == 3  # = sustained_cycles
    assert all(cfg["checks"][n]["confirm_cycles"] == 1
               for n in ("disk", "ssh", "ssl", "ports"))
    cfg = validate({"heartbeat": {"url": " https://hc-ping.com/uuid "}}, env={})
    assert cfg["heartbeat"]["url"] == "https://hc-ping.com/uuid"


def test_quiet_hours_normalized():
    cfg = validate({"alerts": {"quiet_hours": {"start": "7:05"}}}, env={})
    assert cfg["alerts"]["quiet_hours"]["start"] == "07:05"


def test_null_critical_threshold_allowed():
    assert validate({"checks": {"disk": {"critical_threshold": None}}},
                    env={})["checks"]["disk"]["critical_threshold"] is None


def test_numeric_chat_id_from_yaml_becomes_string():
    cfg = validate({"telegram": {"chat_id": -1001234567890}}, env={})
    assert cfg["telegram"]["chat_id"] == "-1001234567890"


def test_env_overrides_file_values():
    cfg = validate({"telegram": {"bot_token": TOKEN, "chat_id": "1"}},
                   env={"QOROVUL_BOT_TOKEN": "999:" + "z" * 30, "QOROVUL_CHAT_ID": "42"})
    assert require_telegram(cfg) == ("999:" + "z" * 30, "42")


def test_env_values_are_validated():
    with pytest.raises(ConfigError, match="bot token"):
        validate({}, env={"QOROVUL_BOT_TOKEN": "garbage"})


def test_require_telegram_missing():
    with pytest.raises(ConfigError, match="missing telegram.bot_token and telegram.chat_id"):
        require_telegram(validate({}, env={}))


def test_per_check_interval_override():
    cfg = validate({"interval": 60, "checks": {"ssl": {"interval": "6h"},
                                               "disk": {"interval": "5m"}}}, env={})
    assert cfg["checks"]["ssl"]["interval"] == 21600
    assert cfg["checks"]["disk"]["interval"] == 300
    assert cfg["checks"]["memory"]["interval"] == 60


def test_load_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="config file not found"):
        load(str(tmp_path / "nope.yml"), env={})
    assert load(str(tmp_path / "nope.yml"), env={}, missing_ok=True)["interval"] == 30


def test_load_bad_yaml(tmp_path):
    p = tmp_path / "c.yml"
    p.write_text("checks: [unclosed\n")
    with pytest.raises(ConfigError, match="cannot parse"):
        load(str(p), env={})


def test_load_empty_file_gives_defaults(tmp_path):
    p = tmp_path / "c.yml"
    p.write_text("# nothing\n")
    assert load(str(p), env={})["interval"] == 30


def test_load_uses_env_path(tmp_path, monkeypatch):
    p = tmp_path / "c.yml"
    p.write_text("interval: 45\n")
    monkeypatch.setenv("QOROVUL_CONFIG", str(p))
    assert load(env={})["interval"] == 45
