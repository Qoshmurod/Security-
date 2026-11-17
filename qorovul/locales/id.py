"""Bahasa Indonesia."""

NAME = "Bahasa Indonesia"
DECIMAL = ","
DURATION_UNITS = {"d": " hr", "h": " j", "m": " mnt", "s": " dtk"}

MESSAGES = {
    "severity.info": "INFO",
    "severity.warning": "PERINGATAN",
    "severity.critical": "KRITIS",
    "event.recovered": "PULIH",
    "event.still": "MASIH {severity}",
    "event.escalated": "tingkat naik",
    "footer.since": "sejak {time}",
    "footer.was": "{severity} selama {duration}",
    "footer.failing_for": "bermasalah selama {duration} (sejak {time})",

    "disk.usage": "{mount} terisi {percent} ({free} kosong dari {total})",
    "disk.unmounted": "{mount} tidak lagi terpasang",
    "disk.unreadable": "tidak dapat membaca penggunaan disk {mount}: {error}",
    "memory.usage": "penggunaan RAM {percent} ({available} tersedia dari {total})",
    "service.state": "{unit}: status {state}",
    "ssh.failures": "login SSH gagal dari {ip} dalam {window} terakhir: {count}",
    "ssh.failures_users": "login SSH gagal dari {ip} dalam {window} terakhir: {count} "
                          "(pengguna: {users})",
    "ssh.cleared": "login gagal dari {ip} turun di bawah {limit} per {window}",
    "ssl.expires": "sertifikat {host} kedaluwarsa pada {date}, sisa hari: {days}",
    "ssl.expired": "sertifikat {host} KEDALUWARSA pada {date}",
    "ssl.invalid": "sertifikat {host} tidak valid: {reason}",
    "ssl.unreachable": "tidak dapat memeriksa sertifikat {host}:{port}: {error}",
    "ports.unexpected": "listener TCP tak terduga di port {port} ({addresses})",
    "ports.user": "pengguna {users}",
    "ports.process": "proses {processes}",
    "ports.cleared": "port TCP {port} tidak lagi mendengarkan",
    "check.error": "pemeriksaan {check} tidak dapat dijalankan: {error}",
    "check.recovered": "pemeriksaan {check} kembali berjalan normal",
    "check.cleared": "kondisi sudah tidak ada",

    "test.title": "Pesan uji Qorovul (v{version})",
    "test.summary": "pemeriksaan dijalankan: {checks}, bermasalah: {failing}, galat: {errors}",
    "test.nothing": "tidak ada yang perlu dilaporkan",
    "test.no_checks": "tidak ada pemeriksaan yang aktif",
    "test.sent": "telegram: pesan uji terkirim",
    "test.send_failed": "telegram: GAGAL mengirim pesan uji (lihat log di atas)",

    "status.empty": "belum ada status ({path})",
    "status.summary": "status: {path} (kunci: {keys}, bermasalah: {failing})",
    "status.col.key": "KUNCI",
    "status.col.status": "STATUS",
    "status.col.severity": "TINGKAT",
    "status.col.since": "SEJAK",
    "status.col.last": "PERINGATAN TERAKHIR",
    "status.col.message": "PESAN",
    "status.failing": "BERMASALAH",
    "status.ok": "ok",
    "status.pending": "* pulih, pesan PULIH belum terkirim",
    "kind.alert": "peringatan",
    "kind.escalated": "eskalasi",
    "kind.reminder": "pengingat",
    "kind.recovered": "pemulihan",
}
