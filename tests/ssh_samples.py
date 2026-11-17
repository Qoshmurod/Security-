"""sshd log samples in the formats written by different distributions.

Kept as Python constants (not files) so the tests touch no real filesystem.
Addresses are from the RFC 5737 / RFC 3849 documentation ranges.
"""

# rsyslog classic timestamps, including rsyslog's "message repeated N times"
UBUNTU_2204_AUTH_LOG = """\
Nov 16 11:50:01 web-01 CRON[2211]: pam_unix(cron:session): session opened for user root(uid=0) by (uid=0)
Nov 16 11:51:12 web-01 sshd[2301]: Invalid user admin from 203.0.113.9 port 51022
Nov 16 11:51:12 web-01 sshd[2301]: pam_unix(sshd:auth): check pass; user unknown
Nov 16 11:51:12 web-01 sshd[2301]: pam_unix(sshd:auth): authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost=203.0.113.9
Nov 16 11:51:14 web-01 sshd[2301]: Failed password for invalid user admin from 203.0.113.9 port 51022 ssh2
Nov 16 11:51:15 web-01 sshd[2301]: Received disconnect from 203.0.113.9 port 51022:11: Bye Bye [preauth]
Nov 16 11:51:15 web-01 sshd[2301]: Disconnected from invalid user admin 203.0.113.9 port 51022 [preauth]
Nov 16 11:51:20 web-01 sshd[2305]: Failed password for root from 203.0.113.9 port 51040 ssh2
Nov 16 11:51:24 web-01 sshd[2305]: message repeated 2 times: [ Failed password for root from 203.0.113.9 port 51040 ssh2]
Nov 16 11:51:25 web-01 sshd[2305]: error: maximum authentication attempts exceeded for root from 203.0.113.9 port 51040 ssh2 [preauth]
Nov 16 11:51:25 web-01 sshd[2305]: Disconnecting authenticating user root 203.0.113.9 port 51040: Too many authentication failures [preauth]
Nov 16 11:51:25 web-01 sshd[2305]: PAM 2 more authentication failures; logname= uid=0 euid=0 tty=ssh ruser= rhost=203.0.113.9  user=root
Nov 16 11:52:02 web-01 sshd[2310]: Accepted publickey for deploy from 198.51.100.7 port 40112 ssh2: ED25519 SHA256:47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU
Nov 16 11:52:02 web-01 sshd[2310]: pam_unix(sshd:session): session opened for user deploy(uid=1000) by (uid=0)
Nov 16 11:52:30 web-01 sshd[2320]: Connection closed by authenticating user root 192.0.2.44 port 33110 [preauth]
Nov 16 11:52:41 web-01 sshd[2322]: Connection closed by 192.0.2.44 port 33112 [preauth]
Nov 16 11:52:50 web-01 sshd[2324]: banner exchange: Connection from 192.0.2.50 port 5555: invalid format
Nov 16 11:53:00 web-01 sshd[2326]: Unable to negotiate with 192.0.2.60 port 4444: no matching key exchange method found. Their offer: diffie-hellman-group1-sha1 [preauth]
Nov 16 11:53:10 web-01 sudo:   deploy : TTY=pts/0 ; PWD=/home/deploy ; USER=root ; COMMAND=/usr/bin/systemctl restart nginx
"""

# rsyslog high-precision ISO timestamps; includes a user name crafted to spoof the source IP
UBUNTU_2404_AUTH_LOG = """\
2026-11-16T11:51:12.482913+00:00 web-02 sshd[8123]: Invalid user oracle from 2001:db8::bad port 40222
2026-11-16T11:51:12.611002+00:00 web-02 sshd[8123]: Connection closed by invalid user oracle 2001:db8::bad port 40222 [preauth]
2026-11-16T11:51:13.020114+00:00 web-02 sshd[8125]: Failed publickey for git from 198.51.100.23 port 55001 ssh2: ED25519 SHA256:47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU
2026-11-16T11:51:13.220114+00:00 web-02 sshd[8125]: Connection closed by authenticating user git 198.51.100.23 port 55001 [preauth]
2026-11-16T11:51:14.000000+00:00 web-02 sudo:   deploy : TTY=pts/0 ; PWD=/home/deploy ; USER=root ; COMMAND=/usr/bin/systemctl restart nginx
2026-11-16T11:51:15.000000+00:00 web-02 sshd[8130]: Failed password for invalid user root from 10.0.0.1 port 22 from 198.51.100.23 port 55010 ssh2
2026-11-16T11:51:16.100000+00:00 web-02 sshd[8131]: Accepted password for deploy from 192.0.2.10 port 50000 ssh2
2026-11-16T11:51:17.000000+00:00 web-02 systemd-logind[612]: New session 12 of user deploy.
"""

# /var/log/secure on RHEL-family systems
ALMALINUX_9_SECURE = """\
Nov 16 11:54:01 alma9 sshd[3001]: Invalid user test from 203.0.113.77 port 60100
Nov 16 11:54:01 alma9 sshd[3001]: pam_unix(sshd:auth): check pass; user unknown
Nov 16 11:54:01 alma9 sshd[3001]: pam_unix(sshd:auth): authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost=203.0.113.77
Nov 16 11:54:03 alma9 sshd[3001]: Failed password for invalid user test from 203.0.113.77 port 60100 ssh2
Nov 16 11:54:05 alma9 sshd[3001]: Failed password for invalid user test from 203.0.113.77 port 60100 ssh2
Nov 16 11:54:06 alma9 sshd[3001]: Connection closed by invalid user test 203.0.113.77 port 60100 [preauth]
Nov 16 11:54:06 alma9 sshd[3001]: PAM 1 more authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost=203.0.113.77
Nov 16 11:54:10 alma9 sshd[3010]: Failed password for root from 203.0.113.77 port 60200 ssh2
Nov 16 11:54:11 alma9 sshd[3010]: Received disconnect from 203.0.113.77 port 60200:11: Bye Bye [preauth]
Nov 16 11:54:11 alma9 sshd[3010]: Disconnected from authenticating user root 203.0.113.77 port 60200 [preauth]
Nov 16 11:54:30 alma9 sshd[3020]: Accepted publickey for admin from 192.0.2.10 port 51000 ssh2: RSA SHA256:nThbg6kXUpJWGl7E1IGOCspRomTxdCARLviKw6E5SY8
Nov 16 11:54:30 alma9 sshd[3020]: pam_unix(sshd:session): session opened for user admin(uid=1000) by (uid=0)
Nov 16 11:54:40 alma9 unix_chkpwd[3030]: password check failed for user (root)
"""

# `journalctl -o short-unix`; OpenSSH 9.8+ logs as sshd-session
JOURNAL_SHORT_UNIX_OPENSSH_10 = """\
1794830000.100000 deb13 sshd-session[901]: Invalid user ubnt from 203.0.113.200 port 41000
1794830000.300000 deb13 sshd-session[901]: Connection closed by invalid user ubnt 203.0.113.200 port 41000 [preauth]
1794830001.000000 deb13 sshd-session[905]: Connection closed by authenticating user root 203.0.113.200 port 41002 [preauth]
1794830002.000000 deb13 sshd[850]: Server listening on 0.0.0.0 port 22.
1794830003.000000 deb13 sshd-session[910]: Accepted publickey for debian from 192.0.2.10 port 52000 ssh2: ED25519 SHA256:47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU
1794830003.500000 deb13 sshd-session[910]: pam_unix(sshd:session): session opened for user debian(uid=1000) by debian(uid=0)
"""
