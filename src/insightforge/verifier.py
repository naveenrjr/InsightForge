from __future__ import annotations

import html
import ipaddress
import re
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import EvidenceCheck


URL_PATTERN = re.compile(r"https?://[^\s<>()\"']+")
TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", flags=re.IGNORECASE | re.DOTALL)
TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(slots=True)
class VerificationConfig:
    enabled: bool = True
    timeout_seconds: int = 3
    max_urls: int = 5
    max_bytes: int = 120000
    allow_private_hosts: bool = False


Fetcher = Callable[[str, int, int], tuple[int, str, str]]


def verify_output_sources(
    text: str,
    config: VerificationConfig,
    fetcher: Fetcher | None = None,
) -> list[EvidenceCheck]:
    if not config.enabled:
        return []

    urls = extract_urls(text)[: config.max_urls]
    verifier = fetcher or _default_fetcher
    evidence_checks: list[EvidenceCheck] = []

    for url in urls:
        host = urlparse(url).hostname
        if not host:
            evidence_checks.append(
                EvidenceCheck(
                    url=url,
                    status="invalid",
                    category="url",
                    detail="The cited URL could not be parsed.",
                )
            )
            continue

        if not config.allow_private_hosts and _is_private_host(host):
            evidence_checks.append(
                EvidenceCheck(
                    url=url,
                    status="blocked",
                    category="safety",
                    detail="Private or local hosts are blocked from verification by default.",
                )
            )
            continue

        try:
            http_status, content_type, body = verifier(url, config.timeout_seconds, config.max_bytes)
        except HTTPError as exc:
            evidence_checks.append(
                EvidenceCheck(
                    url=url,
                    status="unreachable",
                    category="http",
                    detail=f"Source responded with HTTP {exc.code}.",
                    http_status=exc.code,
                )
            )
            continue
        except URLError as exc:
            evidence_checks.append(
                EvidenceCheck(
                    url=url,
                    status="unreachable",
                    category="network",
                    detail=f"Source could not be reached: {exc.reason}.",
                )
            )
            continue
        except TimeoutError:
            evidence_checks.append(
                EvidenceCheck(
                    url=url,
                    status="timeout",
                    category="network",
                    detail="Source verification timed out.",
                )
            )
            continue
        except ValueError as exc:
            evidence_checks.append(
                EvidenceCheck(
                    url=url,
                    status="invalid",
                    category="url",
                    detail=str(exc),
                )
            )
            continue

        title = extract_title(body)
        snippet = extract_snippet(body)
        evidence_checks.append(
            EvidenceCheck(
                url=url,
                status="reachable",
                category="http",
                detail="Source was fetched successfully.",
                http_status=http_status,
                content_type=content_type,
                title=title,
                snippet=snippet,
            )
        )

    return evidence_checks


def extract_urls(text: str) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for match in URL_PATTERN.findall(text):
        normalized = match.rstrip(".,);:]!?'\"")
        if normalized not in seen:
            seen.add(normalized)
            results.append(normalized)
    return results


def extract_title(body: str) -> str:
    match = TITLE_PATTERN.search(body)
    if not match:
        return ""
    title = html.unescape(match.group(1))
    return WHITESPACE_PATTERN.sub(" ", TAG_PATTERN.sub(" ", title)).strip()[:160]


def extract_snippet(body: str) -> str:
    text = html.unescape(TAG_PATTERN.sub(" ", body))
    return WHITESPACE_PATTERN.sub(" ", text).strip()[:280]


def _default_fetcher(url: str, timeout_seconds: int, max_bytes: int) -> tuple[int, str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "InsightForge/0.1 (+https://github.com/your-org/InsightForge)"
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        status = getattr(response, "status", 200)
        content_type = response.headers.get("Content-Type", "")
        body = response.read(max_bytes).decode("utf-8", errors="replace")
    return status, content_type, body


def _is_private_host(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized in {"localhost"} or normalized.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
