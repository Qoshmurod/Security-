"""Configuration loading and validation.

The config is a single YAML file (default ``/etc/qorovul/config.yml``).
Every key has a default, unknown keys are rejected (typos fail fast), and all
problems are reported together with their dotted path.
"""

import copy
import ipaddress
import os
import re
import socket
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from .checks.base import SEVERITIES

DEFAULT_CONFIG_PATH = "/etc/qorovul/config.yml"
ENV_CONFIG = "QOROVUL_CONFIG"
ENV_BOT_TOKEN = "QOROVUL_BOT_TOKEN"
ENV_CHAT_ID = "QOROVUL_CHAT_ID"

_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([smhd]?)\s*$")
_UNITS = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{20,}$")
_CHAT_RE = re.compile(r"^(-?\d+|@[A-Za-z][A-Za-z0-9_]{3,})$")


class ConfigError(Exception):
    """Raised when the configuration cannot be loaded or is invalid."""


def parse_duration(value: Any) -> float:
    """Parse ``30``, ``"30s"``, ``"10m"``, ``"6h"`` or ``"1d"`` into seconds."""
    if isinstance(value, bool):
        raise ValueError("expected a duration like 30s, 10m, 6h")
    if isinstance(value, (int, float)):
        return float(value)
    m = _DURATION_RE.match(str(value))
    if not m:
        raise ValueError("expected a duration like 30s, 10m, 6h, got %r" % (value,))
    return float(m.group(1)) * _UNITS[m.group(2)]


# --------------------------------------------------------------------------
# Tiny schema: each leaf is (validator, default); dicts nest.
# A validator takes the raw value and returns the normalized value or raises
# ValueError with a human readable reason.
# --------------------------------------------------------------------------

Validator = Callable[[Any], Any]


def v_bool(v: Any) -> bool:
    if not isinstance(v, bool):
        raise ValueError("expected true or false")
    return v


def v_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list, bool)):
        raise ValueError("expected a string")
    return str(v)


def v_nonempty_str(v: Any) -> str:
    s = v_str(v).strip()
    if not s:
        raise ValueError("must not be empty")
    return s


def v_num(lo: float, hi: float) -> Validator:
    def check(v: Any) -> float:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("expected a number")
        if not lo <= v <= hi:
            raise ValueError("must be between %g and %g" % (lo, hi))
        return float(v)
    return check


def v_int(lo: int, hi: int) -> Validator:
    def check(v: Any) -> int:
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("expected a whole number")
        if not lo <= v <= hi:
            raise ValueError("must be between %d and %d" % (lo, hi))
        return v
    return check


def v_duration(minimum: float = 0) -> Validator:
    def check(v: Any) -> float:
        secs = parse_duration(v)
        if secs < minimum:
            raise ValueError("must be at least %gs" % minimum)
        return secs
    return check


def v_enum(*choices: str) -> Validator:
    def check(v: Any) -> str:
        if v not in choices:
            raise ValueError("must be one of: %s" % ", ".join(choices))
        return v
    return check


def v_time(v: Any) -> str:
    s = v_str(v).strip()
    if not _TIME_RE.match(s):
        raise ValueError("expected HH:MM (24h), got %r" % (v,))
    h, m = s.split(":")
    return "%02d:%02d" % (int(h), int(m))


def v_optional(inner: Validator) -> Validator:
    def check(v: Any) -> Any:
        return None if v is None else inner(v)
    return check


def v_list(inner: Validator) -> Validator:
    def check(v: Any) -> List[Any]:
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("expected a list")
        out = []
        for i, item in enumerate(v):
            try:
                out.append(inner(item))
            except ValueError as exc:
                raise ValueError("item %d: %s" % (i + 1, exc))
        return out
    return check


def v_network(v: Any) -> str:
    s = v_nonempty_str(v)
    try:
        ipaddress.ip_network(s, strict=False)
    except ValueError:
        raise ValueError("%r is not an IP address or CIDR network" % s)
    return s


