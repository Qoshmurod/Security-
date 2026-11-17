"""Unexpected listening TCP port check.

Reads /proc/net/tcp and /proc/net/tcp6 directly (world-readable), so no root
and no ``ss`` binary are needed.  Those files also carry the UID that owns
each socket, so the owning *user* is always reported.

The owning *process* can only be resolved for sockets whose /proc/<pid>/fd
the service user may inspect: its own processes, or every process when the
unit is granted CAP_DAC_READ_SEARCH (to list the fd directory) and
CAP_SYS_PTRACE (to read the links) - the same pair ``ss -p`` relies on as
root.  That is opt-in (see README); without it the process is simply left
out of the message.
"""

import ipaddress
import os
import pwd
import socket
import struct
from typing import Any, Callable, Dict, Iterable, Iterator, List, NamedTuple, Optional, Set, Tuple

from .base import Check, CheckResult

TCP_LISTEN = "0A"
PROC_FILES = (("/proc/net/tcp", socket.AF_INET), ("/proc/net/tcp6", socket.AF_INET6))
_LITTLE_ENDIAN = struct.pack("=I", 1)[0] == 1


class Listener(NamedTuple):
    ip: str
    port: int
    uid: Optional[int] = None
    inode: Optional[int] = None


def _iter_lines(path: str) -> Optional[Iterator[str]]:
    """Lazily yield lines so a host with 100k connections costs no memory."""
    try:
        fh = open(path)
    except FileNotFoundError:
        return None  # e.g. IPv6 disabled

    def lines() -> Iterator[str]:
        with fh:
            for line in fh:
                yield line
    return lines()


def decode_addr(hexaddr: str, family: int) -> Tuple[str, int]:
    """Decode '0100007F:0035' style /proc/net addresses."""
    ip_hex, port_hex = hexaddr.split(":")
    raw = bytes.fromhex(ip_hex)
    if _LITTLE_ENDIAN:
        # The kernel prints each 32-bit word in host byte order.
        words = struct.unpack("<%dI" % (len(raw) // 4), raw)
        raw = struct.pack(">%dI" % len(words), *words)
    return socket.inet_ntop(family, raw), int(port_hex, 16)


def parse_proc_net(lines: Iterable[str], family: int) -> Set[Listener]:
    """Extract listening sockets from /proc/net/tcp{,6} content."""
    if isinstance(lines, str):
        lines = lines.splitlines()
    out = set()
    for line in lines:
        fields = line.split()
        if len(fields) < 4 or fields[3] != TCP_LISTEN:
            continue
        try:
            ip, port = decode_addr(fields[1], family)
            uid = int(fields[7]) if len(fields) > 9 else None
            inode = int(fields[9]) if len(fields) > 9 else None
        except (ValueError, OSError, struct.error):
            continue  # header or a line format we do not understand
        out.add(Listener(ip, port, uid, inode))
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


def _user_name(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return "uid %d" % uid


def find_socket_owners(inodes: Set[int], proc: str = "/proc") -> Dict[int, str]:
    """Map socket inodes to "name (pid N)" for the processes we may inspect."""
    wanted = {"socket:[%d]" % i: i for i in inodes}
    found = {}  # type: Dict[int, str]
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return found
    for pid in pids:
        fd_dir = "%s/%s/fd" % (proc, pid)
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue  # not ours and no CAP_SYS_PTRACE, or the process exited
        for fd in fds:
            try:
                target = os.readlink("%s/%s" % (fd_dir, fd))
            except OSError:
                continue
            inode = wanted.get(target)
            if inode is None or inode in found:
                continue
            try:
                with open("%s/%s/comm" % (proc, pid)) as fh:
                    name = fh.read().strip()
            except OSError:
                name = "?"
            found[inode] = "%s (pid %s)" % (name, pid)
        if len(found) == len(wanted):
            break
    return found


class PortsCheck(Check):
    """Alert when a TCP port is listening that is not in the allowlist."""

    name = "ports"

    def __init__(self, config: Dict[str, Any],
                 read_file: Callable[[str], Any] = _iter_lines,
                 user_name: Callable[[int], str] = _user_name,
                 find_owners: Callable[[Set[int]], Dict[int, str]] = find_socket_owners) -> None:
        super().__init__(config)
        self.read_file = read_file
        self.user_name = user_name
        self.find_owners = find_owners
        self.allowed_ports, self.allowed_pairs = parse_allowed(config["allowed"])
        # inode -> process description, or None when we may not look.  Cached
        # so /proc is scanned once per new socket, not every cycle.
        self._owners = {}  # type: Dict[int, Optional[str]]

    def listening(self) -> Set[Listener]:
        found = set()  # type: Set[Listener]
        read_any = False
        for path, family in PROC_FILES:
            content = self.read_file(path)
            if content is None:
                continue
            read_any = True
            found |= parse_proc_net(content, family)
        if not read_any:
            raise RuntimeError("cannot read /proc/net/tcp")
        return found

    def _allowed(self, ip: str, port: int) -> bool:
        if port in self.allowed_ports or (ip, port) in self.allowed_pairs:
            return True
        return self.config["ignore_loopback"] and _is_loopback(ip)

    def _resolve_owners(self, listeners: List[Listener]) -> None:
        inodes = {ln.inode for ln in listeners if ln.inode}
        unknown = inodes - set(self._owners)
        if unknown:
            resolved = self.find_owners(unknown)
            for inode in unknown:
                self._owners[inode] = resolved.get(inode)
        for inode in set(self._owners) - inodes:
            del self._owners[inode]

    def _describe(self, port: int, listeners: List[Listener]) -> str:
        addrs = ", ".join(sorted({ln.ip for ln in listeners}))
        msg = "unexpected TCP listener on port %d (%s)" % (port, addrs)
        users = sorted({self.user_name(ln.uid) for ln in listeners if ln.uid is not None})
        procs = sorted({self._owners[ln.inode] for ln in listeners
                        if ln.inode and self._owners.get(ln.inode)})
        if users:
            msg += ", user %s" % ", ".join(users)
        if procs:
            msg += ", process %s" % ", ".join(procs)
        return msg

    def run(self) -> List[CheckResult]:
        by_port = {}  # type: Dict[int, List[Listener]]
        for ln in self.listening():
            if not self._allowed(ln.ip, ln.port):
                by_port.setdefault(ln.port, []).append(ln)
        self._resolve_owners([ln for lns in by_port.values() for ln in lns])
        return [CheckResult("ports:tcp/%d" % port, False, self.config["severity"],
                            self._describe(port, by_port[port]))
                for port in sorted(by_port)]

    def cleared_message(self, key: str) -> str:
        return "TCP port %s is no longer listening" % key.rsplit("/", 1)[1]
