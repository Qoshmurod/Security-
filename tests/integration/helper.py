#!/usr/bin/env python3
"""Helpers for the end-to-end test (standard library only).

    helper.py serve PORT LOG         fake Telegram Bot API + heartbeat endpoint
    helper.py tls PORT CERT KEY      minimal TLS server on 127.0.0.1
    helper.py count LOG KIND KEY     number of KIND events for KEY that were sent
    helper.py wait LOG KIND KEY SEC  exit 0 as soon as count >= 1, else 1 after SEC
    helper.py gets LOG PATH          number of GET requests to PATH
    helper.py show LOG               print every message that was sent
    helper.py listening              comma separated list of listening TCP ports

KIND is one of: alert, escalated, reminder, recovered.
"""

import html
import json
import re
import socket
import ssl
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

PATTERNS = {
    "alert": r"^\S+ <b>(?:INFO|WARNING|CRITICAL)</b> <code>%s</code>$",
    "escalated": r"^\S+ <b>(?:INFO|WARNING|CRITICAL)</b> <code>%s</code> \S+ escalated$",
    "reminder": r"^\S+ <b>STILL (?:INFO|WARNING|CRITICAL)</b> <code>%s</code>$",
    "recovered": r"^\S+ <b>RECOVERED</b> <code>%s</code>$",
}


def serve(port, log_path):
    class Handler(BaseHTTPRequestHandler):
        def _record(self, method, body=None):
            # Real UTF-8, not \\u escapes, so the test script can grep any language.
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"t": time.time(), "method": method, "path": self.path,
                                     "body": body}, ensure_ascii=False) + "\n")

        def _reply(self):
            data = b'{"ok":true,"result":{"message_id":1}}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            self._record("POST", json.loads(self.rfile.read(length) or b"{}"))
            self._reply()

        def do_GET(self):
            self._record("GET")
            self._reply()

        def log_message(self, *args):
            pass

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


def tls(port, cert, key):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(16)
    while True:
        conn, _ = server.accept()
        conn.settimeout(10)
        try:
            with ctx.wrap_socket(conn, server_side=True):
                pass  # complete the handshake, then hang up
        except (ssl.SSLError, OSError):
            conn.close()  # e.g. the client rejected our certificate


def entries(log_path):
    try:
        with open(log_path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]
    except FileNotFoundError:
        return []


def messages(log_path):
    return [e["body"]["text"] for e in entries(log_path)
            if e["method"] == "POST" and e["path"].endswith("/sendMessage")]


def count(log_path, kind, key):
    pattern = re.compile(PATTERNS[kind] % re.escape(html.escape(key, quote=False)))
    return sum(1 for text in messages(log_path) for line in text.splitlines()
               if pattern.match(line))


def listening():
    ports = set()
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(path) as fh:
                lines = fh.read().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if fields[3] == "0A":
                ports.add(int(fields[1].rsplit(":", 1)[1], 16))
    return sorted(ports)


def main(argv):
    cmd = argv[1]
    if cmd == "serve":
        serve(int(argv[2]), argv[3])
    elif cmd == "tls":
        tls(int(argv[2]), argv[3], argv[4])
    elif cmd == "count":
        print(count(argv[2], argv[3], argv[4]))
    elif cmd == "wait":
        deadline = time.time() + float(argv[5])
        while time.time() < deadline:
            if count(argv[2], argv[3], argv[4]) >= 1:
                return 0
            time.sleep(1)
        return 1
    elif cmd == "gets":
        print(sum(1 for e in entries(argv[2]) if e["method"] == "GET" and e["path"] == argv[3]))
    elif cmd == "show":
        for text in messages(argv[2]):
            print(re.sub(r"<[^>]+>", "", html.unescape(text)))
            print("-" * 60)
    elif cmd == "listening":
        print(", ".join(str(p) for p in listening()))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
