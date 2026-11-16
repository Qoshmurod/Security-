# Qorovul

**Qorovul** (Uzbek for *sentry*) is a small Linux server watchdog. It runs as a
systemd service on the machine it watches and sends alerts to Telegram.

No web UI, no database, no inbound ports, no central server. One Python process,
about 30 MB of RAM, a few milliseconds of CPU every 30 seconds.

It watches six things:

| Check     | Alerts when                                                           | Key               |
|-----------|-----------------------------------------------------------------------|-------------------|
| `disk`    | a mounted filesystem is ≥ 85 % full (critical at ≥ 95 %)              | `disk:/var`       |
| `memory`  | RAM usage is ≥ 90 % for 3 checks in a row (critical at ≥ 97 %)        | `memory:ram`      |
| `service` | a listed systemd unit is not `active`                                 | `service:nginx.service` |
| `ssh`     | one IP reaches 20 failed SSH logins within 10 minutes                 | `ssh:203.0.113.9` |
| `ssl`     | a domain's certificate expires within 14 days (critical within 3)     | `ssl:example.com` |
| `ports`   | a TCP port is listening that is not on your allowlist                 | `ports:tcp/8080`  |

Alerts are **sent once**. You get a reminder only if the problem is still there
after a cooldown (6 h by default), and a **RECOVERED** message when it clears.

---

## 60-second quickstart

