"""Unexpected listening TCP port check.

Reads /proc/net/tcp and /proc/net/tcp6 directly (world-readable), so no root
and no ``ss`` binary are needed.  The owning process is *not* reported because
mapping sockets to PIDs requires root.
"""

import ipaddress
import socket
import struct
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .base import Check, CheckResult

TCP_LISTEN = "0A"
PROC_FILES = (("/proc/net/tcp", socket.AF_INET), ("/proc/net/tcp6", socket.AF_INET6))


def _read_file(path: str) -> Optional[str]:
    try:
        with open(path) as fh:
            return fh.read()
    except FileNotFoundError:
        return None  # e.g. IPv6 disabled


def decode_addr(hexaddr: str, family: int) -> Tuple[str, int]:
    """Decode '0100007F:0035' style /proc/net addresses."""
    ip_hex, port_hex = hexaddr.split(":")
    raw = bytes.fromhex(ip_hex)
    # The kernel prints each 32-bit word in host byte order.
    words = struct.unpack("=%dI" % (len(raw) // 4), raw)
    packed = struct.pack(">%dI" % len(words), *words) if struct.pack("=I", 1)[0] == 1 \
        else raw
    if family == socket.AF_INET:
        ip = socket.inet_ntop(socket.AF_INET, packed)
    else:
        ip = socket.inet_ntop(socket.AF_INET6, packed)
    return ip, int(port_hex, 16)


def parse_proc_net(text: str, family: int) -> Set[Tuple[str, int]]:
    out = set()
    for line in text.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 4 or fields[3] != TCP_LISTEN:
            continue
        out.add(decode_addr(fields[1], family))
    return out


def _is_loopback(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return addr.is_loopback


def parse_allowed(entries: List[Any]) -> Tuple[Set[int], Set[Tuple[str, int]]]:
    """Split allowlist into bare ports and exact (address, port) pairs."""
    ports, pairs = set(), set()
    for e in entries:
        if isinstance(e, int):
            ports.add(e)
            continue
        s = str(e).strip()
        if s.isdigit():
            ports.add(int(s))
            continue
        host, _, port = s.rpartition(":")
        host = host.strip("[]")
        pairs.add((str(ipaddress.ip_address(host)), int(port)))
    return ports, pairs


class PortsCheck(Check):
    """Alert when a TCP port is listening that is not in the allowlist."""

    name = "ports"

    def __init__(self, config: Dict[str, Any],
                 read_file: Callable[[str], Optional[str]] = _read_file) -> None:
        super().__init__(config)
        self.read_file = read_file
        self.allowed_ports, self.allowed_pairs = parse_allowed(config["allowed"])

    def listening(self) -> Set[Tuple[str, int]]:
        found = set()
        read_any = False
        for path, family in PROC_FILES:
            text = self.read_file(path)
            if text is None:
                continue
            read_any = True
            found |= parse_proc_net(text, family)
        if not read_any:
            raise RuntimeError("cannot read /proc/net/tcp")
        return found

    def _allowed(self, ip: str, port: int) -> bool:
        if port in self.allowed_ports or (ip, port) in self.allowed_pairs:
            return True
        return self.config["ignore_loopback"] and _is_loopback(ip)

    def run(self) -> List[CheckResult]:
        by_port = {}  # type: Dict[int, List[str]]
        for ip, port in self.listening():
            if not self._allowed(ip, port):
                by_port.setdefault(port, []).append(ip)
        results = []
        for port in sorted(by_port):
            addrs = ", ".join(sorted(by_port[port]))
            results.append(CheckResult(
                "ports:tcp/%d" % port, False, self.config["severity"],
                "unexpected TCP listener on port %d (%s)" % (port, addrs)))
        return results

    def cleared_message(self, key: str) -> str:
        return "TCP port %s is no longer listening" % key.rsplit("/", 1)[1]
