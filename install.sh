#!/usr/bin/env bash
# Qorovul installer - idempotent, safe to re-run for upgrades.
#
#   curl -fsSL https://raw.githubusercontent.com/Qoshmurod/Security-/main/install.sh | sudo bash
#
# or from a checkout:   sudo ./install.sh
#
# Non-interactive:  QOROVUL_BOT_TOKEN=... QOROVUL_CHAT_ID=... sudo -E ./install.sh
#
# Environment knobs:
#   QOROVUL_REPO   GitHub repo URL   (default https://github.com/Qoshmurod/Security-)
#   QOROVUL_REF    branch or tag     (default main)
#   QOROVUL_LANGUAGE  language of the alerts: en uz ru tr ko zh ja es pt fr de ar hi id
#                     or auto (asked on a fresh install; default: this shell's $LANG)
#   QOROVUL_SKIP_START=1             install everything but do not start the service

# Everything lives in main() so a truncated `curl | bash` download runs nothing.
main() {
set -euo pipefail

REPO="${QOROVUL_REPO:-https://github.com/Qoshmurod/Security-}"
REF="${QOROVUL_REF:-main}"
PREFIX=/opt/qorovul
VENV="$PREFIX/venv"
ETC=/etc/qorovul
CONFIG="$ETC/config.yml"
STATE_DIR=/var/lib/qorovul
UNIT=/etc/systemd/system/qorovul.service
SVC_USER=qorovul

say()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!! \033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mxx \033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run as root (e.g. curl -fsSL ... | sudo bash)"
command -v systemctl >/dev/null || die "systemd is required"

# --- package manager / python ------------------------------------------------
PKG=""
if command -v apt-get >/dev/null; then PKG=apt
elif command -v dnf >/dev/null; then PKG=dnf
elif command -v yum >/dev/null; then PKG=yum
fi

find_python() {
    local c
    for c in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
        if command -v "$c" >/dev/null &&
           "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
            command -v "$c"; return 0
        fi
    done
    return 1
}

PY="$(find_python || true)"
if [ -z "$PY" ]; then
    say "installing Python 3.9+"
    case "$PKG" in
        apt) apt-get update -qq && apt-get install -y -qq python3 python3-venv ;;
        dnf|yum) "$PKG" install -y -q python3 || true
                 find_python >/dev/null || "$PKG" install -y -q python39 ;;
        *) die "Python 3.9+ not found and no supported package manager" ;;
    esac
    PY="$(find_python)" || die "could not install Python 3.9+"
fi
# Debian/Ubuntu ship venv separately.
if ! "$PY" -c 'import ensurepip, venv' 2>/dev/null; then
    [ "$PKG" = apt ] || die "$PY lacks the venv module"
    say "installing python3-venv"
    apt-get update -qq
    ver="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    apt-get install -y -qq "python${ver}-venv" || apt-get install -y -qq python3-venv
fi
say "using $("$PY" --version) at $PY"

# --- source -----------------------------------------------------------------
# Always build from a private copy: pip writes build files next to the
# sources, which must not litter (or fail on a read-only) checkout.
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT
SRC="$WORK/src"
mkdir "$SRC"
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/pyproject.toml" ] && [ -d "$SCRIPT_DIR/qorovul" ]; then
    say "installing from local checkout $SCRIPT_DIR"
    for f in pyproject.toml README.md LICENSE config.example.yml qorovul.service qorovul; do
        cp -R "$SCRIPT_DIR/$f" "$SRC/"
    done
else
    command -v curl >/dev/null || die "curl is required"
    say "downloading $REPO ($REF)"
    curl -fsSL "$REPO/archive/$REF.tar.gz" | tar -xz -C "$SRC" --strip-components=1 \
        || die "download failed: $REPO/archive/$REF.tar.gz"
fi
[ -f "$SRC/pyproject.toml" ] || die "source tree is incomplete"

# --- user -------------------------------------------------------------------
NOLOGIN="$(command -v nologin || echo /usr/sbin/nologin)"
if ! id "$SVC_USER" >/dev/null 2>&1; then
    say "creating system user $SVC_USER"
    useradd --system --no-create-home --home-dir "$STATE_DIR" --shell "$NOLOGIN" "$SVC_USER"
fi
# Narrowest standard way to read SSH auth logs without root:
#   adm             -> /var/log/auth.log on Debian/Ubuntu (group adm, 0640)
#   systemd-journal -> journald (Debian 12+, AlmaLinux: /var/log/secure is root-only)
for g in adm systemd-journal; do
    if getent group "$g" >/dev/null && ! id -nG "$SVC_USER" | tr ' ' '\n' | grep -qx "$g"; then
        say "adding $SVC_USER to group $g (read-only access to SSH logs)"
        usermod -aG "$g" "$SVC_USER"
    fi
done

# --- files ------------------------------------------------------------------
install -d -m 0750 -o root -g "$SVC_USER" "$ETC"
install -d -m 0750 -o "$SVC_USER" -g "$SVC_USER" "$STATE_DIR"
install -d -m 0755 "$PREFIX"

if [ ! -x "$VENV/bin/python" ]; then
    say "creating virtualenv $VENV"
    "$PY" -m venv "$VENV"
fi
say "installing qorovul into $VENV"
"$VENV/bin/pip" install --quiet --disable-pip-version-check --upgrade "$SRC"
ln -sf "$VENV/bin/qorovul" /usr/local/bin/qorovul

