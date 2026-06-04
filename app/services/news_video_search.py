import importlib
import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from loguru import logger

from app.config import config
from app.services import web_media
from app.services.news_sources.base import is_direct_video_url
from app.utils import utils


@dataclass
class NewsVideoSearchResult:
    paths: list[str]
    attempts: list[dict]


class _YtDlpLogger:
    def debug(self, message):
        logger.debug(message)

    def warning(self, message):
        logger.debug(message)

    def error(self, message):
        logger.debug(message)


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", (value or "").strip())
    return cleaned[:80] or utils.get_uuid(remove_hyphen=True)


def _iter_entries(info: dict) -> list[dict]:
    entries = info.get("entries") if isinstance(info, dict) else None
    if entries:
        return [entry for entry in entries if isinstance(entry, dict)]
    return [info] if isinstance(info, dict) else []


def _keywords(value: str) -> set[str]:
    stop_words = {
        "a",
        "an",
        "and",
        "breaking",
        "english",
        "footage",
        "from",
        "in",
        "latest",
        "news",
        "official",
        "on",
        "the",
        "to",
        "video",
        "watch",
        "with",
    }
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]{3,}", value or "")
        if token.lower() not in stop_words
    }


def _entry_title(entry: dict) -> str:
    return " ".join(
        str(entry.get(key) or "")
        for key in ("title", "alt_title", "description", "webpage_url")
    ).strip()


def _min_keyword_overlap(query_terms: set[str]) -> int:
    configured = config.app.get("news_ytdlp_min_keyword_overlap", None)
    if configured is not None:
        try:
            return max(1, int(configured))
        except (TypeError, ValueError):
            pass
    return 1 if len(query_terms) <= 3 else 2


def _min_keyword_coverage() -> float:
    try:
        return max(0.0, float(config.app.get("news_ytdlp_min_keyword_coverage", 0.25)))
    except (TypeError, ValueError):
        return 0.25


def _entry_relevance(entry: dict, query: str) -> dict:
    query_terms = _keywords(query)
    if not query_terms:
        return {
            "is_relevant": True,
            "query_terms": [],
            "entry_terms": [],
            "matched_terms": [],
            "coverage": 1.0,
            "required_overlap": 0,
        }

    entry_terms = _keywords(_entry_title(entry))
    if not entry_terms:
        return {
            "is_relevant": True,
            "query_terms": sorted(query_terms),
            "entry_terms": [],
            "matched_terms": [],
            "coverage": 0.0,
            "required_overlap": _min_keyword_overlap(query_terms),
        }

    overlap = query_terms.intersection(entry_terms)
    coverage = len(overlap) / len(query_terms)
    required_overlap = _min_keyword_overlap(query_terms)
    is_relevant = len(overlap) >= required_overlap or coverage >= _min_keyword_coverage()
    return {
        "is_relevant": is_relevant,
        "query_terms": sorted(query_terms),
        "entry_terms": sorted(entry_terms),
        "matched_terms": sorted(overlap),
        "coverage": round(coverage, 3),
        "required_overlap": required_overlap,
    }


def _accepted_relevance(entry: dict, relevance: dict) -> dict:
    return {
        "title": str(entry.get("title") or "")[:160],
        "webpage_url": str(entry.get("webpage_url") or "")[:240],
        "matched_terms": relevance["matched_terms"],
        "coverage": relevance["coverage"],
        "required_overlap": relevance["required_overlap"],
    }


def _is_relevant_entry(entry: dict, query: str) -> bool:
    return bool(_entry_relevance(entry, query)["is_relevant"])


def _english_news_query(query: str) -> str:
    query = re.sub(r"\s+", " ", (query or "").strip())
    if not query:
        return ""
    lowered = query.lower()
    if "english" in lowered and "news" in lowered:
        return query
    return f"{query} English news video"


