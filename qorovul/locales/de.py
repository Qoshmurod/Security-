"""Deutsch."""

NAME = "Deutsch"
DECIMAL = ","
PERCENT = "{n} %"
DURATION_UNITS = {"d": " T", "h": " Std.", "m": " Min.", "s": " s"}

MESSAGES = {
    "severity.info": "INFO",
    "severity.warning": "WARNUNG",
    "severity.critical": "KRITISCH",
    "event.recovered": "BEHOBEN",
    "event.still": "WEITERHIN {severity}",
    "event.escalated": "Schweregrad erhöht",
    "footer.since": "seit {time}",
    "footer.was": "war {duration} lang {severity}",
    "footer.failing_for": "besteht seit {duration} (Beginn: {time})",

    "disk.usage": "{mount} ist zu {percent} belegt ({free} frei von {total})",
    "disk.unmounted": "{mount} ist nicht mehr eingehängt",
    "disk.unreadable": "Belegung von {mount} kann nicht gelesen werden: {error}",
    "memory.usage": "RAM-Auslastung {percent} ({available} verfügbar von {total})",
    "service.state": "{unit}: Status {state}",
    "ssh.failures": "fehlgeschlagene SSH-Anmeldungen von {ip} in den letzten {window}: {count}",
    "ssh.failures_users": "fehlgeschlagene SSH-Anmeldungen von {ip} in den letzten {window}: "
                          "{count} (Benutzer: {users})",
    "ssh.cleared": "fehlgeschlagene Anmeldungen von {ip} unter {limit} pro {window} gesunken",
    "ssl.expires": "Zertifikat von {host} läuft am {date} ab, verbleibende Tage: {days}",
    "ssl.expired": "Zertifikat von {host} ist am {date} ABGELAUFEN",
    "ssl.invalid": "Zertifikat von {host} ist ungültig: {reason}",
    "ssl.unreachable": "Zertifikat von {host}:{port} kann nicht geprüft werden: {error}",
    "ports.unexpected": "unerwarteter TCP-Listener auf Port {port} ({addresses})",
    "ports.user": "Benutzer {users}",
    "ports.process": "Prozess {processes}",
    "ports.cleared": "TCP-Port {port} lauscht nicht mehr",
    "check.error": "Prüfung {check} konnte nicht ausgeführt werden: {error}",
    "check.recovered": "Prüfung {check} läuft wieder normal",
    "check.cleared": "Zustand besteht nicht mehr",

    "test.title": "Qorovul-Testnachricht (v{version})",
    "test.summary": "ausgeführte Prüfungen: {checks}, mit Problemen: {failing}, "
                    "Fehler: {errors}",
    "test.nothing": "nichts zu melden",
    "test.no_checks": "keine Prüfungen aktiviert",
    "test.sent": "telegram: Testnachricht gesendet",
    "test.send_failed": "telegram: Testnachricht konnte NICHT gesendet werden "
                        "(siehe Protokoll oben)",

    "status.empty": "noch kein Zustand ({path})",
    "status.summary": "Zustand: {path} (Schlüssel: {keys}, mit Problemen: {failing})",
    "status.col.key": "SCHLÜSSEL",
    "status.col.status": "STATUS",
    "status.col.severity": "SCHWEREGRAD",
    "status.col.since": "SEIT",
    "status.col.last": "LETZTE MELDUNG",
    "status.col.message": "NACHRICHT",
    "status.failing": "PROBLEM",
    "status.ok": "ok",
    "status.pending": "* behoben, BEHOBEN-Nachricht noch nicht zugestellt",
    "kind.alert": "Alarm",
    "kind.escalated": "Eskalation",
    "kind.reminder": "Erinnerung",
    "kind.recovered": "Behebung",
}
