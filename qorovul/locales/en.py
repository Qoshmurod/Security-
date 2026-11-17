"""English - the reference catalog every other language is checked against."""

NAME = "English"
SIZE_UNITS = ["B", "KB", "MB", "GB", "TB"]
DURATION_UNITS = {"d": "d", "h": "h", "m": "m", "s": "s"}

MESSAGES = {
    # Telegram message parts
    "severity.info": "INFO",
    "severity.warning": "WARNING",
    "severity.critical": "CRITICAL",
    "event.recovered": "RECOVERED",
    "event.still": "STILL {severity}",
    "event.escalated": "escalated",
    "footer.since": "since {time}",
    "footer.was": "was {severity} for {duration}",
    "footer.failing_for": "failing for {duration} (since {time})",

    # check results
    "disk.usage": "{mount} is {percent} full ({free} free of {total})",
    "disk.unmounted": "{mount} is no longer mounted",
    "disk.unreadable": "cannot read disk usage of {mount}: {error}",
    "memory.usage": "RAM usage {percent} ({available} available of {total})",
    "service.state": "{unit} is {state}",
    "ssh.failures": "failed SSH logins from {ip} in the last {window}: {count}",
    "ssh.failures_users": "failed SSH logins from {ip} in the last {window}: {count} "
                          "(users: {users})",
    "ssh.cleared": "failed logins from {ip} dropped below {limit} per {window}",
    "ssl.expires": "{host} certificate expires on {date}, days left: {days}",
    "ssl.expired": "{host} certificate EXPIRED on {date}",
    "ssl.invalid": "{host} certificate is not valid: {reason}",
    "ssl.unreachable": "cannot check certificate of {host}:{port}: {error}",
    "ports.unexpected": "unexpected TCP listener on port {port} ({addresses})",
    "ports.user": "user {users}",
    "ports.process": "process {processes}",
    "ports.cleared": "TCP port {port} is no longer listening",
    "check.error": "{check} check could not run: {error}",
    "check.recovered": "{check} check is running normally again",
    "check.cleared": "condition no longer present",

    # qorovul test
    "test.title": "Qorovul test message (v{version})",
    "test.summary": "checks run: {checks}, failing: {failing}, errors: {errors}",
    "test.nothing": "nothing to report",
    "test.no_checks": "no checks enabled",
    "test.sent": "telegram: test message sent",
    "test.send_failed": "telegram: FAILED to send the test message (see the log above)",

    # qorovul status
    "status.empty": "no state yet ({path})",
    "status.summary": "state: {path} (keys: {keys}, failing: {failing})",
    "status.col.key": "KEY",
    "status.col.status": "STATUS",
    "status.col.severity": "SEVERITY",
    "status.col.since": "SINCE",
    "status.col.last": "LAST ALERT",
    "status.col.message": "MESSAGE",
    "status.failing": "FAILING",
    "status.ok": "ok",
    "status.pending": "* recovered, RECOVERED message not delivered yet",
    "kind.alert": "alert",
    "kind.escalated": "escalated",
    "kind.reminder": "reminder",
    "kind.recovered": "recovered",
}
