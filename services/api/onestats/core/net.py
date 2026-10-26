"""Outbound-request safety (SSRF protection).

Custom/user-supplied integration URLs must never be able to reach internal networks. Before any request to
a user-configured endpoint, ``validate_public_url`` requires https/http, rejects credentials in the URL,
and resolves the host — refusing private, loopback, link-local, reserved or otherwise non-global addresses.
Built-in providers use fixed, vetted hosts and do not accept arbitrary URLs.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def validate_public_url(url: str, *, allow_http: bool = False) -> str:
    """Return the URL if it is safe to request, else raise ValueError. Resolves the host and rejects any
    non-global (private/loopback/link-local/reserved/multicast) address — protecting against SSRF."""
    if not url or not isinstance(url, str):
        raise ValueError("invalid_url")
    parsed = urlparse(url.strip())
    if parsed.scheme not in (("http", "https") if allow_http else ("https",)):
        raise ValueError("url_scheme_not_allowed")        # https only by default
    if parsed.username or parsed.password:
        raise ValueError("url_must_not_contain_credentials")
    host = parsed.hostname
    if not host:
        raise ValueError("url_missing_host")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise ValueError("url_host_unresolvable") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved \
                or ip.is_multicast or ip.is_unspecified:
            raise ValueError("url_resolves_to_internal_address")
    return url
