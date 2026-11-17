"""Command line interface: ``qorovul run | test | status | version``."""

import argparse
import json
import logging
import os
import signal
import sys
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import __version__
from .config import DEFAULT_CONFIG_PATH, ConfigError, load, require_telegram
from .i18n import AUTO, LANGUAGES, display_width, get_translator, ljust, resolve_language

EXIT_OK = 0
EXIT_CHECKS_FAILING = 1
EXIT_CONFIG = 2
EXIT_TELEGRAM = 3


def _setup_logging(level: str) -> None:
    # Under systemd journald adds timestamps itself.
    fmt = "%(levelname)s %(message)s" if os.environ.get("JOURNAL_STREAM") \
        else "%(asctime)s %(levelname)s %(message)s"
    logging.basicConfig(level=getattr(logging, level.upper()), format=fmt, stream=sys.stderr)


def _load(args: argparse.Namespace, missing_ok: bool = False) -> Dict[str, Any]:
    """Load the config and apply ``--lang`` if given."""
    cfg = load(args.config, missing_ok=missing_ok)
    lang = getattr(args, "lang", None)
    if lang:
        if lang not in LANGUAGES + (AUTO,):
            raise ConfigError("--lang: unsupported language %r (supported: %s)"
                              % (lang, ", ".join(LANGUAGES + (AUTO,))))
        cfg["language"] = resolve_language(lang)
    return cfg


def _notifier(cfg: Dict[str, Any]) -> Any:
    from .notifier import TelegramNotifier
    token, chat = require_telegram(cfg)
    t = cfg["telegram"]
    return TelegramNotifier(token, chat, timeout=t["timeout"], api_url=t["api_url"],
                            tr=get_translator(cfg["language"]))


