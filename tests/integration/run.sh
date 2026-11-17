#!/usr/bin/env bash
# End-to-end test of Qorovul on a machine running real systemd.
#
# DESTRUCTIVE - meant for CI runners, VMs and throw-away containers only. It
# installs qorovul, creates a dummy unit, mounts a tmpfs, adds a test CA to
# the system trust store and makes failed SSH logins against the local sshd.
# Nothing here talks to the real Telegram API.
#
#   sudo QOROVUL_CI=1 tests/integration/run.sh
#
# Requires: systemd as PID 1, python3, openssl, sshd + ssh client.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HELPER="$SRC/tests/integration/helper.py"
QOROVUL=/usr/local/bin/qorovul
API=18080 TLS_BAD=18443 TLS_SOON=18444 ROGUE=18999 ROGUE2=18998
MNT=/mnt/qci-disk
TRUST_DEB=/usr/local/share/ca-certificates/qorovul-ci.crt
TRUST_EL=/etc/pki/ca-trust/source/anchors/qorovul-ci.crt
PIDS=()

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 2; }
[ "${QOROVUL_CI:-}" = 1 ] || { echo "refusing to run: this modifies the system. Set QOROVUL_CI=1." >&2; exit 2; }
[ "$(ps -o comm= -p 1)" = systemd ] || { echo "systemd is not PID 1" >&2; exit 2; }

WORK="$(mktemp -d)"
TG="$WORK/telegram.jsonl"

step() { printf '\n\033[1;34m### %s\033[0m\n' "$*"; }
ok()   { printf '  \033[1;32mok\033[0m    %s\n' "$*"; }

diagnostics() {
    printf '\n=========== DIAGNOSTICS ===========\n'
    systemctl --no-pager --full status qorovul 2>&1 | head -25 || true
    echo "--- journal"
    journalctl --no-pager -u qorovul -n 120 2>&1 || true
    echo "--- status"
    "$QOROVUL" status 2>&1 || true
    echo "--- messages sent"
    python3 "$HELPER" show "$TG" 2>&1 || true
}
fail() { printf '  \033[1;31mFAIL\033[0m  %s\n' "$*" >&2; diagnostics; exit 1; }

cleanup() {
    local p
    for p in "${PIDS[@]:-}"; do
        if [ -n "$p" ]; then kill "$p" 2>/dev/null || true; fi
    done
    pkill -f "http.server $ROGUE" 2>/dev/null || true
    pkill -f "http.server $ROGUE2" 2>/dev/null || true
    systemctl stop qci-dummy.service 2>/dev/null || true
    rm -f /etc/systemd/system/qci-dummy.service
    rm -rf /etc/systemd/system/qorovul.service.d
    umount "$MNT" 2>/dev/null || true
    if [ -f "$TRUST_DEB" ]; then rm -f "$TRUST_DEB"; update-ca-certificates >/dev/null 2>&1 || true; fi
    if [ -f "$TRUST_EL" ]; then rm -f "$TRUST_EL"; update-ca-trust 2>/dev/null || true; fi
    systemctl daemon-reload 2>/dev/null || true
    rm -rf "$WORK"
}
trap cleanup EXIT

count() { python3 "$HELPER" count "$TG" "$1" "$2"; }
expect_event() {  # kind key [timeout]
    python3 "$HELPER" wait "$TG" "$1" "$2" "${3:-60}" || fail "no '$1' for $2 within ${3:-60}s"
    ok "$1 $2"
}
expect_count() {  # kind key n
    local n
    n="$(count "$1" "$2")"
    [ "$n" = "$3" ] || fail "expected $3 x '$1' for $2, got $n"
    ok "$2: '$1' sent exactly $3 time(s)"
}
field() {  # key field -> value from `qorovul status --json`
    "$QOROVUL" status --json | python3 -c '
import json, sys
rec = json.load(sys.stdin).get(sys.argv[1])
print("" if rec is None else rec.get(sys.argv[2]))' "$1" "$2"
}
expect_state() {  # key status [severity] [message-regex]
    local st sev msg
    st="$(field "$1" status)"
    [ "$st" = "$2" ] || fail "$1: expected status $2, got '${st:-<missing>}'"
    if [ -n "${3:-}" ]; then
        sev="$(field "$1" severity)"
        [ "$sev" = "$3" ] || fail "$1: expected severity $3, got '$sev'"
    fi
    if [ -n "${4:-}" ]; then
        msg="$(field "$1" message)"
        printf '%s' "$msg" | grep -Eq -- "$4" || fail "$1: message '$msg' does not match /$4/"
    fi
    ok "$1 is $2${3:+ ($3)}: $(field "$1" message)"
}
keys_matching() {  # python expression over key `k`
    "$QOROVUL" status --json | python3 -c '
import json, sys
print(" ".join(sorted(k for k in json.load(sys.stdin) if eval(sys.argv[1]))))' "$1"
}
service_active() { [ "$(systemctl is-active qorovul)" = active ] || fail "qorovul.service is not active"; }
main_pid() { systemctl show -p MainPID --value qorovul; }

