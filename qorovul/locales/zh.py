"""简体中文."""

NAME = "简体中文"
DURATION_UNITS = {"d": "天", "h": "小时", "m": "分", "s": "秒"}
DURATION_JOIN = ""
LIST_SEP = "，"

MESSAGES = {
    "severity.info": "信息",
    "severity.warning": "警告",
    "severity.critical": "严重",
    "event.recovered": "已恢复",
    "event.still": "仍为{severity}",
    "event.escalated": "级别升高",
    "footer.since": "开始于 {time}",
    "footer.was": "{severity}状态持续了 {duration}",
    "footer.failing_for": "已持续 {duration}（开始于 {time}）",

    "disk.usage": "{mount} 已用 {percent}（可用 {free}，共 {total}）",
    "disk.unmounted": "{mount} 已不再挂载",
    "disk.unreadable": "无法读取 {mount} 的磁盘用量：{error}",
    "memory.usage": "内存使用率 {percent}（可用 {available}，共 {total}）",
    "service.state": "{unit} 状态：{state}",
    "ssh.failures": "最近 {window} 内来自 {ip} 的 SSH 登录失败次数：{count}",
    "ssh.failures_users": "最近 {window} 内来自 {ip} 的 SSH 登录失败次数：{count}"
                          "（用户：{users}）",
    "ssh.cleared": "来自 {ip} 的登录失败已降至每 {window} 少于 {limit} 次",
    "ssl.expires": "{host} 证书将于 {date} 到期，剩余天数：{days}",
    "ssl.expired": "{host} 证书已于 {date} 过期",
    "ssl.invalid": "{host} 证书无效：{reason}",
    "ssl.unreachable": "无法检查 {host}:{port} 的证书：{error}",
    "ports.unexpected": "端口 {port} 上出现意外的 TCP 监听（{addresses}）",
    "ports.user": "用户 {users}",
    "ports.process": "进程 {processes}",
    "ports.cleared": "TCP 端口 {port} 已不再监听",
    "check.error": "{check} 检查无法运行：{error}",
    "check.recovered": "{check} 检查已恢复正常运行",
    "check.cleared": "该状况已不存在",

    "test.title": "Qorovul 测试消息（v{version}）",
    "test.summary": "已运行检查：{checks}，异常：{failing}，错误：{errors}",
    "test.nothing": "无可报告内容",
    "test.no_checks": "未启用任何检查",
    "test.sent": "telegram：测试消息已发送",
    "test.send_failed": "telegram：测试消息发送失败（见上方日志）",

    "status.empty": "暂无状态（{path}）",
    "status.summary": "状态：{path}（键：{keys}，异常：{failing}）",
    "status.col.key": "键",
    "status.col.status": "状态",
    "status.col.severity": "级别",
    "status.col.since": "开始",
    "status.col.last": "最近通知",
    "status.col.message": "消息",
    "status.failing": "异常",
    "status.ok": "正常",
    "status.pending": "* 已恢复，恢复消息尚未送达",
    "kind.alert": "告警",
    "kind.escalated": "升级",
    "kind.reminder": "提醒",
    "kind.recovered": "恢复",
}
