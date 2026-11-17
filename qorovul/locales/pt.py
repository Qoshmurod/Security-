"""Português."""

NAME = "Português"
DECIMAL = ","
DURATION_UNITS = {"d": " d", "h": " h", "m": " min", "s": " s"}

MESSAGES = {
    "severity.info": "INFO",
    "severity.warning": "AVISO",
    "severity.critical": "CRÍTICO",
    "event.recovered": "RECUPERADO",
    "event.still": "AINDA {severity}",
    "event.escalated": "gravidade aumentou",
    "footer.since": "desde {time}",
    "footer.was": "ficou em {severity} por {duration}",
    "footer.failing_for": "com problema há {duration} (desde {time})",

    "disk.usage": "{mount} está {percent} cheio ({free} livres de {total})",
    "disk.unmounted": "{mount} não está mais montado",
    "disk.unreadable": "não foi possível ler o uso de disco de {mount}: {error}",
    "memory.usage": "uso de RAM {percent} ({available} disponíveis de {total})",
    "service.state": "{unit}: estado {state}",
    "ssh.failures": "logins SSH com falha de {ip} nos últimos {window}: {count}",
    "ssh.failures_users": "logins SSH com falha de {ip} nos últimos {window}: {count} "
                          "(usuários: {users})",
    "ssh.cleared": "as falhas de login de {ip} caíram abaixo de {limit} por {window}",
    "ssl.expires": "o certificado de {host} expira em {date}, dias restantes: {days}",
    "ssl.expired": "o certificado de {host} EXPIROU em {date}",
    "ssl.invalid": "o certificado de {host} não é válido: {reason}",
    "ssl.unreachable": "não foi possível verificar o certificado de {host}:{port}: {error}",
    "ports.unexpected": "escuta TCP inesperada na porta {port} ({addresses})",
    "ports.user": "usuário {users}",
    "ports.process": "processo {processes}",
    "ports.cleared": "a porta TCP {port} não está mais em escuta",
    "check.error": "a verificação {check} não pôde ser executada: {error}",
    "check.recovered": "a verificação {check} voltou a funcionar normalmente",
    "check.cleared": "a condição não está mais presente",

    "test.title": "Mensagem de teste do Qorovul (v{version})",
    "test.summary": "verificações executadas: {checks}, com problema: {failing}, "
                    "erros: {errors}",
    "test.nothing": "nada a relatar",
    "test.no_checks": "nenhuma verificação ativada",
    "test.sent": "telegram: mensagem de teste enviada",
    "test.send_failed": "telegram: FALHA ao enviar a mensagem de teste (veja o log acima)",

    "status.empty": "ainda não há estado ({path})",
    "status.summary": "estado: {path} (chaves: {keys}, com problema: {failing})",
    "status.col.key": "CHAVE",
    "status.col.status": "STATUS",
    "status.col.severity": "GRAVIDADE",
    "status.col.since": "DESDE",
    "status.col.last": "ÚLTIMO ALERTA",
    "status.col.message": "MENSAGEM",
    "status.failing": "PROBLEMA",
    "status.ok": "ok",
    "status.pending": "* recuperado, mensagem RECUPERADO ainda não entregue",
    "kind.alert": "alerta",
    "kind.escalated": "escalada",
    "kind.reminder": "lembrete",
    "kind.recovered": "recuperação",
}
