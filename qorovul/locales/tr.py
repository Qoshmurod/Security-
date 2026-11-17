"""Türkçe."""

NAME = "Türkçe"
DECIMAL = ","
PERCENT = "%{n}"
DURATION_UNITS = {"d": " g", "h": " sa", "m": " dk", "s": " sn"}

MESSAGES = {
    "severity.info": "BİLGİ",
    "severity.warning": "UYARI",
    "severity.critical": "KRİTİK",
    "event.recovered": "DÜZELDİ",
    "event.still": "HÂLÂ {severity}",
    "event.escalated": "seviye yükseldi",
    "footer.since": "başlangıç: {time}",
    "footer.was": "{duration} boyunca {severity} durumundaydı",
    "footer.failing_for": "{duration} süredir devam ediyor (başlangıç: {time})",

    "disk.usage": "{mount} {percent} dolu (boş: {free}, toplam: {total})",
    "disk.unmounted": "{mount} artık bağlı değil",
    "disk.unreadable": "{mount} disk kullanımı okunamadı: {error}",
    "memory.usage": "RAM kullanımı {percent} (kullanılabilir: {available}, toplam: {total})",
    "service.state": "{unit} durumu: {state}",
    "ssh.failures": "son {window} içinde {ip} adresinden başarısız SSH girişleri: {count}",
    "ssh.failures_users": "son {window} içinde {ip} adresinden başarısız SSH girişleri: "
                          "{count} (kullanıcılar: {users})",
    "ssh.cleared": "{ip} adresinden başarısız girişler {window} başına {limit} altına düştü",
    "ssl.expires": "{host} sertifikasının süresi {date} tarihinde doluyor, kalan gün: {days}",
    "ssl.expired": "{host} sertifikasının süresi {date} tarihinde DOLDU",
    "ssl.invalid": "{host} sertifikası geçersiz: {reason}",
    "ssl.unreachable": "{host}:{port} sertifikası kontrol edilemedi: {error}",
    "ports.unexpected": "{port} numaralı portta beklenmeyen TCP dinleyicisi ({addresses})",
    "ports.user": "kullanıcı {users}",
    "ports.process": "süreç {processes}",
    "ports.cleared": "TCP {port} portu artık dinlenmiyor",
    "check.error": "{check} denetimi çalıştırılamadı: {error}",
    "check.recovered": "{check} denetimi yeniden normal çalışıyor",
    "check.cleared": "durum artık gözlenmiyor",

    "test.title": "Qorovul test mesajı (v{version})",
    "test.summary": "çalıştırılan denetim: {checks}, sorunlu: {failing}, hata: {errors}",
    "test.nothing": "bildirilecek bir şey yok",
    "test.no_checks": "etkin denetim yok",
    "test.sent": "telegram: test mesajı gönderildi",
    "test.send_failed": "telegram: test mesajı GÖNDERİLEMEDİ (yukarıdaki günlüğe bakın)",

    "status.empty": "henüz durum bilgisi yok ({path})",
    "status.summary": "durum: {path} (anahtar: {keys}, sorunlu: {failing})",
    "status.col.key": "ANAHTAR",
    "status.col.status": "DURUM",
    "status.col.severity": "SEVİYE",
    "status.col.since": "BAŞLANGIÇ",
    "status.col.last": "SON BİLDİRİM",
    "status.col.message": "MESAJ",
    "status.failing": "SORUNLU",
    "status.ok": "normal",
    "status.pending": "* düzeldi, DÜZELDİ mesajı henüz iletilmedi",
    "kind.alert": "uyarı",
    "kind.escalated": "yükselme",
    "kind.reminder": "hatırlatma",
    "kind.recovered": "düzelme",
}
