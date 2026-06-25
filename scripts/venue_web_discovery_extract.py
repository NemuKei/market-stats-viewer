"""Fetch official/semi-official page text for Venue Web Discovery.

Default extractor is requests+BeautifulSoup. Crawl4AI is an optional fallback
for JS-rendered or complex official pages and is never required for DB reads.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ExtractorName = Literal["auto", "requests_bs4", "crawl4ai"]
ALLOWED_EXTRACTORS = {"auto", "requests_bs4", "crawl4ai"}


@dataclass
class ExtractionResult:
    url: str
    content_extractor: str
    success: bool
    text: str = ""
    links: list[str] = field(default_factory=list)
    status_code: int | None = None
    error: str | None = None
    fallback_error: str | None = None


class OptionalExtractorUnavailable(RuntimeError):
    """Raised when an optional content extractor is requested but unavailable."""


def compact_text(text: str) -> str:
    return " ".join(str(text or "").split())


def extract_with_requests_bs4(
    url: str,
    *,
    session: requests.Session | None = None,
    timeout_sec: int = 30,
) -> ExtractionResult:
    active_session = session or requests.Session()
    response = active_session.get(url, timeout=timeout_sec)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = compact_text(soup.get_text(" "))
    links = sorted(
        {
            urljoin(url, link.get("href", ""))
            for link in soup.find_all("a", href=True)
            if str(link.get("href") or "").strip()
        }
    )
    return ExtractionResult(
        url=url,
        content_extractor="requests_bs4",
        success=bool(text),
        text=text,
        links=links,
        status_code=int(response.status_code),
    )


async def _crawl4ai_arun(url: str) -> ExtractionResult:
    try:
        from crawl4ai import AsyncWebCrawler
    except Exception as exc:  # pragma: no cover - exercised only without optional extra
        raise OptionalExtractorUnavailable(
            "crawl4ai is not installed. Run `uv sync --extra crawl4ai` and `uv run crawl4ai-setup`."
        ) from exc

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
    text = _crawl4ai_markdown_text(result)
    links = _crawl4ai_links(result)
    success = bool(text) and bool(getattr(result, "success", True))
    error = None if success else compact_text(str(getattr(result, "error_message", "") or "crawl4ai returned no text"))
    return ExtractionResult(
        url=url,
        content_extractor="crawl4ai",
        success=success,
        text=text,
        links=links,
        status_code=getattr(result, "status_code", None),
        error=error,
    )


def extract_with_crawl4ai(url: str) -> ExtractionResult:
    return asyncio.run(_crawl4ai_arun(url))


def _crawl4ai_markdown_text(result: Any) -> str:
    markdown = getattr(result, "markdown", "")
    if isinstance(markdown, str):
        return compact_text(markdown)
    for attr in ("fit_markdown", "raw_markdown", "markdown"):
        value = getattr(markdown, attr, None)
        if value:
            return compact_text(str(value))
    return compact_text(str(markdown or ""))


def _crawl4ai_links(result: Any) -> list[str]:
    raw_links = getattr(result, "links", None)
    if isinstance(raw_links, dict):
        values: list[str] = []
        for group in raw_links.values():
            if isinstance(group, list):
                for item in group:
                    if isinstance(item, dict) and item.get("href"):
                        values.append(str(item["href"]))
                    elif isinstance(item, str):
                        values.append(item)
        return sorted(set(values))
    if isinstance(raw_links, list):
        return sorted({str(value) for value in raw_links if str(value).strip()})
    return []


def extract_url(
    url: str,
    *,
    content_extractor: ExtractorName = "auto",
    fallback_to_requests: bool = True,
    min_text_chars: int = 500,
    timeout_sec: int = 30,
) -> ExtractionResult:
    if content_extractor not in ALLOWED_EXTRACTORS:
        raise ValueError(f"unknown content_extractor: {content_extractor}")

    if content_extractor == "requests_bs4":
        return extract_with_requests_bs4(url, timeout_sec=timeout_sec)

    if content_extractor == "crawl4ai":
        try:
            return extract_with_crawl4ai(url)
        except OptionalExtractorUnavailable as exc:
            if not fallback_to_requests:
                raise
            result = extract_with_requests_bs4(url, timeout_sec=timeout_sec)
            result.fallback_error = str(exc)
            return result

    primary = extract_with_requests_bs4(url, timeout_sec=timeout_sec)
    if primary.success and len(primary.text) >= min_text_chars:
        return primary
    try:
        fallback = extract_with_crawl4ai(url)
    except OptionalExtractorUnavailable as exc:
        primary.fallback_error = str(exc)
        return primary
    if not fallback.success and fallback_to_requests:
        primary.fallback_error = fallback.error
        return primary
    return fallback


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract page text for Venue Web Discovery evidence checks.")
    parser.add_argument("url", nargs="?", help="URL to extract. Omit with --help for setup verification.")
    parser.add_argument(
        "--content-extractor",
        choices=sorted(ALLOWED_EXTRACTORS),
        default="auto",
        help="Extractor provider to use.",
    )
    parser.add_argument("--min-text-chars", type=int, default=500)
    parser.add_argument("--timeout-sec", type=int, default=30)
    parser.add_argument("--no-fallback", action="store_true", help="Do not fall back to requests_bs4.")
    parser.add_argument("--output", type=Path, help="Optional JSON output path.")
    args = parser.parse_args()

    if not args.url:
        parser.print_help()
        return 0

    result = extract_url(
        args.url,
        content_extractor=args.content_extractor,
        fallback_to_requests=not bool(args.no_fallback),
        min_text_chars=max(1, int(args.min_text_chars)),
        timeout_sec=max(1, int(args.timeout_sec)),
    )
    payload = asdict(result)
    payload["text"] = result.text[:20000]
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body, encoding="utf-8")
    else:
        print(body)
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
