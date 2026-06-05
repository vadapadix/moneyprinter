import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests
from loguru import logger

from app.config import config


MAX_ARTICLE_CHARS = 5000


class _ArticleHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._current_tag = ""
        self._current_attrs = {}
        self._current_text = []
        self.paragraphs = []
        self.meta_descriptions = []
        self.json_ld_blocks = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_dict = {key.lower(): value for key, value in attrs}
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self._skip_depth += 1
            if tag == "script" and attrs_dict.get("type", "").lower() == "application/ld+json":
                self._skip_depth -= 1
                self._current_tag = "script_json_ld"
                self._current_text = []
            return

        if self._skip_depth:
            return

        if tag == "meta":
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            if name in {"description", "og:description", "twitter:description"}:
                content = attrs_dict.get("content", "")
                if content:
                    self.meta_descriptions.append(content)
            return

        if tag in {"p", "h1", "h2", "li"}:
            self._current_tag = tag
            self._current_attrs = attrs_dict
            self._current_text = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._current_tag == "script_json_ld" and tag == "script":
            block = "".join(self._current_text).strip()
            if block:
                self.json_ld_blocks.append(block)
            self._current_tag = ""
            self._current_text = []
            return

        if tag in {"script", "style", "noscript", "svg", "nav", "footer"} and self._skip_depth:
            self._skip_depth -= 1
            return

        if self._skip_depth:
            return

        if tag == self._current_tag:
            text = _clean_text(" ".join(self._current_text))
            if _looks_like_article_text(text):
                self.paragraphs.append(text)
            self._current_tag = ""
            self._current_attrs = {}
            self._current_text = []

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._current_tag:
            self._current_text.append(data)


def _clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _looks_like_article_text(value: str) -> bool:
    if len(value) < 35:
        return False
    lower = value.lower()
    blocked_phrases = (
        "sign up",
        "subscribe",
        "cookie",
        "privacy policy",
        "advertisement",
        "all rights reserved",
        "follow us",
        "share this",
    )
    return not any(phrase in lower for phrase in blocked_phrases)


def _iter_json_values(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_json_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_json_values(child)


def _extract_json_ld_article_text(blocks: list[str]) -> list[str]:
    extracted = []
    for block in blocks:
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue
        for item in _iter_json_values(payload):
            article_body = item.get("articleBody") or item.get("description")
            if isinstance(article_body, str):
                cleaned = _clean_text(article_body)
                if _looks_like_article_text(cleaned):
                    extracted.append(cleaned)
    return extracted


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        key = re.sub(r"\W+", "", item.lower())[:140]
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _allowed_url(url: str) -> bool:
    parsed = urlparse(url or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def fetch_article_text(url: str) -> str:
    if not config.app.get("news_article_text_enabled", True):
        return ""
    if not _allowed_url(url):
        return ""

    max_chars = int(config.app.get("news_article_text_max_chars", MAX_ARTICLE_CHARS))
    timeout = (
        float(config.app.get("news_article_connect_timeout", 5)),
        float(config.app.get("news_article_read_timeout", 15)),
    )
    headers = {
        "User-Agent": config.app.get(
            "news_article_user_agent",
            "Mozilla/5.0 (compatible; MoneyPrinterTurbo/1.2; +https://example.com)",
        )
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.warning(f"failed to fetch news article text: {url}, error: {exc}")
        return ""

    content_type = response.headers.get("content-type", "").lower()
    if "html" not in content_type and "<html" not in response.text[:500].lower():
        return ""

    parser = _ArticleHTMLParser()
    try:
        parser.feed(response.text)
    except Exception as exc:
        logger.warning(f"failed to parse news article html: {url}, error: {exc}")
        return ""

    candidates = [
        *_extract_json_ld_article_text(parser.json_ld_blocks),
        *parser.meta_descriptions,
        *parser.paragraphs,
    ]
    text = "\n".join(_dedupe_preserve_order([_clean_text(item) for item in candidates]))
    return text[:max_chars].strip()
