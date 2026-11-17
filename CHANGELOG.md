# Changelog

## 1.1.1 — 2026-11-17

- Tested on Ubuntu 26.04 LTS (Python 3.14, systemd 259, OpenSSH 10.2, uutils
  coreutils, sudo-rs). CI now runs the full integration test on it and the
  unit tests on Python 3.14.
- The installer looks for `python3.14` first.
- SSL: on Python 3.13+ (Ubuntu 26.04) some private CAs that curl and browsers
  accept, for example a CA without a keyUsage extension, were reported as
  "not valid" (critical). Verification now follows the same rules on every
  distribution. Chain, host name and expiry are still checked.

## 1.1.0 — 2026-11-17

### Added
- Messages in 14 languages: English, Uzbek, Russian, Turkish, Korean,
  Chinese (Simplified), Japanese, Spanish, Portuguese, French, German, Arabic,
  Hindi and Indonesian. This covers Telegram alerts, check results, and the
  output of `qorovul test` and `qorovul status`.
- `language` config option (or `auto` to follow `$LANG`), the `QOROVUL_LANG`
  environment override, and the `--lang` command-line option.
- The installer asks for the alert language on a fresh install and suggests
  the shell's. `QOROVUL_LANGUAGE` skips the question.
- Numbers, sizes and durations follow each language's conventions: decimal
  comma, `%87,3` in Turkish, `ГБ` in Russian, `Go` in French, `2시간 5분`.
- `qorovul status` lines up columns by display width, so Korean, Chinese and
  Japanese tables align.
- README in Uzbek, Russian, Turkish and Korean, with example screenshots.

### Changed
- English messages with a count no longer need plural forms:
  `failed SSH logins from 203.0.113.9 in the last 10m: 48` and
  `example.com certificate expires on 2026-11-26, days left: 9`.
- The memory message shows sizes with units (`15.0 GB`) instead of a fixed MB.
- `qorovul status --json` keeps non-ASCII text readable.

### Fixed
- The installer can set the language on configs written by 1.0, which have no
  `language` line.

## 1.0.0 — 2026-11-17

Verified end to end on real systemd. `tests/integration/run.sh` and CI now
cover Ubuntu 22.04/24.04, Debian 12 and AlmaLinux 9.

### Added
- `heartbeat.url`: optional dead-man's-switch ping, so you learn when the
  whole server stops.
- systemd watchdog (`Type=notify`, `WatchdogSec=10min`). A hung process is
  killed and restarted, and `systemctl status` shows a status line.
- `confirm_cycles` per check. `service` now waits for 2 failing checks, so a
  unit caught mid-restart or still starting at boot is not reported.
- Port alerts name the user that owns the socket. They also name the process
  when the optional capability drop-in is installed.
- Integration test suite and GitHub Actions CI.
- Example screenshot in the README.

### Fixed
- SSH: an attacker-chosen user name such as `root from 10.0.0.1 port 22`
  could spoof the source IP, so attacks evaded the per-IP count or were
  blamed on another address.
- SSH: rsyslog's `message repeated N times` lines were counted once instead
  of N times.
- SSH: the `Failed none` probe was counted as a password guess.
- SSH: lines written just before logrotate renamed the file were lost.
- SSH: the journald source missed sshd on distributions whose unit is
  neither `ssh.service` nor `sshd.service`, and OpenSSH 9.8+ (`sshd-session`).
- Memory: the "3 consecutive cycles" counter reset on restart, so a running
  incident could look recovered. It is now stored in `state.json`.
- Disk: paths listed in `mountpoints` were ignored unless they were
  auto-discoverable local filesystems (tmpfs, NFS).
- Scheduling used the wall clock. An NTP step backwards could pause all
  checks. It now uses a monotonic clock.
- A Telegram outage made every cycle retry immediately. Retries now back off
  from 30 s up to 5 min, without dropping anything.
- A message Telegram cannot parse is re-sent as plain text, and long messages
  are clipped without breaking markup.
- `install.sh` wrote build files into the checkout and failed on a read-only
  one. It now builds from a temporary copy.
- `qorovul status` renamed an unreadable state file as "corrupt". It now
  reports the problem and suggests `sudo`.
- SSL: a single failed connection is retried once before alerting.

## 0.1.0 — 2026-11-16

First release.