FRESH_CONFIG=0
if [ ! -f "$CONFIG" ]; then
    say "writing $CONFIG"
    install -m 0640 -o root -g "$SVC_USER" "$SRC/config.example.yml" "$CONFIG"
    FRESH_CONFIG=1
else
    say "keeping existing $CONFIG"
fi
cp -f "$SRC/config.example.yml" "$ETC/config.example.yml"
chown root:"$SVC_USER" "$CONFIG"; chmod 0640 "$CONFIG"

# --- telegram credentials -----------------------------------------------------
cfg_value() {  # cfg_value bot_token
    "$VENV/bin/python" - "$CONFIG" "$1" <<'PY'
import sys, yaml
with open(sys.argv[1]) as fh:
    c = yaml.safe_load(fh) or {}
print((c.get("telegram") or {}).get(sys.argv[2]) or "")
PY
}
set_cfg() {  # set_cfg key value   (value already validated: no quotes/slashes)
    sed -i -E "s|^(  $1:)[[:space:]]*\"?\"?[[:space:]]*(#.*)?$|\1 \"$2\"|" "$CONFIG"
    [ "$(cfg_value "$1")" = "$2" ] || die "could not set telegram.$1 in $CONFIG; edit it by hand"
}
ask() {  # ask "prompt" -> stdout; reads the terminal even under curl | bash
    local reply=""
    if [ -r /dev/tty ] && { exec 3</dev/tty; } 2>/dev/null; then
        printf '%s' "$1" >/dev/tty
        IFS= read -r reply <&3 || true
        exec 3<&-
    fi
    printf '%s' "$reply"
}

TOKEN_RE='^[0-9]+:[A-Za-z0-9_-]{20,}$'
CHAT_RE='^(-?[0-9]+|@[A-Za-z][A-Za-z0-9_]{3,})$'
ENV_FILE="$ETC/qorovul.env"
in_env_file() { [ -f "$ENV_FILE" ] && grep -Eq "^$1=.+" "$ENV_FILE"; }
CREDS_OK=1
if [ -z "$(cfg_value bot_token)" ] && ! in_env_file QOROVUL_BOT_TOKEN; then
    token="${QOROVUL_BOT_TOKEN:-}"
    [ -n "$token" ] || token="$(ask 'Telegram bot token (from @BotFather): ')"
    if [[ "$token" =~ $TOKEN_RE ]]; then set_cfg bot_token "$token"
    else warn "no valid bot token given; set telegram.bot_token in $CONFIG"; CREDS_OK=0; fi
fi
if [ -z "$(cfg_value chat_id)" ] && ! in_env_file QOROVUL_CHAT_ID; then
    chat="${QOROVUL_CHAT_ID:-}"
    [ -n "$chat" ] || chat="$(ask 'Telegram chat id (e.g. 123456789 or -100...): ')"
    if [[ "$chat" =~ $CHAT_RE ]]; then set_cfg chat_id "$chat"
    else warn "no valid chat id given; set telegram.chat_id in $CONFIG"; CREDS_OK=0; fi
fi

# --- language -----------------------------------------------------------------
LANGS="en uz ru tr ko zh ja es pt fr de ar hi id"
supported_lang() { [ "$1" = auto ] || [[ " $LANGS " == *" $1 "* ]]; }
lang="${QOROVUL_LANGUAGE:-}"
if [ -z "$lang" ] && [ "$FRESH_CONFIG" = 1 ]; then
    # Suggest the language of the shell that runs the installer.
    guess="${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}"
    guess="${guess%%[_.@]*}"
    supported_lang "$guess" || guess=en
    lang="$(ask "Alert language ($LANGS) [$guess]: ")"
    lang="${lang:-$guess}"
fi
if [ -n "$lang" ]; then
    if supported_lang "$lang"; then
        if grep -q '^language:' "$CONFIG"; then
            sed -i -E "s|^language:.*$|language: $lang|" "$CONFIG"
        else
            # Configs from before 1.1 have no language line: add one on top.
            sed -i "1i language: $lang" "$CONFIG"
        fi
        grep -qx "language: $lang" "$CONFIG" || die "could not set language in $CONFIG"
        say "alert language: $lang"
    else
        warn "unsupported language '$lang' (supported: $LANGS auto); keeping the current one"
    fi
fi

# --- service ------------------------------------------------------------------
install -m 0644 "$SRC/qorovul.service" "$UNIT"
systemctl daemon-reload
systemctl enable --quiet qorovul.service

if [ "$CREDS_OK" -ne 1 ] || [ "${QOROVUL_SKIP_START:-0}" = 1 ]; then
    warn "service enabled but not started. After editing $CONFIG run:"
    warn "  sudo systemctl restart qorovul && sudo -u $SVC_USER qorovul test"
    exit 0
fi

say "running checks as $SVC_USER (qorovul test)"
set +e
(
    # shellcheck disable=SC1090
    if [ -f "$ENV_FILE" ]; then set -a; . "$ENV_FILE"; set +a; fi
    runuser -u "$SVC_USER" -- "$VENV/bin/qorovul" test -c "$CONFIG"
)
rc=$?
set -e
case "$rc" in
    0) say "all checks passed and the test message was sent" ;;
    1) warn "test message sent; some checks are failing right now (see above)" ;;
    2) die "configuration error (see above); fix $CONFIG and re-run" ;;
    3) die "could not send the Telegram test message; check token/chat id and network" ;;
    *) warn "qorovul test exited with $rc" ;;
esac

systemctl restart qorovul.service
say "qorovul is running:  systemctl status qorovul   |   journalctl -u qorovul -f"
say "current state:       qorovul status"
}

main "$@"