def v_port_entry(v: Any) -> Any:
    """Allowlist entry: 22, "22", "127.0.0.1:5432" or "[::1]:6379"."""
    if isinstance(v, bool):
        raise ValueError("expected a port number or \"address:port\"")
    if isinstance(v, int) or (isinstance(v, str) and v.strip().isdigit()):
        port = int(v)
        if not 1 <= port <= 65535:
            raise ValueError("port %d out of range" % port)
        return port
    s = v_nonempty_str(v)
    host, sep, port_s = s.rpartition(":")
    try:
        if not sep:
            raise ValueError
        ipaddress.ip_address(host.strip("[]"))
        if not 1 <= int(port_s) <= 65535:
            raise ValueError
    except ValueError:
        raise ValueError("%r is not a port or \"address:port\"" % s)
    return s


def v_domain(v: Any) -> str:
    s = v_nonempty_str(v)
    if "/" in s or " " in s:
        raise ValueError("%r: give a bare host name, optionally host:port" % s)
    return s


def _common(enabled: bool = True) -> Dict[str, Any]:
    return {
        "enabled": (v_bool, enabled),
        "interval": (v_optional(v_duration(5)), None),
        "cooldown": (v_optional(v_duration(0)), None),
        "send_recovery": (v_optional(v_bool), None),
    }


SEVERITY = v_enum(*SEVERITIES)

SCHEMA = {
    "hostname": (v_str, ""),
    "interval": (v_duration(5), 30),
    "state_file": (v_nonempty_str, "/var/lib/qorovul/state.json"),
    "log_level": (v_enum("debug", "info", "warning", "error"), "info"),
    "telegram": {
        "bot_token": (v_str, ""),
        "chat_id": (v_str, ""),
        "timeout": (v_duration(1), 10),
        "api_url": (v_nonempty_str, "https://api.telegram.org"),
    },
    "alerts": {
        "min_severity": (SEVERITY, "warning"),
        "cooldown": (v_duration(0), "6h"),
        "recovery_cycles": (v_int(1, 1000), 2),
        "send_recovery": (v_bool, True),
        "quiet_hours": {
            "enabled": (v_bool, False),
            "start": (v_time, "23:00"),
            "end": (v_time, "07:00"),
        },
    },
    "checks": {
        "disk": dict(_common(), **{
            "threshold": (v_num(1, 100), 85),
            "critical_threshold": (v_optional(v_num(1, 100)), 95),
            "mountpoints": (v_list(v_nonempty_str), []),
            "exclude_fstypes": (v_list(v_nonempty_str), [
                "tmpfs", "devtmpfs", "squashfs", "overlay", "iso9660", "ramfs",
                "autofs", "nsfs", "fuse.lxcfs"]),
            "exclude_mountpoints": (v_list(v_nonempty_str), ["/snap", "/var/lib/docker"]),
        }),
        "memory": dict(_common(), **{
            "threshold": (v_num(1, 100), 90),
            "critical_threshold": (v_optional(v_num(1, 100)), 97),
            "sustained_cycles": (v_int(1, 1000), 3),
        }),
        "service": dict(_common(), **{
            "units": (v_list(v_nonempty_str), []),
            "severity": (SEVERITY, "critical"),
        }),
        "ssh": dict(_common(), **{
            "source": (v_enum("auto", "file", "journal"), "auto"),
            "log_paths": (v_list(v_nonempty_str), ["/var/log/auth.log", "/var/log/secure"]),
            "failures": (v_int(1, 1000000), 20),
            "window": (v_duration(60), "10m"),
            "severity": (SEVERITY, "warning"),
            "ignore_ips": (v_list(v_network), []),
        }),
        "ssl": dict(_common(), **{
            "domains": (v_list(v_domain), []),
            "warn_days": (v_num(0, 3650), 14),
            "critical_days": (v_num(0, 3650), 3),
            "timeout": (v_duration(1), 10),
            "connect_error_severity": (SEVERITY, "warning"),
        }),
        "ports": dict(_common(), **{
            "allowed": (v_list(v_port_entry), [22]),
            "ignore_loopback": (v_bool, True),
            "severity": (SEVERITY, "warning"),
        }),
    },
}

# Per-check interval defaults that differ from the global interval.
CHECK_INTERVAL_DEFAULTS = {"ssl": 3600.0}


