"""Oʻzbekcha (lotin yozuvi)."""

NAME = "Oʻzbekcha"
DECIMAL = ","
DURATION_UNITS = {"d": " kun", "h": " soat", "m": " daq", "s": " s"}

MESSAGES = {
    "severity.info": "MAʼLUMOT",
    "severity.warning": "OGOHLANTIRISH",
    "severity.critical": "KRITIK",
    "event.recovered": "TIKLANDI",
    "event.still": "HAMON {severity}",
    "event.escalated": "darajasi oshdi",
    "footer.since": "boshlangan: {time}",
    "footer.was": "{duration} davomida {severity} holatida edi",
    "footer.failing_for": "{duration} davom etmoqda (boshlangan: {time})",

    "disk.usage": "{mount} {percent} toʻlgan (boʻsh: {free}, jami: {total})",
    "disk.unmounted": "{mount} endi ulanmagan",
    "disk.unreadable": "{mount} bandligini oʻqib boʻlmadi: {error}",
    "memory.usage": "Operativ xotira bandligi {percent} (boʻsh: {available}, jami: {total})",
    "service.state": "{unit} holati: {state}",
    "ssh.failures": "{ip} manzilidan oxirgi {window} ichidagi muvaffaqiyatsiz SSH kirishlar: "
                    "{count}",
    "ssh.failures_users": "{ip} manzilidan oxirgi {window} ichidagi muvaffaqiyatsiz SSH "
                          "kirishlar: {count} (foydalanuvchilar: {users})",
    "ssh.cleared": "{ip} manzilidan muvaffaqiyatsiz kirishlar {window} ichida {limit} tadan "
                   "kamaydi",
    "ssl.expires": "{host} sertifikati {date} kuni tugaydi, qolgan kunlar: {days}",
    "ssl.expired": "{host} sertifikatining muddati {date} kuni TUGAGAN",
    "ssl.invalid": "{host} sertifikati yaroqsiz: {reason}",
    "ssl.unreachable": "{host}:{port} sertifikatini tekshirib boʻlmadi: {error}",
    "ports.unexpected": "{port}-portda kutilmagan TCP tinglovchi ({addresses})",
    "ports.user": "foydalanuvchi {users}",
    "ports.process": "jarayon {processes}",
    "ports.cleared": "TCP {port}-port endi tinglanmayapti",
    "check.error": "{check} tekshiruvini bajarib boʻlmadi: {error}",
    "check.recovered": "{check} tekshiruvi yana odatdagidek ishlayapti",
    "check.cleared": "bu holat endi kuzatilmayapti",

    "test.title": "Qorovul sinov xabari (v{version})",
    "test.summary": "bajarilgan tekshiruvlar: {checks}, muammoli: {failing}, xatolar: {errors}",
    "test.nothing": "xabar beradigan narsa yoʻq",
    "test.no_checks": "birorta tekshiruv yoqilmagan",
    "test.sent": "telegram: sinov xabari yuborildi",
    "test.send_failed": "telegram: sinov xabarini yuborib BOʻLMADI (yuqoridagi logga qarang)",

    "status.empty": "hali holat yoʻq ({path})",
    "status.summary": "holat: {path} (kalitlar: {keys}, muammoli: {failing})",
    "status.col.key": "KALIT",
    "status.col.status": "HOLAT",
    "status.col.severity": "DARAJA",
    "status.col.since": "BOSHLANGAN",
    "status.col.last": "OXIRGI XABAR",
    "status.col.message": "TAVSIF",
    "status.failing": "MUAMMO",
    "status.ok": "joyida",
    "status.pending": "* tiklandi, lekin TIKLANDI xabari hali yuborilmagan",
    "kind.alert": "ogohlantirish",
    "kind.escalated": "daraja oshdi",
    "kind.reminder": "eslatma",
    "kind.recovered": "tiklandi",
}