def _query_variants(query: str, source_context: dict | None = None) -> list[str]:
    source_context = source_context or {}
    title = re.sub(r"\s+", " ", (query or source_context.get("title") or "").strip())
    provider = str(source_context.get("provider") or "").strip()
    category = str(source_context.get("category") or "").strip()
    keywords = [
        str(keyword).strip()
        for keyword in source_context.get("keywords") or []
        if str(keyword).strip()
    ][:4]

    candidates = [
        title,
        f'"{title}"',
        " ".join([title, provider]).strip(),
        " ".join([title, category]).strip(),
        " ".join([title, *keywords]).strip(),
        f"{title} latest footage",
        f"{title} official video",
        f"{title} eyewitness video",
        f"{title} press conference",
        f"{title} live report",
    ]
    variants = []
    seen = set()
    for candidate in candidates:
        cleaned = re.sub(r"\s+", " ", candidate.strip())
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            variants.append(cleaned)
    return variants


def _is_ytdlp_direct_candidate_url(url: str) -> bool:
    if not url:
        return False
    if is_direct_video_url(url):
        return True

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    video_hosts = (
        "youtube.com",
        "youtu.be",
        "tiktok.com",
        "instagram.com",
        "facebook.com",
        "fb.watch",
        "twitter.com",
        "x.com",
        "vimeo.com",
        "dailymotion.com",
        "twitch.tv",
        "rumble.com",
        "streamable.com",
        "telegram.org",
        "t.me",
    )
    return any(host == candidate or host.endswith(f".{candidate}") for candidate in video_hosts)


def _candidate_targets(query: str, limit: int, source_context: dict | None = None) -> list[dict]:
    source_context = source_context or {}
    targets = []
    source_urls = [
        str(source_context.get("source_url") or "").strip(),
        *[
            str(url or "").strip()
            for url in source_context.get("source_urls", [])
            if str(url or "").strip()
        ],
    ]
    seen_source_urls = set()
    if config.app.get("news_ytdlp_try_source_url", True):
        for source_url in source_urls:
            if not source_url or source_url in seen_source_urls:
                continue
            seen_source_urls.add(source_url)
            if _is_ytdlp_direct_candidate_url(source_url):
                targets.append({"kind": "source_url", "query": source_url, "target": source_url})
            else:
                logger.debug(f"skipping non-video source URL for yt-dlp: {source_url}")

    try:
        overfetch_multiplier = max(
            1, int(config.app.get("news_ytdlp_overfetch_multiplier", 3))
        )
    except (TypeError, ValueError):
        overfetch_multiplier = 3
    configured_results = int(config.app.get("news_ytdlp_results_per_query", 3))
    per_search_limit = max(1, min(max(configured_results, limit * overfetch_multiplier), 12))
    web_search_failed = False
    for variant in _query_variants(query, source_context):
        if config.app.get("news_ytdlp_web_search_enabled", True) and not web_search_failed:
            try:
                for url in web_media.search_video_pages(variant, limit=per_search_limit):
                    targets.append(
                        {
                            "kind": "web_search_url",
                            "query": variant,
                            "target": url,
                        }
                    )
            except Exception as exc:
                logger.warning(f"yt-dlp web video search failed for '{variant}': {exc}")
                if web_media._stop_web_search_after_error(exc):
                    web_search_failed = True

        search_query = _english_news_query(variant)
        targets.append(
            {
                "kind": "youtube_search",
                "query": variant,
                "target": f"ytsearch{per_search_limit}:{search_query}",
            }
        )
    return targets


def _downloaded_path(ydl, entry: dict) -> str:
    requested = entry.get("requested_downloads")
    if isinstance(requested, list) and requested:
        path = requested[0].get("filepath")
        if path:
            return path
    return ydl.prepare_filename(entry)


def _is_max_downloads_stop(exc: Exception) -> bool:
    return "Maximum number of downloads reached" in str(exc)


def _collect_downloaded_video_files(save_dir: str, known_paths: list[str]) -> list[str]:
    known = {os.path.abspath(path) for path in known_paths}
    extensions = {".mp4", ".mov", ".mkv", ".webm"}
    candidates = []
    for filename in os.listdir(save_dir):
        path = os.path.join(save_dir, filename)
        if not os.path.isfile(path):
            continue
        if os.path.abspath(path) in known:
            continue
        if os.path.splitext(filename)[1].lower() not in extensions:
            continue
        candidates.append(path)
    return sorted(candidates, key=lambda path: os.path.getmtime(path), reverse=True)


