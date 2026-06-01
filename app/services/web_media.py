import html
import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from loguru import logger

from app.config import config
from app.models.schema import NewsMediaAsset, NewsStory
from app.services.news_sources.base import is_direct_video_url


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


def _timeout() -> tuple[int, int]:
    return (10, int(config.app.get("news_web_media_timeout", 20)))


def extract_urls(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s<>'\")]+", text or "")
    deduped = []
    seen = set()
    for url in urls:
        cleaned = url.rstrip(".,;:!?")
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped


def _fetch(url: str) -> tuple[str, str]:
    response = requests.get(
        url,
        headers=HEADERS,
        proxies=config.proxy,
        timeout=_timeout(),
        allow_redirects=True,
    )
    response.raise_for_status()
    return response.url, response.text


def _search_urls(query: str, limit: int = 4) -> list[str]:
    if not config.app.get("news_web_search_enabled", True):
        return []

    search_url = "https://duckduckgo.com/html/"
    response = requests.get(
        search_url,
        params={"q": f"{query} video"},
        headers=HEADERS,
        proxies=config.proxy,
        timeout=_timeout(),
    )
    response.raise_for_status()
    urls = []
    for href in re.findall(r'href="([^"]+)"', response.text):
        href = html.unescape(href)
        parsed = urlparse(href)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            uddg = parse_qs(parsed.query).get("uddg", [""])[0]
            href = unquote(uddg)
        if href.startswith("http") and "duckduckgo.com" not in urlparse(href).netloc:
            urls.append(href)
        if len(urls) >= limit:
            break
    return urls


def _search_query_variants(story: NewsStory) -> list[str]:
    candidates = [
        story.title,
        " ".join([story.title, story.provider]).strip(),
        " ".join([story.title, story.category]).strip(),
    ]
    variants = []
    seen = set()
    for candidate in candidates:
        cleaned = re.sub(r"\s+", " ", (candidate or "").strip())
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            variants.append(cleaned)
    return variants


def _candidate_video_urls(page_url: str, content: str) -> list[str]:
    candidates = []
    patterns = [
        r'<meta[^>]+property=["\']og:video(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']twitter:player:stream["\'][^>]+content=["\']([^"\']+)["\']',
        r'<video[^>]+src=["\']([^"\']+)["\']',
        r'<source[^>]+src=["\']([^"\']+)["\'][^>]+type=["\']video/[^"\']+["\']',
        r'https?://[^\s"\'<>]+?\.(?:mp4|mov|m4v|webm)(?:\?[^\s"\'<>]*)?',
    ]
    for pattern in patterns:
        for match in re.findall(pattern, content, flags=re.IGNORECASE):
            url = html.unescape(match)
            url = urljoin(page_url, url)
            if is_direct_video_url(url) and url not in candidates:
                candidates.append(url)
    return candidates


def discover_story_media(story: NewsStory, limit: int = 3) -> list[NewsMediaAsset]:
    urls = []
    urls.extend(extract_urls(story.summary))
    if story.url:
        urls.append(story.url)
    if config.app.get("news_web_search_enabled", True) and story.title:
        for query in _search_query_variants(story):
            try:
                urls.extend(_search_urls(query))
            except Exception as exc:
                logger.warning(f"web media search failed for '{query}': {str(exc)}")

    assets = []
    seen = {asset.url for asset in story.media}
    for url in urls:
        if len(assets) >= limit:
            break
        try:
            resolved_url, content = _fetch(url)
            if is_direct_video_url(resolved_url) and resolved_url not in seen:
                assets.append(
                    NewsMediaAsset(
                        provider="web",
                        url=resolved_url,
                        media_type="video",
                        title=story.title,
                        source_url=url,
                    )
                )
                seen.add(resolved_url)
                continue

            for video_url in _candidate_video_urls(resolved_url, content):
                if video_url in seen:
                    continue
                assets.append(
                    NewsMediaAsset(
                        provider="web",
                        url=video_url,
                        media_type="video",
                        title=story.title,
                        source_url=resolved_url,
                    )
                )
                seen.add(video_url)
                if len(assets) >= limit:
                    break
        except Exception as exc:
            logger.debug(f"failed to discover media from {url}: {str(exc)}")
    return assets
