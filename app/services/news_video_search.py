import importlib
import os
import re
from dataclasses import dataclass

from loguru import logger

from app.config import config
from app.services import web_media
from app.utils import utils


@dataclass
class NewsVideoSearchResult:
    paths: list[str]
    attempts: list[dict]


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


def _is_relevant_entry(entry: dict, query: str) -> bool:
    query_terms = _keywords(query)
    if not query_terms:
        return True

    entry_terms = _keywords(_entry_title(entry))
    if not entry_terms:
        return True

    overlap = query_terms.intersection(entry_terms)
    if len(overlap) >= 2:
        return True
    return len(overlap) >= 1 and len(query_terms) <= 3


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

    candidates = [
        title,
        " ".join([title, provider]).strip(),
        " ".join([title, category]).strip(),
        f"{title} latest footage",
        f"{title} official video",
        f"{title} eyewitness video",
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


def _candidate_targets(query: str, limit: int, source_context: dict | None = None) -> list[dict]:
    source_context = source_context or {}
    targets = []
    source_url = str(source_context.get("source_url") or "").strip()
    if source_url and config.app.get("news_ytdlp_try_source_url", True):
        targets.append({"kind": "source_url", "query": source_url, "target": source_url})

    per_search_limit = max(1, min(limit, int(config.app.get("news_ytdlp_results_per_query", 3))))
    for variant in _query_variants(query, source_context):
        if config.app.get("news_ytdlp_web_search_enabled", True):
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
                    "skipped_irrelevant_count": 0,
                    "error": "",
                }
                try:
                    info = ydl.extract_info(target, download=True)
                    for entry in _iter_entries(info):
                        if not _is_relevant_entry(entry, query):
                            attempt["skipped_irrelevant_count"] += 1
                            continue
                        path = _downloaded_path(ydl, entry)
                        if path and os.path.isfile(path) and path not in downloaded:
                            downloaded.append(path)
                            attempt["downloaded_count"] += 1
                        if len(downloaded) >= limit:
                            break
                except Exception as exc:
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
