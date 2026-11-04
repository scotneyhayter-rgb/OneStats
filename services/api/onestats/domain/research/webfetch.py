"""SSRF-hardened HTTP retrieval for the Internet Research Engine.

This is the ONLY place the engine reaches the public internet, and it is deliberately paranoid. Every
fetch is validated fail-closed: a target is retrieved only if it is provably a public host over
http(s), within strict content-type, size, timeout and redirect limits, and permitted by robots.txt.

Security properties (threat: SSRF / internal-network pivot, prompt injection, resource exhaustion):
  * Scheme allow-list: only ``http`` / ``https``. Anything else (file, ftp, gopher, data, ...) is blocked.
  * Host validation: every hostname is resolved and EVERY resolved IP must be globally routable. Private,
    loopback, link-local, CGNAT/shared, reserved, multicast and unspecified addresses are blocked, and
    so is anything not provably global (fail closed). IP-literal hosts are validated the same way.
  * Redirects are NOT auto-followed; each ``Location`` is re-validated from scratch before the next hop,
    so a public URL cannot redirect into the internal network. A cross-protocol hop to a non-http scheme
    is blocked.
  * Size cap: the body is streamed and aborted the moment it exceeds the limit (anti memory-exhaustion).
  * Content-type allow-list: only HTML / XHTML / plain text are accepted here (PDF/other arrive later).
  * Timeouts on connect and read; no cookies; no credentials; no auth headers.
  * robots.txt is fetched (through this same safe path) and honoured for our user agent.

Everything returned is UNTRUSTED DATA. The engine treats fetched bytes/text as evidence to extract from,
never as instructions — no fetched content is ever executed, templated into a prompt, or acted upon as a
command.

Residual note (documented, hardened in a later phase): host validation happens just before connecting,
so a DNS-rebinding attacker could in theory return a public IP to our resolver and a private IP to the
socket (TOCTOU). The later-phase hardening pins the validated IP for the actual connection. The current
guard still blocks the common SSRF vectors (literal private targets, public→private redirects).
"""
from __future__ import annotations

import hashlib
import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

# Outcomes mirror research_fetch.outcome (see migration 0065).
FETCHED = "fetched"
BLOCKED = "blocked"          # SSRF / scheme / host validation refused the target
FAILED = "failed"            # network/HTTP error
DISALLOWED = "disallowed"    # robots.txt forbids it for our agent
TOO_LARGE = "too_large"
WRONG_TYPE = "wrong_type"
DUPLICATE = "duplicate"      # set by the caller, not here

DEFAULT_USER_AGENT = (
    "OneStatsResearchBot/0.1 (+https://onestats.local; cricket historical research; respects robots.txt)"
)
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain", "text/xml", "application/xml")
# Content types we decode to text (vs. binary bodies like PDF kept as raw bytes).
TEXT_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain", "text/xml", "application/xml")
PDF_CONTENT_TYPE = "application/pdf"
IMAGE_CONTENT_TYPES = ("image/jpeg", "image/png", "image/tiff", "image/gif", "image/webp", "image/bmp")
DEFAULT_MAX_BYTES = 5_000_000           # 5 MB per page
DEFAULT_CONNECT_TIMEOUT = 8.0
DEFAULT_READ_TIMEOUT = 20.0
DEFAULT_MAX_REDIRECTS = 5

# A resolver maps a hostname to a list of IP strings. Injectable so the whole module is testable offline.
Resolver = Callable[[str], "list[str]"]


def _default_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None)
    return [info[4][0] for info in infos]


