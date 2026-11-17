"""العربية."""

NAME = "العربية"
DURATION_UNITS = {"d": " ي", "h": " س", "m": " د", "s": " ث"}
LIST_SEP = "، "

MESSAGES = {
    "severity.info": "معلومات",
    "severity.warning": "تحذير",
    "severity.critical": "حرج",
    "event.recovered": "تمت الاستعادة",
    "event.still": "لا يزال {severity}",
    "event.escalated": "ارتفعت الخطورة",
    "footer.since": "منذ {time}",
    "footer.was": "كان {severity} لمدة {duration}",
    "footer.failing_for": "مستمر منذ {duration} (البداية: {time})",

    "disk.usage": "{mount} ممتلئ بنسبة {percent} (المتاح {free} من {total})",
    "disk.unmounted": "{mount} لم يعد مُركّبًا",
    "disk.unreadable": "تعذّرت قراءة استخدام القرص لـ {mount}: {error}",
    "memory.usage": "استخدام الذاكرة {percent} (المتاح {available} من {total})",
    "service.state": "{unit}: الحالة {state}",
    "ssh.failures": "محاولات دخول SSH الفاشلة من {ip} خلال آخر {window}: {count}",
    "ssh.failures_users": "محاولات دخول SSH الفاشلة من {ip} خلال آخر {window}: {count} "
                          "(المستخدمون: {users})",
    "ssh.cleared": "انخفضت محاولات الدخول الفاشلة من {ip} إلى أقل من {limit} لكل {window}",
    "ssl.expires": "تنتهي شهادة {host} في {date}، الأيام المتبقية: {days}",
    "ssl.expired": "انتهت صلاحية شهادة {host} في {date}",
    "ssl.invalid": "شهادة {host} غير صالحة: {reason}",
    "ssl.unreachable": "تعذّر فحص شهادة {host}:{port}: {error}",
    "ports.unexpected": "منفذ TCP غير متوقع قيد الاستماع: {port} ({addresses})",
    "ports.user": "المستخدم {users}",
    "ports.process": "العملية {processes}",
    "ports.cleared": "لم يعد منفذ TCP {port} قيد الاستماع",
    "check.error": "تعذّر تشغيل فحص {check}: {error}",
    "check.recovered": "عاد فحص {check} إلى العمل بشكل طبيعي",
    "check.cleared": "لم تعد الحالة قائمة",

    "test.title": "رسالة اختبار من Qorovul (v{version})",
    "test.summary": "الفحوصات المنفذة: {checks}، بها مشكلات: {failing}، أخطاء: {errors}",
    "test.nothing": "لا شيء للإبلاغ عنه",
    "test.no_checks": "لا توجد فحوصات مفعّلة",
    "test.sent": "telegram: تم إرسال رسالة الاختبار",
    "test.send_failed": "telegram: فشل إرسال رسالة الاختبار (راجع السجل أعلاه)",

    "status.empty": "لا توجد حالة بعد ({path})",
    "status.summary": "الحالة: {path} (المفاتيح: {keys}، بها مشكلات: {failing})",
    "status.col.key": "المفتاح",
    "status.col.status": "الحالة",
    "status.col.severity": "الخطورة",
    "status.col.since": "منذ",
    "status.col.last": "آخر تنبيه",
    "status.col.message": "الرسالة",
    "status.failing": "مشكلة",
    "status.ok": "سليم",
    "status.pending": "* تمت الاستعادة، لم تُرسل رسالة الاستعادة بعد",
    "kind.alert": "تنبيه",
    "kind.escalated": "تصعيد",
    "kind.reminder": "تذكير",
    "kind.recovered": "استعادة",
}
