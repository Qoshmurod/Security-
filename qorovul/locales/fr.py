"""Français."""

NAME = "Français"
DECIMAL = ","
PERCENT = "{n} %"
SIZE_UNITS = ["o", "Ko", "Mo", "Go", "To"]
DURATION_UNITS = {"d": " j", "h": " h", "m": " min", "s": " s"}

MESSAGES = {
    "severity.info": "INFO",
    "severity.warning": "AVERTISSEMENT",
    "severity.critical": "CRITIQUE",
    "event.recovered": "RÉTABLI",
    "event.still": "TOUJOURS {severity}",
    "event.escalated": "gravité accrue",
    "footer.since": "depuis {time}",
    "footer.was": "en {severity} pendant {duration}",
    "footer.failing_for": "problème en cours depuis {duration} (début : {time})",

    "disk.usage": "{mount} est rempli à {percent} ({free} libres sur {total})",
    "disk.unmounted": "{mount} n'est plus monté",
    "disk.unreadable": "impossible de lire l'occupation disque de {mount} : {error}",
    "memory.usage": "utilisation de la RAM {percent} ({available} disponibles sur {total})",
    "service.state": "{unit} : état {state}",
    "ssh.failures": "connexions SSH échouées depuis {ip} sur les dernières {window} : "
                    "{count}",
    "ssh.failures_users": "connexions SSH échouées depuis {ip} sur les dernières "
                          "{window} : {count} (utilisateurs : {users})",
    "ssh.cleared": "les connexions échouées depuis {ip} sont passées sous {limit} par {window}",
    "ssl.expires": "le certificat de {host} expire le {date}, jours restants : {days}",
    "ssl.expired": "le certificat de {host} a EXPIRÉ le {date}",
    "ssl.invalid": "le certificat de {host} n'est pas valide : {reason}",
    "ssl.unreachable": "impossible de vérifier le certificat de {host}:{port} : {error}",
    "ports.unexpected": "écoute TCP inattendue sur le port {port} ({addresses})",
    "ports.user": "utilisateur {users}",
    "ports.process": "processus {processes}",
    "ports.cleared": "le port TCP {port} n'est plus en écoute",
    "check.error": "la vérification {check} n'a pas pu s'exécuter : {error}",
    "check.recovered": "la vérification {check} fonctionne de nouveau normalement",
    "check.cleared": "la condition n'est plus présente",

    "test.title": "Message de test Qorovul (v{version})",
    "test.summary": "vérifications exécutées : {checks}, en échec : {failing}, "
                    "erreurs : {errors}",
    "test.nothing": "rien à signaler",
    "test.no_checks": "aucune vérification activée",
    "test.sent": "telegram : message de test envoyé",
    "test.send_failed": "telegram : ÉCHEC de l'envoi du message de test "
                        "(voir le journal ci-dessus)",

    "status.empty": "pas encore d'état ({path})",
    "status.summary": "état : {path} (clés : {keys}, en échec : {failing})",
    "status.col.key": "CLÉ",
    "status.col.status": "ÉTAT",
    "status.col.severity": "GRAVITÉ",
    "status.col.since": "DEPUIS",
    "status.col.last": "DERNIÈRE ALERTE",
    "status.col.message": "MESSAGE",
    "status.failing": "ÉCHEC",
    "status.ok": "ok",
    "status.pending": "* rétabli, message RÉTABLI pas encore envoyé",
    "kind.alert": "alerte",
    "kind.escalated": "aggravation",
    "kind.reminder": "rappel",
    "kind.recovered": "rétablissement",
}
