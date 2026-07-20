"""Common utilities."""
import ipaddress
from typing import Optional

from . import uploads  # noqa: F401  — re-export submodule for `from shared.utils import uploads`


def safe_ip(value: Optional[str]) -> Optional[str]:
    """Validate IP address; return None if invalid (test client gửi 'testclient')."""
    if not value:
        return None
    # X-Forwarded-For có thể là 'ip1, ip2' — lấy first
    first = value.split(",")[0].strip()
    try:
        ipaddress.ip_address(first)
        return first
    except ValueError:
        return None