1. **Create a bot.** In Telegram, message [@BotFather](https://t.me/BotFather),
   send `/newbot` and copy the token (`123456789:AAE...`).
2. **Get your chat id.** Send any message to your new bot, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `"chat":{"id": ...}`.
   For a group, add the bot to the group first; group ids are negative.
3. **Install** on the server (Ubuntu, Debian, AlmaLinux/RHEL 9 and similar with systemd):

   ```bash
   curl -fsSL https://raw.githubusercontent.com/Qoshmurod/Security-/main/install.sh | sudo bash
   ```

   The installer asks for the token and chat id, starts the service and sends
   a test message. To skip the prompts:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/Qoshmurod/Security-/main/install.sh \
     | sudo QOROVUL_BOT_TOKEN='123456789:AAE...' QOROVUL_CHAT_ID='123456789' bash
   ```

4. **Tell it about your server** in `/etc/qorovul/config.yml`: the services
   to watch, your domains, and the ports you expect to be open:

   ```yaml
   checks:
     service: { units: [nginx, postgresql] }
     ssl:     { domains: [example.com] }
     ports:   { allowed: [22, 80, 443] }
   ```

   Then run `sudo systemctl restart qorovul && sudo -u qorovul qorovul test`.

That's it. `qorovul status` shows what it currently knows.

### What an alert looks like

> 📸 **Screenshot placeholder.** Add `docs/alert-example.png` and replace this
> line with `![Alert example](docs/alert-example.png)`.

Until then, here is the text. Several events from one cycle are batched into one message:

```
🛡 web-01

🔴 CRITICAL disk:/var
/var is 96.1% full (3.9 GB free of 100.0 GB)
since 2026-11-16 14:03

🟠 WARNING ssh:203.0.113.9
48 failed SSH logins from 203.0.113.9 in the last 10m (users: admin, oracle, root)
since 2026-11-16 14:05

✅ RECOVERED service:nginx.service
nginx.service is active
was CRITICAL for 4m
```

---

## How alerting works

This is the part Qorovul is strict about. Every result has a stable **key**,
and for each key the state is kept in `/var/lib/qorovul/state.json`, so a
restart or upgrade does not repeat alerts you have already received.

| Situation                                        | What you get                                   |
|--------------------------------------------------|------------------------------------------------|
| A condition becomes true                         | one **ALERT**                                  |
| It stays true                                    | nothing, every cycle                           |
| …still true after `cooldown` (6 h)               | one **STILL FAILING** reminder, then every 6 h |
| Severity goes up (warning → critical)            | **ESCALATED** right away, cooldown ignored     |
| Severity goes down                               | nothing                                        |
| Healthy for `recovery_cycles` (2) checks in a row | one **RECOVERED**                             |
| It cleared before you were ever alerted          | nothing (no recovery for an alert you never got) |
| Severity below `min_severity`                    | nothing, ever                                  |
| Quiet hours, not critical                        | held, then delivered when quiet hours end if still relevant |
| Quiet hours, critical                            | delivered right away                           |
| Telegram is unreachable                          | retried next cycle, until it is delivered      |
| A check itself crashes (e.g. log not readable)   | one ALERT on `<check>:error`; RECOVERED when it works again |

Some details:

* `recovery_cycles: 2` stops a value sitting right on a threshold (say a disk
  going 84.9 % → 85.0 % → 84.9 %) from sending alert/recovered pairs all day.
* If something recovers during quiet hours and fails again before the
  RECOVERED went out, it is treated as the same incident. You get no
  duplicate alert.
* When a check runs normally and stops reporting a key that was failing
  (a port closed, an IP stopped attacking, a filesystem was unmounted), that
  key counts as cleared. When a check *errors*, its keys are left alone, so
  "could not look" is never read as "all clear".
* Events are sent in as few messages as possible. They are marked delivered
  only after Telegram accepts them, so a send that fails is retried and never lost.

---

## Configuration reference

The config lives at `/etc/qorovul/config.yml` (`-c PATH` or `$QOROVUL_CONFIG`
to override). [`config.example.yml`](config.example.yml) is fully commented
and lists every default. Unknown keys are rejected, and all errors are
reported at once with their path:

```
qorovul: invalid configuration:
  - checks.disk.treshold: unknown key (allowed: critical_threshold, enabled, ...)
  - checks.ssh.window: must be at least 60s
```

Durations accept seconds (`30`) or `30s`, `10m`, `6h`, `1d`.

### Top level

| Key          | Default                        | Meaning |
|--------------|--------------------------------|---------|
| `hostname`   | system hostname                | Name in the message header |
| `interval`   | `30s`                          | How often checks run (min 5 s) |
| `state_file` | `/var/lib/qorovul/state.json`  | Alert state, must be writable |
| `log_level`  | `info`                         | `debug` `info` `warning` `error` |

### `telegram`

| Key         | Default                     | Meaning |
|-------------|-----------------------------|---------|
| `bot_token` | —                           | From @BotFather. Env `QOROVUL_BOT_TOKEN` overrides |
| `chat_id`   | —                           | User/group id or `@channel`. Env `QOROVUL_CHAT_ID` overrides |
| `timeout`   | `10s`                       | Per request. 3 attempts, honours rate limits |
| `api_url`   | `https://api.telegram.org`  | Only for proxies/mirrors |

To keep the token out of the config file, put it in `/etc/qorovul/qorovul.env`
(mode `0600`, root-owned), which the unit loads:

```
QOROVUL_BOT_TOKEN=123456789:AAE...
QOROVUL_CHAT_ID=123456789
```

### `alerts`

| Key                   | Default   | Meaning |
|-----------------------|-----------|---------|
| `min_severity`        | `warning` | `info` / `warning` / `critical`: lowest severity sent |
| `cooldown`            | `6h`      | Time between reminders while still failing (`0` = every cycle) |
| `recovery_cycles`     | `2`       | Consecutive healthy runs before RECOVERED |
| `send_recovery`       | `true`    | Send RECOVERED messages |
| `quiet_hours.enabled` | `false`   | Only critical is delivered inside the window |
| `quiet_hours.start`   | `"23:00"` | Local time, may cross midnight |
| `quiet_hours.end`     | `"07:00"` | |

### `checks.*`: keys every check accepts

| Key             | Default                         | Meaning |
|-----------------|---------------------------------|---------|
| `enabled`       | `true`                          | |
| `interval`      | global `interval` (`ssl`: `1h`) | How often this check runs |
| `cooldown`      | `alerts.cooldown`               | Per-check override |
| `send_recovery` | `alerts.send_recovery`          | Per-check override |

### `checks.disk`

| Key                   | Default | Meaning |
|-----------------------|---------|---------|
| `threshold`           | `85`    | Warning at ≥ this % |
| `critical_threshold`  | `95`    | Critical at ≥ this % (`null` = never) |
| `mountpoints`         | `[]`    | Only these (empty = every real filesystem) |
| `exclude_fstypes`     | tmpfs, devtmpfs, squashfs, overlay, … | Skipped filesystem types |
| `exclude_mountpoints` | `/snap`, `/var/lib/docker` | Skipped, including everything below |

Bind mounts and btrfs subvolumes of the same device are reported once, under the shortest path.

### `checks.memory`

| Key                  | Default | Meaning |
|----------------------|---------|---------|
| `threshold`          | `90`    | Warning at ≥ this % |
| `critical_threshold` | `97`    | Critical at ≥ this % (`null` = never) |
| `sustained_cycles`   | `3`     | Consecutive runs at/above threshold before alerting |

Usage is `(total − available) / total`, so page cache does not count.

### `checks.service`

| Key        | Default    | Meaning |
|------------|------------|---------|
| `units`    | `[]`       | Units to watch; `nginx` means `nginx.service`; timers, sockets etc. need a suffix |
| `severity` | `critical` | |

`active` and `reloading` are healthy; anything else (`failed`, `inactive`,
`activating` …) alerts.

### `checks.ssh`

| Key          | Default                                 | Meaning |
|--------------|-----------------------------------------|---------|
| `source`     | `auto`                                  | `auto` = first readable log file, else journald; `file`; `journal` |
| `log_paths`  | `/var/log/auth.log`, `/var/log/secure`  | |
| `failures`   | `20`                                    | Alert when one IP reaches this many failures… |
| `window`     | `10m`                                   | …within this sliding window |
| `severity`   | `warning`                               | |
| `ignore_ips` | `[]`                                    | IPs or CIDRs never alerted on |

Failures are counted per connection: `Invalid user x` followed by
`Failed password for invalid user x` on the same source port is **one**
failure, not two. A connection with several password tries counts each
`Failed …` line. Key-only servers are covered as well (`Invalid user`,
`Connection closed by authenticating user … [preauth]`). The log is read
incrementally, and rotation and truncation are handled. On first start only
the last 2 MB are read.

On internet-facing servers bots come and go. If you don't want a RECOVERED
message for every attacker, set `send_recovery: false` on this check.

### `checks.ssl`

| Key                      | Default   | Meaning |
|--------------------------|-----------|---------|
| `domains`                | `[]`      | `example.com` or `host:port` (default 443) |
| `warn_days`              | `14`      | Warning when expiring in ≤ this many days |
| `critical_days`          | `3`       | Critical when ≤ this many days |
| `timeout`                | `10s`     | |
| `connect_error_severity` | `warning` | When the host cannot be reached at all |
| `interval`               | `1h`      | |

Certificates are fetched with full verification and SNI. An expired, untrusted
or wrong-host certificate is reported as critical, with the reason.

### `checks.ports`

| Key               | Default   | Meaning |
|-------------------|-----------|---------|
| `allowed`         | `[22]`    | `443` (any address) or `"127.0.0.1:5432"` / `"[::1]:6379"` (exact) |
| `ignore_loopback` | `true`    | Ignore listeners bound only to 127.0.0.0/8 / ::1 |
| `severity`        | `warning` | |

One alert per port, listing every address it is bound on.

---

## CLI

```
qorovul run [--once]     foreground loop (what systemd runs)
qorovul test             run every check once, print results, send a test message
qorovul status [--json]  current state and the last alert per key
qorovul version
```

All commands accept `-c PATH`. Exit codes for `test`: `0` all good, `1` some
checks are failing (the message was still sent), `2` invalid config,
`3` Telegram delivery failed. `run` exits `2` on invalid config, and systemd
does not restart it in a loop for that.

```
$ qorovul status
state: /var/lib/qorovul/state.json  (9 keys, 1 failing)

KEY                            STATUS   SEVERITY  SINCE            LAST ALERT                 MESSAGE
ports:tcp/8080                 FAILING  warning   2026-11-16 14:10 alert 2026-11-16 14:10     unexpected TCP listener on port 8080 (0.0.0.0)
disk:/                         ok       -         -                recovered 2026-11-15 03:12 / is 61.2% full (38.1 GB free of 98.3 GB)
...
```

---

## Permissions: what needs more than an ordinary user

Qorovul runs as the unprivileged system user **`qorovul`**, with no
capabilities, `NoNewPrivileges`, and a read-only view of the filesystem
(see [`qorovul.service`](qorovul.service)). The only writable path is
`/var/lib/qorovul`.

| Needs                          | How it is read                    | Access required |
|--------------------------------|-----------------------------------|-----------------|
| Disk usage                     | `statvfs` via psutil              | none |
| Memory                         | `/proc/meminfo` via psutil        | none |
| Service state                  | `systemctl is-active` (D-Bus)     | none |
| Listening ports                | `/proc/net/tcp`, `/proc/net/tcp6` | none: **`ss` and root are not used** |
| TLS certificates               | outbound TLS connection           | none |
| SSH log, Debian/Ubuntu         | `/var/log/auth.log` (`root:adm 0640`) | member of group **`adm`** |
| SSH log, journald (Debian 12+, AlmaLinux) | `journalctl -u ssh -u sshd` | member of group **`systemd-journal`** |

So the only elevated access is **read-only access to logs**, through standard
groups. `install.sh` adds `qorovul` to `adm` and `systemd-journal` if they
exist. On AlmaLinux/RHEL `/var/log/secure` is `root:root 0600`, so Qorovul
leaves it alone and reads the journal. If you want to grant less, remove the
group you don't need (`gpasswd -d qorovul adm`) and set `checks.ssh.source`
to match.

Because ports are read from `/proc/net`, the alert tells you the port and
bind address, but not the owning process. Finding the process needs root.
Run `sudo ss -ltnp 'sport = :8080'` yourself when you get one.

---

## Installation details

`install.sh` is idempotent, so re-running it upgrades in place. It:

1. finds Python ≥ 3.9 (installs `python3`/`python3-venv`, or `python39` on EL8, if needed);
2. creates the system user `qorovul` and adds it to `adm` / `systemd-journal`;
3. creates `/etc/qorovul` (`root:qorovul 0750`) and `/var/lib/qorovul` (`qorovul 0750`);
4. installs into a virtualenv at `/opt/qorovul/venv` (no system Python
   packages are touched, PEP 668 safe) and links `/usr/local/bin/qorovul`;
5. writes `/etc/qorovul/config.yml` from the example **only if it does not exist**;
6. asks for the bot token and chat id (on the terminal, so it works under
   `curl | bash`) if they are not set yet, or takes `QOROVUL_BOT_TOKEN` /
   `QOROVUL_CHAT_ID` from the environment;
7. installs and enables `qorovul.service`, runs `qorovul test` as the
   `qorovul` user, then (re)starts the service.

Options: `QOROVUL_REF=v0.1.0` (branch or tag to install), `QOROVUL_REPO=...`,
`QOROVUL_SKIP_START=1`. From a checkout: `sudo ./install.sh`.

Manual install with pip works too: `pip install .` gives you the `qorovul`
command. Copy `config.example.yml` and `qorovul.service` into place yourself.

### Uninstall

```bash
sudo systemctl disable --now qorovul
sudo rm -rf /etc/systemd/system/qorovul.service /opt/qorovul /usr/local/bin/qorovul \
            /var/lib/qorovul /etc/qorovul
sudo userdel qorovul
sudo systemctl daemon-reload
```

---

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[test]'
pytest
```

The tests use no network and no real system state: psutil, log files,
`/proc/net`, systemctl, certificates and the Telegram API are all faked. Most
of them cover the alert state machine (`tests/test_state_machine.py`).

Out of scope, on purpose: web dashboards, metrics history, graphs, databases,
a central hub, channels other than Telegram, auto-remediation.

## License

[MIT](LICENSE)