def cmd_run(args: argparse.Namespace) -> int:
    cfg = _load(args)
    _setup_logging(cfg["log_level"])
    notifier = _notifier(cfg)
    from .runner import Runner
    runner = Runner(cfg, notifier)
    stop = threading.Event()

    def _stop(signum: int, _frame: Any) -> None:
        logging.getLogger("qorovul").info("received signal %d, stopping", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    if args.once:
        runner.run_cycle()
        return EXIT_OK
    runner.run_forever(stop)
    return EXIT_OK


def cmd_test(args: argparse.Namespace) -> int:
    cfg = _load(args)
    _setup_logging("warning")
    import html

    from . import checks as checks_mod
    from .notifier import format_header
    from .runner import run_check

    tr = get_translator(cfg["language"])
    failing, errored, lines = [], [], []
    checks = checks_mod.build_checks(cfg)
    if not checks:
        print(tr("test.no_checks"))
    rows = []
    for check in checks:
        results, complete = run_check(check, tr=tr)
        if not results:
            rows.append((" ok ", check.name, tr("test.nothing")))
        for r in results:
            tag = " ok " if r.ok else ("ERR " if not complete else r.severity[:4].upper())
            rows.append((tag, r.key, r.message))
            if not complete:
                errored.append(r)
            elif not r.ok:
                failing.append(r)
    width = max([display_width(key) for _, key, _ in rows] + [20])
    for tag, key, message in rows:
        print("[%s] %s %s" % (tag, ljust(key, width), message))

    summary = tr("test.summary", checks=len(checks), failing=len(failing), errors=len(errored))
    print("\n" + summary)
    lines.append(format_header(cfg["hostname"]))
    lines.append("\U0001F9EA <b>%s</b>" % html.escape(tr("test.title", version=__version__),
                                                      quote=False))
    lines.append(html.escape(summary, quote=False))
    for r in (errored + failing)[:20]:
        lines.append("\u2022 <code>%s</code> %s" % (html.escape(r.key), html.escape(r.message)))

    try:
        notifier = _notifier(cfg)
    except ConfigError as exc:
        print("telegram: %s" % exc, file=sys.stderr)
        return EXIT_TELEGRAM
    if notifier.send_text("\n".join(lines)):
        print(tr("test.sent"))
    else:
        print(tr("test.send_failed"), file=sys.stderr)
        return EXIT_TELEGRAM
    return EXIT_CHECKS_FAILING if failing or errored else EXIT_OK


def _fmt_ts(ts: Optional[float]) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "-"


def cmd_status(args: argparse.Namespace) -> int:
    cfg = _load(args, missing_ok=True)
    from .state import StateError, StateStore
    tr = get_translator(cfg["language"])
    path = cfg["state_file"]
    try:
        records = StateStore(path).load(strict=True)
    except StateError as exc:
        hint = " (try: sudo qorovul status)" if "ermission" in str(exc) else ""
        print("qorovul: %s%s" % (exc, hint), file=sys.stderr)
        return EXIT_CHECKS_FAILING
    if args.json:
        print(json.dumps(records, indent=2, sort_keys=True, ensure_ascii=False))
        return EXIT_OK
    if not records:
        print(tr("status.empty", path=path))
        return EXIT_OK
    failing = sorted(k for k, r in records.items() if r["status"] == "failing")
    print(tr("status.summary", path=path, keys=len(records), failing=len(failing)) + "\n")
    header = tuple(tr("status.col." + c)
                   for c in ("key", "status", "severity", "since", "last", "message"))
    rows = []
    for key in failing + sorted(k for k in records if k not in failing):
        r = records[key]
        is_failing = r["status"] == "failing"
        status = tr("status.failing") if is_failing else tr("status.ok")
        if r.get("pending_recovery"):
            status += "*"
        ev = r.get("last_event")
        last = "%s %s" % (tr("kind." + ev["kind"]), _fmt_ts(ev["at"])) if ev else "-"
        since = _fmt_ts(r.get("since")) if is_failing else "-"
        sev = tr.severity(r.get("severity", "info")) if is_failing else "-"
        rows.append((key, status, sev, since, last, r.get("message", "")))
    # Column widths in terminal cells, so CJK text lines up too.
    widths = [max(display_width(row[i]) for row in [header] + rows) for i in range(5)]
    for row in [header] + rows:
        print(" ".join(ljust(cell, w) for cell, w in zip(row, widths)) + " " + row[5])
    if any(r.get("pending_recovery") for r in records.values()):
        print("\n" + tr("status.pending"))
    return EXIT_OK


def cmd_version(_args: argparse.Namespace) -> int:
    print("qorovul %s" % __version__)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    cfg_help = "config file (default: $QOROVUL_CONFIG or %s)" % DEFAULT_CONFIG_PATH
    lang_help = ("language of messages: %s or auto (default: the config's "
                 "`language`, or $QOROVUL_LANG)" % ", ".join(LANGUAGES))
    # -c and -l are accepted both before and after the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-c", "--config", default=argparse.SUPPRESS, help=cfg_help)
    common.add_argument("-l", "--lang", default=argparse.SUPPRESS, metavar="LANG",
                        help=lang_help)
    p = argparse.ArgumentParser(prog="qorovul",
                                description="Linux server watchdog with Telegram alerts")
    p.add_argument("-c", "--config", default=None, help=cfg_help)
    p.add_argument("-l", "--lang", default=None, metavar="LANG", help=lang_help)
    sub = p.add_subparsers(dest="command")
    r = sub.add_parser("run", parents=[common],
                       help="run the monitoring loop in the foreground (used by systemd)")
    r.add_argument("--once", action="store_true", help="run a single cycle and exit")
    r.set_defaults(func=cmd_run)
    sub.add_parser("test", parents=[common],
                   help="run all checks once, print results, send a test message"
                   ).set_defaults(func=cmd_test)
    s = sub.add_parser("status", parents=[common], help="show current state and last alert per key")
    s.add_argument("--json", action="store_true", help="print raw state as JSON")
    s.set_defaults(func=cmd_status)
    sub.add_parser("version", help="print version").set_defaults(func=cmd_version)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_CONFIG
    try:
        return args.func(args)
    except ConfigError as exc:
        print("qorovul: %s" % exc, file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
