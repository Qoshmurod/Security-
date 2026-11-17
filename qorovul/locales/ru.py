"""Русский."""

NAME = "Русский"
DECIMAL = ","
SIZE_UNITS = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
DURATION_UNITS = {"d": " д", "h": " ч", "m": " мин", "s": " с"}

MESSAGES = {
    "severity.info": "ИНФО",
    "severity.warning": "ВНИМАНИЕ",
    "severity.critical": "КРИТИЧНО",
    "event.recovered": "ВОССТАНОВЛЕНО",
    "event.still": "ВСЁ ЕЩЁ {severity}",
    "event.escalated": "уровень повышен",
    "footer.since": "с {time}",
    "footer.was": "уровень {severity} держался {duration}",
    "footer.failing_for": "продолжается {duration} (с {time})",

    "disk.usage": "{mount} заполнен на {percent} (свободно {free} из {total})",
    "disk.unmounted": "{mount} больше не смонтирован",
    "disk.unreadable": "не удалось получить заполненность {mount}: {error}",
    "memory.usage": "Использование ОЗУ {percent} (доступно {available} из {total})",
    "service.state": "{unit}: состояние {state}",
    "ssh.failures": "неудачные входы по SSH с {ip} за последние {window}: {count}",
    "ssh.failures_users": "неудачные входы по SSH с {ip} за последние {window}: {count} "
                          "(пользователи: {users})",
    "ssh.cleared": "неудачных входов с {ip} стало меньше {limit} за {window}",
    "ssl.expires": "сертификат {host} истекает {date}, осталось дней: {days}",
    "ssl.expired": "сертификат {host} ИСТЁК {date}",
    "ssl.invalid": "сертификат {host} недействителен: {reason}",
    "ssl.unreachable": "не удалось проверить сертификат {host}:{port}: {error}",
    "ports.unexpected": "порт TCP {port} неожиданно прослушивается ({addresses})",
    "ports.user": "пользователь {users}",
    "ports.process": "процесс {processes}",
    "ports.cleared": "порт TCP {port} больше не прослушивается",
    "check.error": "проверку {check} не удалось выполнить: {error}",
    "check.recovered": "проверка {check} снова работает нормально",
    "check.cleared": "условие больше не наблюдается",

    "test.title": "Тестовое сообщение Qorovul (v{version})",
    "test.summary": "проверок выполнено: {checks}, с проблемами: {failing}, ошибок: {errors}",
    "test.nothing": "сообщать не о чем",
    "test.no_checks": "ни одна проверка не включена",
    "test.sent": "telegram: тестовое сообщение отправлено",
    "test.send_failed": "telegram: НЕ УДАЛОСЬ отправить тестовое сообщение (см. журнал выше)",

    "status.empty": "состояния пока нет ({path})",
    "status.summary": "состояние: {path} (ключей: {keys}, с проблемами: {failing})",
    "status.col.key": "КЛЮЧ",
    "status.col.status": "СТАТУС",
    "status.col.severity": "УРОВЕНЬ",
    "status.col.since": "НАЧАЛО",
    "status.col.last": "ПОСЛЕДНЕЕ ОПОВЕЩЕНИЕ",
    "status.col.message": "СООБЩЕНИЕ",
    "status.failing": "ПРОБЛЕМА",
    "status.ok": "норма",
    "status.pending": "* восстановлено, сообщение ВОССТАНОВЛЕНО ещё не доставлено",
    "kind.alert": "оповещение",
    "kind.escalated": "повышение",
    "kind.reminder": "напоминание",
    "kind.recovered": "восстановление",
}
