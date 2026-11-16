"""Built-in checks."""

from typing import Any, Dict, List

from .base import SEVERITIES, Check, CheckResult, severity_rank
from .disk import DiskCheck
from .memory import MemoryCheck
from .ports import PortsCheck
from .service import ServiceCheck
from .ssh import SSHCheck
from .ssl import SSLCheck

REGISTRY = {
    "disk": DiskCheck,
    "memory": MemoryCheck,
    "service": ServiceCheck,
    "ssh": SSHCheck,
    "ssl": SSLCheck,
    "ports": PortsCheck,
}


def build_checks(config: Dict[str, Any]) -> List[Check]:
    """Instantiate every enabled check from a validated config."""
    return [REGISTRY[name](section) for name, section in config["checks"].items()
            if section["enabled"]]


__all__ = ["Check", "CheckResult", "SEVERITIES", "severity_rank", "REGISTRY", "build_checks"]
