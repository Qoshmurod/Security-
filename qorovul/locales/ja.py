"""日本語."""

NAME = "日本語"
DURATION_UNITS = {"d": "日", "h": "時間", "m": "分", "s": "秒"}
DURATION_JOIN = ""
LIST_SEP = "、"

MESSAGES = {
    "severity.info": "情報",
    "severity.warning": "警告",
    "severity.critical": "重大",
    "event.recovered": "復旧",
    "event.still": "継続中：{severity}",
    "event.escalated": "重大度が上昇",
    "footer.since": "開始 {time}",
    "footer.was": "{severity} の状態が {duration} 続きました",
    "footer.failing_for": "{duration} 継続中（開始 {time}）",

    "disk.usage": "{mount} の使用率 {percent}（空き {free} / 合計 {total}）",
    "disk.unmounted": "{mount} はマウントされていません",
    "disk.unreadable": "{mount} のディスク使用量を取得できません：{error}",
    "memory.usage": "メモリ使用率 {percent}（利用可能 {available} / 合計 {total}）",
    "service.state": "{unit} の状態：{state}",
    "ssh.failures": "直近 {window} の {ip} からの SSH ログイン失敗：{count} 回",
    "ssh.failures_users": "直近 {window} の {ip} からの SSH ログイン失敗：{count} 回"
                          "（ユーザー：{users}）",
    "ssh.cleared": "{ip} からのログイン失敗が {window} あたり {limit} 回未満に減少しました",
    "ssl.expires": "{host} の証明書の有効期限は {date}、残り日数：{days}",
    "ssl.expired": "{host} の証明書は {date} に期限切れになりました",
    "ssl.invalid": "{host} の証明書が無効です：{reason}",
    "ssl.unreachable": "{host}:{port} の証明書を確認できません：{error}",
    "ports.unexpected": "ポート {port} で想定外の TCP 待ち受け（{addresses}）",
    "ports.user": "ユーザー {users}",
    "ports.process": "プロセス {processes}",
    "ports.cleared": "TCP ポート {port} の待ち受けは終了しました",
    "check.error": "{check} チェックを実行できません：{error}",
    "check.recovered": "{check} チェックは正常に戻りました",
    "check.cleared": "この状態は解消されました",

    "test.title": "Qorovul テストメッセージ（v{version}）",
    "test.summary": "実行したチェック：{checks}、異常：{failing}、エラー：{errors}",
    "test.nothing": "報告事項なし",
    "test.no_checks": "有効なチェックがありません",
    "test.sent": "telegram：テストメッセージを送信しました",
    "test.send_failed": "telegram：テストメッセージの送信に失敗しました（上のログを参照）",

    "status.empty": "状態はまだありません（{path}）",
    "status.summary": "状態：{path}（キー：{keys}、異常：{failing}）",
    "status.col.key": "キー",
    "status.col.status": "状態",
    "status.col.severity": "重大度",
    "status.col.since": "開始",
    "status.col.last": "最終通知",
    "status.col.message": "メッセージ",
    "status.failing": "異常",
    "status.ok": "正常",
    "status.pending": "* 復旧済み、復旧メッセージは未送信",
    "kind.alert": "アラート",
    "kind.escalated": "上昇",
    "kind.reminder": "リマインド",
    "kind.recovered": "復旧",
}