# ---------------------------------------------------------------------------
step "prepare: fake Telegram API, TLS servers, dummy unit, sshd, small filesystem"

python3 "$HELPER" serve "$API" "$TG" & PIDS+=($!)

(
    cd "$WORK"
    # 1) self-signed certificate -> must be reported as "not valid"
    openssl req -x509 -newkey rsa:2048 -nodes -keyout self.key -out self.crt -days 365 \
        -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost" 2>/dev/null
    # 2) properly signed by a trusted CA but expiring in 10 days -> "days left"
    #    Extensions as a public CA would set them, so the chain is valid even
    #    under the strictest verification.
    openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.crt -days 3650 \
        -subj "/CN=Qorovul CI Root" \
        -addext "basicConstraints=critical,CA:TRUE" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
    openssl req -newkey rsa:2048 -nodes -keyout leaf.key -out leaf.csr -subj "/CN=localhost" 2>/dev/null
    printf '%s\n' "subjectAltName=DNS:localhost" "basicConstraints=critical,CA:FALSE" \
        "keyUsage=critical,digitalSignature,keyEncipherment" "extendedKeyUsage=serverAuth" \
        "subjectKeyIdentifier=hash" "authorityKeyIdentifier=keyid,issuer" > leaf.ext
    openssl x509 -req -in leaf.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out leaf.crt \
        -days 10 -extfile leaf.ext 2>/dev/null
)
if command -v update-ca-certificates >/dev/null; then
    cp "$WORK/ca.crt" "$TRUST_DEB"; update-ca-certificates >/dev/null
else
    cp "$WORK/ca.crt" "$TRUST_EL"; update-ca-trust
fi
python3 "$HELPER" tls "$TLS_BAD" "$WORK/self.crt" "$WORK/self.key" & PIDS+=($!)
python3 "$HELPER" tls "$TLS_SOON" "$WORK/leaf.crt" "$WORK/leaf.key" & PIDS+=($!)

cat > /etc/systemd/system/qci-dummy.service <<'EOF'
[Unit]
Description=Qorovul CI dummy service

[Service]
ExecStart=/bin/sleep infinity
EOF
systemctl daemon-reload
systemctl start qci-dummy.service
systemctl start ssh 2>/dev/null || systemctl start sshd

mkdir -p "$MNT"
mountpoint -q "$MNT" || mount -t tmpfs -o size=8m tmpfs "$MNT"
sleep 1

mkdir -p /etc/qorovul
cat > /etc/qorovul/config.yml <<EOF
language: en
hostname: qci
interval: 5s
telegram:
  bot_token: ""
  chat_id: ""
  api_url: http://127.0.0.1:$API
heartbeat:
  url: http://127.0.0.1:$API/heartbeat
  interval: 30s
checks:
  disk:
    mountpoints: [/, $MNT]
  memory:
    threshold: 1            # always exceeded: exercises the sustain logic
    critical_threshold: null
  service:
    units: [qci-dummy]
  ssh:
    failures: 3
  ssl:
    domains: ["localhost:$TLS_BAD", "localhost:$TLS_SOON"]
    interval: 10s
  ports:
    allowed: [$(python3 "$HELPER" listening)]
EOF
ok "environment ready"

# ---------------------------------------------------------------------------
step "install.sh (non-interactive)"

QOROVUL_BOT_TOKEN="123456789:AAEabcdefghijklmnopqrstuvwxyz0123" QOROVUL_CHAT_ID="-1001234567890" \
    bash "$SRC/install.sh" || fail "install.sh failed"

