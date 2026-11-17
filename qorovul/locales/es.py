"""Español."""

NAME = "Español"
DECIMAL = ","
DURATION_UNITS = {"d": " d", "h": " h", "m": " min", "s": " s"}

MESSAGES = {
    "severity.info": "INFO",
    "severity.warning": "AVISO",
    "severity.critical": "CRÍTICO",
    "event.recovered": "RECUPERADO",
    "event.still": "TODAVÍA {severity}",
    "event.escalated": "gravedad aumentada",
    "footer.since": "desde {time}",
    "footer.was": "estuvo en {severity} durante {duration}",
    "footer.failing_for": "lleva {duration} con el problema (desde {time})",

    "disk.usage": "{mount} está lleno al {percent} ({free} libres de {total})",
    "disk.unmounted": "{mount} ya no está montado",
    "disk.unreadable": "no se puede leer el uso de disco de {mount}: {error}",
    "memory.usage": "uso de RAM {percent} ({available} disponibles de {total})",
    "service.state": "{unit}: estado {state}",
    "ssh.failures": "inicios de sesión SSH fallidos desde {ip} en los últimos {window}: "
                    "{count}",
    "ssh.failures_users": "inicios de sesión SSH fallidos desde {ip} en los últimos "
                          "{window}: {count} (usuarios: {users})",
    "ssh.cleared": "los inicios de sesión fallidos desde {ip} bajaron de {limit} por {window}",
    "ssl.expires": "el certificado de {host} caduca el {date}, días restantes: {days}",
    "ssl.expired": "el certificado de {host} CADUCÓ el {date}",
    "ssl.invalid": "el certificado de {host} no es válido: {reason}",
    "ssl.unreachable": "no se puede comprobar el certificado de {host}:{port}: {error}",
    "ports.unexpected": "escucha TCP inesperada en el puerto {port} ({addresses})",
    "ports.user": "usuario {users}",
    "ports.process": "proceso {processes}",
    "ports.cleared": "el puerto TCP {port} ya no está a la escucha",
    "check.error": "la comprobación {check} no pudo ejecutarse: {error}",
    "check.recovered": "la comprobación {check} vuelve a funcionar con normalidad",
    "check.cleared": "la condición ya no está presente",

    "test.title": "Mensaje de prueba de Qorovul (v{version})",
    "test.summary": "comprobaciones ejecutadas: {checks}, con problemas: {failing}, "
                    "errores: {errors}",
    "test.nothing": "nada que informar",
    "test.no_checks": "no hay comprobaciones activadas",
    "test.sent": "telegram: mensaje de prueba enviado",
    "test.send_failed": "telegram: NO se pudo enviar el mensaje de prueba "
                        "(consulte el registro de arriba)",

    "status.empty": "todavía no hay estado ({path})",
    "status.summary": "estado: {path} (claves: {keys}, con problemas: {failing})",
    "status.col.key": "CLAVE",
    "status.col.status": "ESTADO",
    "status.col.severity": "GRAVEDAD",
    "status.col.since": "DESDE",
    "status.col.last": "ÚLTIMO AVISO",
    "status.col.message": "MENSAJE",
    "status.failing": "PROBLEMA",
    "status.ok": "ok",
    "status.pending": "* recuperado, el mensaje RECUPERADO aún no se ha entregado",
    "kind.alert": "alerta",
    "kind.escalated": "escalado",
    "kind.reminder": "recordatorio",
    "kind.recovered": "recuperado",
}