def _ip_is_public(ip_str: str) -> bool:
    """True only if ``ip_str`` is a globally-routable public address. Fail closed: anything private,
    loopback, link-local, CGNAT/shared, reserved, multicast, unspecified — or not provably global — is
    rejected. IPv4-mapped IPv6 addresses are unwrapped and validated as their IPv4."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None) is not None and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
            or ip.is_multicast or ip.is_unspecified):
        return False
    # 100.64.0.0/10 CGNAT / shared address space is not flagged is_private by ipaddress — block it.
    if ip.version == 4 and ipaddress.ip_address(ip_str if "." in ip_str else str(ip)) in ipaddress.ip_network("100.64.0.0/10"):
        return False
    # Fail closed: require a globally-routable address.
    return bool(ip.is_global)


@dataclass(slots=True)
class HostCheck:
    ok: bool
    detail: str = ""
    ips: list[str] = field(default_factory=list)


def validate_host(host: str, *, resolver: Resolver | None = None) -> HostCheck:
    """Resolve ``host`` and require EVERY resolved address to be public. An IP literal is validated
    directly (no DNS). Returns the validated IPs so a caller could pin the connection later."""
    resolver = resolver or _default_resolver
    if not host:
        return HostCheck(False, "empty host")
    # Strip IPv6 brackets if present.
    bare = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        ipaddress.ip_address(bare)
        is_literal = True
    except ValueError:
        is_literal = False
    if is_literal:
        return HostCheck(_ip_is_public(bare), "" if _ip_is_public(bare) else "non-public IP literal", [bare])
    try:
        ips = resolver(bare)
    except Exception as exc:  # noqa: BLE001 - any resolution failure blocks the target
        return HostCheck(False, f"could not resolve host: {type(exc).__name__}")
    if not ips:
        return HostCheck(False, "host did not resolve")
    for ip in ips:
        if not _ip_is_public(ip):
            return HostCheck(False, "host resolves to a non-public address", ips)
    return HostCheck(True, "", ips)


@dataclass(slots=True)
class UrlCheck:
    ok: bool
    detail: str = ""
    scheme: str = ""
    host: str = ""


def validate_url(url: str, *, resolver: Resolver | None = None) -> UrlCheck:
    """Validate scheme + host of an absolute URL. Blocks non-http(s) schemes and non-public hosts."""
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        return UrlCheck(False, f"unparseable url: {exc}")
    scheme = (parts.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        return UrlCheck(False, f"scheme '{scheme or '(none)'}' not allowed")
    host = parts.hostname or ""
    hc = validate_host(host, resolver=resolver)
    if not hc.ok:
        return UrlCheck(False, hc.detail or "host not allowed", scheme, host)
    return UrlCheck(True, "", scheme, host)


@dataclass(slots=True)
class FetchResult:
    outcome: str
    url: str
    final_url: str | None = None
    http_status: int | None = None
    content_type: str | None = None
    bytes: int | None = None
    content_sha256: str | None = None
    text: str | None = None            # decoded text (text/html/plain/xml only)
    content: bytes | None = None       # raw body (always set on success; used for PDFs/images)
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome == FETCHED


def _base_content_type(raw: str | None) -> str:
    return (raw or "").split(";", 1)[0].strip().lower()


class RobotsCache:
    """Per-host robots.txt cache. robots.txt is retrieved through the SSRF-safe fetch path so it cannot
    be used as its own SSRF vector. A host whose robots cannot be read is treated as *allowed* (common
    web convention: absent/erroring robots = no restriction), but host validation still applies."""

    def __init__(self) -> None:
        self._parsers: dict[str, RobotFileParser | None] = {}

    def allowed(self, url: str, user_agent: str, *, fetch_text: Callable[[str], str | None]) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        key = origin.lower()
        if key not in self._parsers:
            robots_url = urljoin(origin + "/", "robots.txt")
            body = fetch_text(robots_url)
            if body is None:
                self._parsers[key] = None
            else:
                rp = RobotFileParser()
                rp.parse(body.splitlines())
                self._parsers[key] = rp
        rp = self._parsers[key]
        if rp is None:
            return True
        return rp.can_fetch(user_agent, url)


class Fetcher:
    """SSRF-hardened fetcher. ``transport`` and ``resolver`` are injectable for offline testing
    (e.g. ``httpx.MockTransport`` + a fake resolver)."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        max_bytes: int = DEFAULT_MAX_BYTES,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        allowed_content_types: tuple[str, ...] = ALLOWED_CONTENT_TYPES,
        resolver: Resolver | None = None,
        transport: Any | None = None,
        respect_robots: bool = True,
    ) -> None:
        self.user_agent = user_agent
        self.max_bytes = max_bytes
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.max_redirects = max_redirects
        self.allowed_content_types = tuple(allowed_content_types)
        self.resolver = resolver
        self._transport = transport
        self.respect_robots = respect_robots
        self._robots = RobotsCache()

    def _client(self):
        import httpx  # lazy: module imports without httpx installed

        timeout = httpx.Timeout(self.read_timeout, connect=self.connect_timeout)
        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml,text/plain"}
        return httpx.Client(timeout=timeout, follow_redirects=False, headers=headers,
                            transport=self._transport, trust_env=False)

    def _read_capped(self, resp: Any) -> tuple[bytes, bool]:
        """Stream the response body, stopping once max_bytes is exceeded. Returns (body, too_large)."""
        buf = bytearray()
        for chunk in resp.iter_bytes():
            buf.extend(chunk)
            if len(buf) > self.max_bytes:
                return bytes(buf[: self.max_bytes]), True
        return bytes(buf), False

    def fetch_text(self, url: str) -> str | None:
        """Convenience used for robots.txt: return decoded text or None on any block/failure."""
        r = self.fetch(url, _robots_check=False)
        return r.text if r.ok else None

    def fetch(self, url: str, *, _robots_check: bool = True) -> FetchResult:
        """Retrieve one URL with full SSRF hardening and manual redirect revalidation."""
        import httpx

        current = url
        try:
            with self._client() as client:
                for _hop in range(self.max_redirects + 1):
                    chk = validate_url(current, resolver=self.resolver)
                    if not chk.ok:
                        return FetchResult(BLOCKED, url, detail=chk.detail)
                    if _robots_check and self.respect_robots:  # noqa: SIM102 - kept explicit in SSRF path
                        if not self._robots.allowed(current, self.user_agent, fetch_text=self.fetch_text):
                            return FetchResult(DISALLOWED, url, final_url=current,
                                               detail="robots.txt disallows this path for our agent")
                    try:
                        with client.stream("GET", current) as resp:
                            if resp.is_redirect:
                                loc = resp.headers.get("location")
                                if not loc:
                                    return FetchResult(FAILED, url, final_url=current,
                                                       http_status=resp.status_code, detail="redirect without location")
                                current = urljoin(current, loc)
                                continue
                            if resp.status_code >= 400:
                                return FetchResult(FAILED, url, final_url=current, http_status=resp.status_code,
                                                   detail=f"HTTP {resp.status_code}")
                            ctype = _base_content_type(resp.headers.get("content-type"))
                            if ctype and ctype not in self.allowed_content_types:
                                return FetchResult(WRONG_TYPE, url, final_url=current,
                                                   http_status=resp.status_code, content_type=ctype,
                                                   detail=f"content-type '{ctype}' not accepted")
                            body, too_large = self._read_capped(resp)
                            sha = hashlib.sha256(body).hexdigest()
                            if too_large:
                                return FetchResult(TOO_LARGE, url, final_url=current, http_status=resp.status_code,
                                                   content_type=ctype, bytes=len(body), content_sha256=sha,
                                                   detail=f"body exceeded {self.max_bytes} bytes")
                            # Decode to text for everything EXCEPT known-binary bodies (PDF/image), which
                            # keep their raw bytes for a specialised extractor (pdfplumber/OCR). This still
                            # covers HTML, plain text, XML and JSON (discovery APIs), which need text.
                            text = None
                            if ctype not in (PDF_CONTENT_TYPE, *IMAGE_CONTENT_TYPES):
                                try:
                                    text = body.decode(resp.encoding or "utf-8", errors="replace")
                                except (LookupError, TypeError):
                                    text = body.decode("utf-8", errors="replace")
                            return FetchResult(FETCHED, url, final_url=current, http_status=resp.status_code,
                                               content_type=ctype or None, bytes=len(body),
                                               content_sha256=sha, text=text, content=body)
                    except httpx.HTTPError as exc:
                        return FetchResult(FAILED, url, final_url=current, detail=f"{type(exc).__name__}")
                return FetchResult(FAILED, url, final_url=current, detail="too many redirects")
        except Exception as exc:  # noqa: BLE001 - never let a fetch crash the worker; record and move on
            return FetchResult(FAILED, url, detail=f"{type(exc).__name__}")