service_active
PID="$(main_pid)"
[ "$(ps -o user= -p "$PID" | tr -d ' ')" = qorovul ] || fail "service does not run as user qorovul"
ok "running as unprivileged user qorovul (pid $PID)"
grep -Eq '^CapEff:[[:space:]]*0+$' "/proc/$PID/status" || fail "service process holds capabilities"
grep -Eq '^NoNewPrivs:[[:space:]]*1$' "/proc/$PID/status" || fail "NoNewPrivileges is not in effect"
ok "no capabilities, NoNewPrivileges set"
[ "$(systemctl show -p Type --value qorovul)" = notify ] || fail "unit is not Type=notify"
[ "$(stat -c '%a %U:%G' /etc/qorovul/config.yml)" = "640 root:qorovul" ] || fail "config permissions"
[ "$(stat -c '%a %U:%G' /var/lib/qorovul)" = "750 qorovul:qorovul" ] || fail "state dir permissions"
ok "config is 0640 root:qorovul, state dir is 0750 qorovul"
if [ -e "$SRC/qorovul.egg-info" ] || [ -e "$SRC/build" ]; then fail "installer wrote into the checkout"; fi
grep -q "Qorovul test message" "$TG" || fail "install did not send the test message"
ok "test message delivered during install"

# ---------------------------------------------------------------------------
step "baseline: every check works under the hardened unit"

expect_event alert "ssl:localhost:$TLS_BAD" 45
expect_event alert "ssl:localhost:$TLS_SOON" 45
expect_event alert memory:ram 60          # only after 3 consecutive cycles
errors="$(keys_matching 'k.endswith(":error")')"
[ -z "$errors" ] || fail "checks that could not run: $errors"
ok "no check errors"
expect_state "ssl:localhost:$TLS_BAD" failing critical 'not valid'
expect_state "ssl:localhost:$TLS_SOON" failing warning 'expires on [0-9-]+, days left: (9|10)$'
expect_state memory:ram failing warning 'RAM usage'
expect_state "disk:$MNT" ok
expect_state service:qci-dummy.service ok
[ -n "$(field disk:/ status)" ] || fail "disk:/ is not tracked"
ok "disk:/ is tracked: $(field disk:/ message)"
stray="$(keys_matching 'k.startswith(("ports:", "ssh:"))')"
[ -z "$stray" ] || fail "unexpected keys before anything was triggered: $stray"
ok "no port or ssh alerts at rest"
journalctl --no-pager -u qorovul > "$WORK/journal.txt" 2>&1 || true
grep -E "ssh: reading" "$WORK/journal.txt" | tail -1 | sed 's/^/        /' || true

# ---------------------------------------------------------------------------
step "trigger: stop a unit, open a port, fill a disk, fail SSH logins"

systemctl stop qci-dummy.service
(cd / && exec runuser -u nobody -- python3 -m http.server "$ROGUE" --bind 0.0.0.0 >/dev/null 2>&1) &
dd if=/dev/zero of="$MNT/fill" bs=1M count=7 status=none
for _ in 1 2 3 4; do
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o PubkeyAuthentication=no -o LogLevel=ERROR -o ConnectTimeout=5 \
        qci-nouser@127.0.0.1 true 2>/dev/null || true
done

expect_event alert service:qci-dummy.service 60
expect_event alert "ports:tcp/$ROGUE" 60
expect_event alert "disk:$MNT" 60
expect_event alert ssh:127.0.0.1 60
expect_state service:qci-dummy.service failing critical 'qci-dummy.service is (inactive|failed)'
expect_state "ports:tcp/$ROGUE" failing warning "port $ROGUE \\(0\\.0\\.0\\.0\\), user nobody"
expect_state "disk:$MNT" failing warning '8[5-9]\.[0-9]% full'
expect_state ssh:127.0.0.1 failing warning \
    '^failed SSH logins from 127\.0\.0\.1 in the last 10m: 4 \(users: qci-nouser\)$'

# ---------------------------------------------------------------------------
step "discipline: each alert is sent once"

sleep 25  # five more cycles
ALERTED=(service:qci-dummy.service "ports:tcp/$ROGUE" "disk:$MNT" ssh:127.0.0.1 memory:ram
         "ssl:localhost:$TLS_BAD" "ssl:localhost:$TLS_SOON")