def _apply(schema: Dict[str, Any], data: Any, path: str, errors: List[str]) -> Dict[str, Any]:
    if data is None:
        data = {}
    if not isinstance(data, dict):
        errors.append("%s: expected a mapping" % (path or "<root>"))
        data = {}
    out = {}
    for key in data:
        if key not in schema:
            errors.append("%s: unknown key (allowed: %s)" % (
                _join(path, str(key)), ", ".join(sorted(schema))))
    for key, spec in schema.items():
        sub = _join(path, key)
        if isinstance(spec, dict):
            out[key] = _apply(spec, data.get(key), sub, errors)
            continue
        validator, default = spec
        raw = data[key] if key in data else copy.deepcopy(default)
        try:
            out[key] = validator(raw)
        except ValueError as exc:
            errors.append("%s: %s" % (sub, exc))
            out[key] = None
    return out


def _join(path: str, key: str) -> str:
    return "%s.%s" % (path, key) if path else key


def _cross_validate(cfg: Dict[str, Any], errors: List[str]) -> None:
    checks = cfg["checks"]
    for name in ("disk", "memory"):
        c = checks[name]
        if c["threshold"] is not None and c["critical_threshold"] is not None \
                and c["critical_threshold"] < c["threshold"]:
            errors.append("checks.%s.critical_threshold: must be >= threshold (%g)"
                          % (name, c["threshold"]))
    s = checks["ssl"]
    if s["warn_days"] is not None and s["critical_days"] is not None \
            and s["critical_days"] > s["warn_days"]:
        errors.append("checks.ssl.critical_days: must be <= warn_days (%g)" % s["warn_days"])
    q = cfg["alerts"]["quiet_hours"]
    if q["enabled"] and q["start"] == q["end"]:
        errors.append("alerts.quiet_hours: start and end must differ")
    t = cfg["telegram"]
    if t["bot_token"] and not _TOKEN_RE.match(t["bot_token"]):
        errors.append("telegram.bot_token: does not look like a bot token "
                      "(expected 123456789:ABC... from @BotFather)")
    if t["chat_id"] and not _CHAT_RE.match(t["chat_id"]):
        errors.append("telegram.chat_id: expected a numeric id (e.g. 123456789 or "
                      "-1001234567890) or @channelname")


def validate(data: Any, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Validate raw parsed YAML, apply defaults and env overrides."""
    env = os.environ if env is None else env
    errors = []  # type: List[str]
    cfg = _apply(SCHEMA, data, "", errors)
    if env.get(ENV_BOT_TOKEN):
        cfg["telegram"]["bot_token"] = env[ENV_BOT_TOKEN].strip()
    if env.get(ENV_CHAT_ID):
        cfg["telegram"]["chat_id"] = env[ENV_CHAT_ID].strip()
    if not errors:
        _cross_validate(cfg, errors)
    if errors:
        raise ConfigError("invalid configuration:\n  - " + "\n  - ".join(errors))
    if not cfg["hostname"]:
        cfg["hostname"] = socket.gethostname()
    for name, section in cfg["checks"].items():
        if section["interval"] is None:
            section["interval"] = CHECK_INTERVAL_DEFAULTS.get(name, cfg["interval"])
    return cfg


def config_path(explicit: Optional[str] = None) -> str:
    return explicit or os.environ.get(ENV_CONFIG) or DEFAULT_CONFIG_PATH


def load(path: Optional[str] = None, env: Optional[Dict[str, str]] = None,
         missing_ok: bool = False) -> Dict[str, Any]:
    """Load and validate the config file.

    With ``missing_ok`` a missing file yields the defaults (used by ``status``).
    """
    path = config_path(path)
    try:
        with open(path) as fh:
            text = fh.read()
    except FileNotFoundError:
        if missing_ok:
            return validate({}, env)
        raise ConfigError("config file not found: %s (copy config.example.yml there)" % path)
    except OSError as exc:
        raise ConfigError("cannot read config %s: %s" % (path, exc.strerror or exc))
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError("cannot parse %s: %s" % (path, exc))
    return validate(data, env)


def require_telegram(cfg: Dict[str, Any]) -> Tuple[str, str]:
    """Return (token, chat_id) or raise ConfigError if either is missing."""
    t = cfg["telegram"]
    missing = [name for name, val, env in (
        ("telegram.bot_token", t["bot_token"], ENV_BOT_TOKEN),
        ("telegram.chat_id", t["chat_id"], ENV_CHAT_ID)) if not val]
    if missing:
        raise ConfigError("missing %s (set it in the config file or via %s / %s)"
                          % (" and ".join(missing), ENV_BOT_TOKEN, ENV_CHAT_ID))
    return t["bot_token"], t["chat_id"]
