"""SSRF checks for replay targets.

Resolves the hostname and rejects private, loopback, link-local and other
non-public addresses unless explicitly allowed. DNS rebinding between check and
connect remains a residual risk; see SECURITY.md.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class ReplayTargetError(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.goog",
    }
)


def _is_blocked_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # is_site_local exists on IPv6Address only (and was removed from some IPv4 paths).
    site_local = bool(getattr(address, "is_site_local", False))
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or site_local
    )


def _resolve(hostname: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ReplayTargetError("dns", f"could not resolve hostname {hostname!r}") from exc
    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr:
            addresses.append(str(sockaddr[0]))
    # Preserve order while dropping duplicates from dual-stack lookups.
    unique: list[str] = []
    seen: set[str] = set()
    for address in addresses:
        if address not in seen:
            seen.add(address)
            unique.append(address)
    if not unique:
        raise ReplayTargetError("dns", f"no addresses found for hostname {hostname!r}")
    return unique


def validate_replay_url(url: str, *, allow_private: bool = False) -> str:
    """Return a normalized http(s) URL, or raise ReplayTargetError."""
    raw = url.strip()
    if not raw:
        raise ReplayTargetError("invalid", "target URL is empty")

    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ReplayTargetError("scheme", "only http and https replay targets are allowed")
    if not parsed.hostname:
        raise ReplayTargetError("invalid", "target URL must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ReplayTargetError("credentials", "URLs with embedded credentials are not allowed")
    if parsed.hostname.lower() in _BLOCKED_HOSTNAMES and not allow_private:
        raise ReplayTargetError("private", f"hostname {parsed.hostname!r} is not allowed")

    hostname = parsed.hostname
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None

    if literal is not None:
        if _is_blocked_ip(literal) and not allow_private:
            raise ReplayTargetError("private", f"address {hostname} is not a public IP")
    else:
        for address in _resolve(hostname):
            try:
                parsed_ip = ipaddress.ip_address(address)
            except ValueError as exc:
                raise ReplayTargetError("dns", f"resolved address {address!r} is invalid") from exc
            if _is_blocked_ip(parsed_ip) and not allow_private:
                raise ReplayTargetError(
                    "private",
                    f"hostname {hostname!r} resolves to non-public address {address}",
                )

    # Rebuild without fragment; keep path/query as provided.
    netloc = parsed.netloc
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{netloc}{path}{query}"