for key in "${ALERTED[@]}"; do expect_count alert "$key" 1; done

# ---------------------------------------------------------------------------
step "discipline: a restart neither repeats alerts nor fakes recoveries"

systemctl restart qorovul
sleep 25
service_active
for key in "${ALERTED[@]}"; do
    expect_count alert "$key" 1
    expect_count recovered "$key" 0
done

# ---------------------------------------------------------------------------
step "recovery: undo three of the conditions"

systemctl start qci-dummy.service
pkill -f "http.server $ROGUE"
rm -f "$MNT/fill"
expect_event recovered service:qci-dummy.service 60
expect_event recovered "ports:tcp/$ROGUE" 60
expect_event recovered "disk:$MNT" 60
sleep 12
for key in service:qci-dummy.service "ports:tcp/$ROGUE" "disk:$MNT"; do
    expect_count recovered "$key" 1
    expect_count alert "$key" 1
done
# These are still true, so they must stay quiet.
for key in ssh:127.0.0.1 memory:ram "ssl:localhost:$TLS_BAD" "ssl:localhost:$TLS_SOON"; do
    expect_count recovered "$key" 0
    expect_count alert "$key" 1
done
expect_state "ports:tcp/$ROGUE" ok "" 'no longer listening'

# ---------------------------------------------------------------------------
step "footprint and health"

PID="$(main_pid)"
rss_kb="$(ps -o rss= -p "$PID" | tr -d ' ')"
[ "$rss_kb" -lt 40960 ] || fail "RSS is $((rss_kb / 1024)) MB, limit is 40 MB"
ok "RSS $((rss_kb / 1024)) MB (limit 40 MB)"
cpu="$(python3 - "$PID" <<'PY'
import os, sys
pid = sys.argv[1]
with open("/proc/%s/stat" % pid) as fh:
    f = fh.read().rsplit(")", 1)[1].split()
ticks = sum(int(f[i]) for i in (11, 12, 13, 14))        # utime stime cutime cstime
hz = os.sysconf("SC_CLK_TCK")
with open("/proc/uptime") as fh:
    uptime = float(fh.read().split()[0])
elapsed = uptime - int(f[19]) / hz                        # starttime
print("%.2f" % (100.0 * ticks / hz / max(elapsed, 1)))
PY
)"
python3 -c 'import sys; sys.exit(0 if float(sys.argv[1]) < 5 else 1)' "$cpu" \
    || fail "CPU usage ${cpu}% of one core at a 5s interval"
ok "CPU ${cpu}% of one core at a 5s interval (default interval is 30s)"
hb="$(python3 "$HELPER" gets "$TG" /heartbeat)"
[ "$hb" -ge 1 ] || fail "no heartbeat ping was sent"
ok "heartbeat pinged $hb time(s)"
journalctl --no-pager -u qorovul > "$WORK/journal.txt" 2>&1 || true
if grep -q "Traceback" "$WORK/journal.txt"; then fail "tracebacks in the journal"; fi
ok "no tracebacks in the journal"
systemctl status qorovul --no-pager 2>/dev/null | grep -E "Status:" | sed 's/^ */        /' || true
systemd-analyze security qorovul.service --no-pager 2>/dev/null | tail -1 | sed 's/^/        /' || true

# ---------------------------------------------------------------------------
step "opt-in: process names in port alerts (capability drop-in from the README)"

mkdir -p /etc/systemd/system/qorovul.service.d
printf '[Service]\nAmbientCapabilities=CAP_SYS_PTRACE CAP_DAC_READ_SEARCH\nCapabilityBoundingSet=CAP_SYS_PTRACE CAP_DAC_READ_SEARCH\n' \
    > /etc/systemd/system/qorovul.service.d/process-names.conf
systemctl daemon-reload
systemctl restart qorovul
(cd / && exec runuser -u nobody -- python3 -m http.server "$ROGUE2" --bind 0.0.0.0 >/dev/null 2>&1) &
expect_event alert "ports:tcp/$ROGUE2" 60
expect_state "ports:tcp/$ROGUE2" failing warning 'user nobody, process python3[.0-9]* \(pid [0-9]+\)'
pkill -f "http.server $ROGUE2"
expect_event recovered "ports:tcp/$ROGUE2" 60
rm -rf /etc/systemd/system/qorovul.service.d
systemctl daemon-reload
systemctl restart qorovul
sleep 6
grep -Eq '^CapEff:[[:space:]]*0+$' "/proc/$(main_pid)/status" || fail "capability not dropped again"
ok "drop-in removed, capabilities back to none"