def search_and_download_report(
    query: str,
    save_dir: str,
    limit: int = 2,
    source_context: dict | None = None,
) -> NewsVideoSearchResult:
    if not config.app.get("news_ytdlp_enabled", True):
        return NewsVideoSearchResult(paths=[], attempts=[])
    query = (query or "").strip()
    if not query or limit <= 0:
        return NewsVideoSearchResult(paths=[], attempts=[])

    try:
        yt_dlp = importlib.import_module("yt_dlp")
    except Exception:
        logger.warning("yt-dlp is not installed; skipping deep news video search")
        return NewsVideoSearchResult(paths=[], attempts=[])

    os.makedirs(save_dir, exist_ok=True)
    outtmpl = os.path.join(save_dir, f"news-{_safe_filename(query)}-%(id)s.%(ext)s")
    ydl_opts = {
        "format": config.app.get(
            "news_ytdlp_format",
            "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/best",
        ),
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "socket_timeout": int(config.app.get("news_ytdlp_timeout", 30)),
        "max_downloads": max(1, limit),
        "logger": _YtDlpLogger(),
    }
    if config.proxy:
        proxy = config.proxy.get("https") or config.proxy.get("http")
        if proxy:
            ydl_opts["proxy"] = proxy

    downloaded = []
    attempts = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for target_info in _candidate_targets(query, limit, source_context):
                if len(downloaded) >= limit:
                    break
                target = target_info["target"]
                attempt = {
                    "kind": target_info["kind"],
                    "query": target_info["query"],
                    "target": target,
                    "downloaded_count": 0,
                    "accepted_relevance": [],
                    "skipped_irrelevant_count": 0,
                    "skipped_relevance": [],
                    "error": "",
                }
                try:
                    info = ydl.extract_info(target, download=True)
                    for entry in _iter_entries(info):
                        relevance = _entry_relevance(entry, query)
                        if not relevance["is_relevant"]:
                            attempt["skipped_irrelevant_count"] += 1
                            attempt["skipped_relevance"].append(
                                {
                                    "title": str(entry.get("title") or "")[:160],
                                    "matched_terms": relevance["matched_terms"],
                                    "coverage": relevance["coverage"],
                                    "required_overlap": relevance["required_overlap"],
                                }
                            )
                            continue
                        path = _downloaded_path(ydl, entry)
                        if path and os.path.isfile(path) and path not in downloaded:
                            downloaded.append(path)
                            attempt["downloaded_count"] += 1
                            attempt["accepted_relevance"].append(
                                _accepted_relevance(entry, relevance)
                            )
                        if len(downloaded) >= limit:
                            break
                except Exception as exc:
                    if _is_max_downloads_stop(exc):
                        recovered_paths = _collect_downloaded_video_files(
                            save_dir, downloaded
                        )
                        for path in recovered_paths:
                            if len(downloaded) >= limit:
                                break
                            downloaded.append(path)
                            attempt["downloaded_count"] += 1
                            attempt["accepted_relevance"].append(
                                {
                                    "title": os.path.basename(path)[:160],
                                    "webpage_url": target[:240],
                                    "matched_terms": [],
                                    "coverage": 0.0,
                                    "required_overlap": 0,
                                    "recovered_after": "max_downloads",
                                }
                            )
                        logger.info(
                            "yt-dlp reached max downloads for "
                            f"{target}; recovered {len(recovered_paths)} downloaded file(s)"
                        )
                    else:
                        attempt["error"] = str(exc)
                        logger.debug(f"yt-dlp target failed for {target}: {exc}")
                attempts.append(attempt)
    except Exception as exc:
        logger.warning(f"yt-dlp news video search failed: {exc}")
    return NewsVideoSearchResult(paths=downloaded, attempts=attempts)


def search_and_download(
    query: str,
    save_dir: str,
    limit: int = 2,
    source_context: dict | None = None,
) -> list[str]:
    return search_and_download_report(
        query=query,
        save_dir=save_dir,
        limit=limit,
        source_context=source_context,
    ).paths
