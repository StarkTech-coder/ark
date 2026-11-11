"""Secure web research helpers for ARK local MCP tooling."""

from __future__ import annotations

import datetime as dt
import html
import ipaddress
import re
import socket
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse, urlunparse

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "metadata.google.internal",
    "metadata",
}

TRACKING_QUERY_PREFIXES = ("utm_", "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid")


class WebResearchError(RuntimeError):
    """Raised when web research cannot complete safely."""


@dataclass(frozen=True)
class WebSource:
    source_title: str
    source_url: str
    domain: str
    publication_date: str | None
    access_date: str
    extracted_content: str
    relevant_excerpt: str


@dataclass(frozen=True)
class WebResearchResult:
    user_query: str
    search_query: str
    access_date: str
    sources: list[WebSource]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_query": self.user_query,
            "search_query": self.search_query,
            "access_date": self.access_date,
            "sources": [asdict(src) for src in self.sources],
            "warnings": self.warnings,
        }


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _is_blocked_ip(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve_host_ips(hostname: str) -> set[str]:
    ips: set[str] = set()
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return ips
    for info in infos:
        sockaddr = info[4]
        if sockaddr:
            ips.add(str(sockaddr[0]))
    return ips


def is_safe_remote_url(raw_url: str) -> bool:
    try:
        parsed = urlparse(raw_url)
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False

    host = parsed.hostname.strip().lower()
    if host in BLOCKED_HOSTS:
        return False
    if _is_blocked_ip(host):
        return False

    resolved_ips = _resolve_host_ips(host)
    if any(_is_blocked_ip(ip) for ip in resolved_ips):
        return False

    return True


def _normalize_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    host = (parsed.hostname or "").lower()
    port = parsed.port

    netloc = host
    if port and not ((parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"

    query_pairs = parse_qs(parsed.query, keep_blank_values=False)
    filtered: list[tuple[str, str]] = []
    for key, values in query_pairs.items():
        lower_key = key.lower()
        if any(lower_key.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES):
            continue
        for value in values:
            filtered.append((key, value))
    filtered.sort(key=lambda x: (x[0], x[1]))
    query = "&".join(f"{quote_plus(k)}={quote_plus(v)}" for k, v in filtered)

    return urlunparse((parsed.scheme.lower(), netloc, parsed.path or "/", "", query, ""))


def _extract_ddg_links(search_html: str) -> list[tuple[str, str]]:
    pattern = re.compile(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    links: list[tuple[str, str]] = []
    for href, title_html in pattern.findall(search_html):
        clean_href = html.unescape(href).strip()
        if not clean_href:
            continue
        parsed = urlparse(clean_href)
        if "duckduckgo.com" in (parsed.netloc or "") and parsed.path.startswith("/l/"):
            redirect_target = parse_qs(parsed.query).get("uddg", [""])[0]
            clean_href = unquote(redirect_target).strip() or clean_href

        title = _sanitize_text(title_html)
        if clean_href:
            links.append((title or "Untitled", clean_href))
    return links


def _sanitize_text(text: str) -> str:
    no_script = re.sub(
        r"(?is)<(script|style|noscript|iframe|svg|canvas|object|embed)[^>]*>.*?</\1>",
        " ",
        text,
    )
    no_tags = re.sub(r"(?is)<[^>]+>", " ", no_script)
    unescaped = html.unescape(no_tags)
    collapsed = re.sub(r"\s+", " ", unescaped).strip()
    return collapsed


def _extract_publication_date(raw_html: str) -> str | None:
    meta_patterns = [
        r'property="article:published_time"\s+content="([^"]+)"',
        r'name="article:published_time"\s+content="([^"]+)"',
        r'name="pubdate"\s+content="([^"]+)"',
        r'name="publishdate"\s+content="([^"]+)"',
        r'name="date"\s+content="([^"]+)"',
        r'itemprop="datePublished"\s+datetime="([^"]+)"',
    ]
    for pattern in meta_patterns:
        match = re.search(pattern, raw_html, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip() or None
    return None


def _extract_title(raw_html: str, fallback: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw_html)
    if not match:
        return fallback
    title = _sanitize_text(match.group(1))
    return title or fallback


def _build_excerpt(query: str, clean_text: str, max_len: int = 320) -> str:
    if not clean_text:
        return ""
    terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 2]
    lowered = clean_text.lower()
    best_pos = -1
    for term in terms:
        pos = lowered.find(term)
        if pos >= 0:
            best_pos = pos
            break

    if best_pos < 0:
        return clean_text[:max_len].strip()

    start = max(0, best_pos - 80)
    end = min(len(clean_text), best_pos + max_len)
    return clean_text[start:end].strip()


def _fetch_url_content(
    *,
    client: httpx.Client,
    url: str,
    timeout_sec: float,
    max_bytes: int,
    max_redirects: int = 3,
) -> tuple[str, str]:
    current_url = url
    for _ in range(max_redirects + 1):
        if not is_safe_remote_url(current_url):
            raise WebResearchError("Blocked unsafe or local URL")

        response = client.get(
            current_url,
            timeout=timeout_sec,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9,tr;q=0.8"},
        )

        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("location", "").strip()
            if not location:
                raise WebResearchError("Redirect without location")
            next_url = urljoin(current_url, location)
            if not is_safe_remote_url(next_url):
                raise WebResearchError("Blocked redirect target")
            current_url = next_url
            continue

        if response.status_code != 200:
            raise WebResearchError(f"HTTP status {response.status_code}")

        content = response.text
        if len(content.encode("utf-8", errors="ignore")) > max_bytes:
            content = content.encode("utf-8", errors="ignore")[:max_bytes].decode("utf-8", errors="ignore")
        return current_url, content

    raise WebResearchError("Too many redirects")


def perform_web_research(
    user_query: str,
    *,
    search_query: str | None = None,
    max_sources: int = 5,
    timeout_sec: float = 8.0,
    max_bytes_per_page: int = 400_000,
) -> WebResearchResult:
    query = (search_query or user_query or "").strip()
    if not query:
        raise WebResearchError("Search query is empty")

    access_date = _now_iso()
    warnings: list[str] = []
    search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

    with httpx.Client() as client:
        resolved_search_url, search_html = _fetch_url_content(
            client=client,
            url=search_url,
            timeout_sec=timeout_sec,
            max_bytes=max_bytes_per_page,
        )
        _ = resolved_search_url

        candidates = _extract_ddg_links(search_html)
        if not candidates:
            raise WebResearchError("No web sources found for query")

        dedup: dict[str, tuple[str, str]] = {}
        for title, candidate_url in candidates:
            normalized = _normalize_url(candidate_url)
            if normalized in dedup:
                continue
            dedup[normalized] = (title, candidate_url)
            if len(dedup) >= max_sources:
                break

        sources: list[WebSource] = []
        for normalized_url, (candidate_title, _) in dedup.items():
            try:
                final_url, html_payload = _fetch_url_content(
                    client=client,
                    url=normalized_url,
                    timeout_sec=timeout_sec,
                    max_bytes=max_bytes_per_page,
                )
                clean_content = _sanitize_text(html_payload)
                if not clean_content:
                    warnings.append(f"Empty content: {final_url}")
                    continue

                title = _extract_title(html_payload, fallback=candidate_title)
                publication_date = _extract_publication_date(html_payload)
                excerpt = _build_excerpt(query, clean_content)
                domain = (urlparse(final_url).hostname or "").lower()

                sources.append(
                    WebSource(
                        source_title=title,
                        source_url=final_url,
                        domain=domain,
                        publication_date=publication_date,
                        access_date=access_date,
                        extracted_content=clean_content[:5000],
                        relevant_excerpt=excerpt,
                    )
                )
            except WebResearchError as exc:
                warnings.append(f"Skipped source ({normalized_url}): {exc}")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Source fetch failed ({normalized_url}): {exc}")

    if not sources:
        raise WebResearchError("No readable sources after security checks")

    return WebResearchResult(
        user_query=user_query,
        search_query=query,
        access_date=access_date,
        sources=sources,
        warnings=warnings,
    )


def format_web_research_markdown(result: WebResearchResult) -> str:
    lines = [
        "## Web Araştırma Sonuçları",
        "",
        f"- Sorgu: **{result.search_query}**",
        f"- Erişim Tarihi: **{result.access_date}**",
        "",
    ]

    for idx, src in enumerate(result.sources, start=1):
        pub_date = src.publication_date or "bulunamadı"
        lines.extend(
            [
                f"### {idx}) {src.source_title}",
                f"- URL: [{src.source_url}]({src.source_url})",
                f"- Domain: {src.domain}",
                f"- Publication Date: {pub_date}",
                f"- Access Date: {src.access_date}",
                f"- Relevant Excerpt: {src.relevant_excerpt}",
                "",
            ]
        )

    if result.warnings:
        lines.append("### Uyarılar")
        for warning in result.warnings:
            lines.append(f"- {warning}")

    lines.append("")
    lines.append(
        "Not: Yukarıdaki alıntılar kaynaklardan çıkarılmıştır. Model yorumları ayrıca üretilir."
    )
    return "\n".join(lines)


def build_research_document_for_rag(source: WebSource) -> str:
    publication = source.publication_date or "unknown"
    return (
        "[WEB SOURCE]\n"
        f"Title: {source.source_title}\n"
        f"URL: {source.source_url}\n"
        f"Domain: {source.domain}\n"
        f"Publication Date: {publication}\n"
        f"Access Date: {source.access_date}\n"
        f"Excerpt: {source.relevant_excerpt}\n\n"
        f"Content:\n{source.extracted_content}\n"
    )


__all__ = [
    "WebResearchError",
    "WebResearchResult",
    "WebSource",
    "build_research_document_for_rag",
    "format_web_research_markdown",
    "is_safe_remote_url",
    "perform_web_research",
]