# ---------------------------------------------------------------------------
step "self-healing: systemd restarts a hung process (watchdog)"

mkdir -p /etc/systemd/system/qorovul.service.d
printf '[Service]\nWatchdogSec=20s\nWatchdogSignal=SIGKILL\nRestartSec=2\n' \
    > /etc/systemd/system/qorovul.service.d/ci.conf
systemctl daemon-reload
systemctl restart qorovul
sleep 8
OLD="$(main_pid)"
kill -STOP "$OLD"   # simulate a hang: the process stops pinging the watchdog
healed=0
for _ in $(seq 1 60); do
    sleep 1
    NEW="$(main_pid)"
    if [ "$NEW" != "$OLD" ] && [ "$NEW" != 0 ] && [ "$(systemctl is-active qorovul)" = active ]; then
        healed=1; break
    fi
done
kill -CONT "$OLD" 2>/dev/null || true
[ "$healed" = 1 ] || fail "hung process was not restarted by the watchdog"
ok "hung process $OLD was killed and replaced by $NEW"
rm -rf /etc/systemd/system/qorovul.service.d
systemctl daemon-reload
systemctl restart qorovul
sleep 15
for key in ssh:127.0.0.1 memory:ram "ssl:localhost:$TLS_BAD"; do
    expect_count alert "$key" 1
    expect_count recovered "$key" 0
done

# ---------------------------------------------------------------------------
step "languages: the CLI and Telegram messages follow the chosen language"

runuser -u qorovul -- "$QOROVUL" test --lang ru >"$WORK/test-ru.txt" 2>&1 || true
grep -q "проверок выполнено:" "$WORK/test-ru.txt" || fail "qorovul test --lang ru printed no Russian"
grep -q "Тестовое сообщение Qorovul" "$TG" || fail "no Russian test message reached Telegram"
ok "qorovul test --lang ru: Russian output and Telegram message"
status_ko="$("$QOROVUL" status --lang ko)"
printf '%s\n' "$status_ko" | grep -q "마지막 알림" || fail "qorovul status --lang ko is not Korean"
ok "qorovul status --lang ko: Korean table"
sed -i -E 's|^language:.*$|language: uz|' /etc/qorovul/config.yml
systemctl restart qorovul
dd if=/dev/zero of="$MNT/fill" bs=1M count=7 status=none
uz_alert=0
for _ in $(seq 1 60); do
    if grep -q "toʻlgan (boʻsh:" "$TG"; then uz_alert=1; break; fi
    sleep 1
done
[ "$uz_alert" = 1 ] || fail "no Uzbek alert after switching the language"
ok "daemon with language: uz sends Uzbek alerts"
rm -f "$MNT/fill"
sed -i -E 's|^language:.*$|language: en|' /etc/qorovul/config.yml
systemctl restart qorovul
sleep 3

# ---------------------------------------------------------------------------
step "idempotency: running install.sh again changes nothing"

before="$(md5sum < /etc/qorovul/config.yml)"
bash "$SRC/install.sh" >/dev/null 2>&1 || fail "second install.sh run failed"
[ "$before" = "$(md5sum < /etc/qorovul/config.yml)" ] || fail "re-install modified the config"
service_active
sleep 12
expect_count alert memory:ram 1
ok "config untouched, service active, no repeated alerts"

# ---------------------------------------------------------------------------
step "uninstall (commands from the README)"

systemctl disable --now qorovul >/dev/null 2>&1
rm -rf /etc/systemd/system/qorovul.service /etc/systemd/system/qorovul.service.d \
       /opt/qorovul /usr/local/bin/qorovul \
       /var/lib/qorovul /etc/qorovul
userdel qorovul
systemctl daemon-reload
[ "$(systemctl is-active qorovul 2>/dev/null || true)" != active ] || fail "service still active"
! id qorovul >/dev/null 2>&1 || fail "user still exists"
ok "removed cleanly"

printf '\n\033[1;32mALL INTEGRATION CHECKS PASSED\033[0m\n'
