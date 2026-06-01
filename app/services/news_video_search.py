import importlib
import os
import re

from loguru import logger

from app.config import config
from app.utils import utils


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", (value or "").strip())
    return cleaned[:80] or utils.get_uuid(remove_hyphen=True)


def _iter_entries(info: dict) -> list[dict]:
    entries = info.get("entries") if isinstance(info, dict) else None
    if entries:
        return [entry for entry in entries if isinstance(entry, dict)]
    return [info] if isinstance(info, dict) else []


def search_and_download(query: str, save_dir: str, limit: int = 2) -> list[str]:
    if not config.app.get("news_ytdlp_enabled", True):
        return []
    query = (query or "").strip()
    if not query or limit <= 0:
        return []

    try:
        yt_dlp = importlib.import_module("yt_dlp")
    except Exception:
        logger.warning("yt-dlp is not installed; skipping deep news video search")
        return []

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
        "max_downloads": limit,
    }
    if config.proxy:
        proxy = config.proxy.get("https") or config.proxy.get("http")
        if proxy:
            ydl_opts["proxy"] = proxy

    search_target = f"ytsearch{limit}:{query}"
    downloaded = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_target, download=True)
            for entry in _iter_entries(info):
                path = entry.get("requested_downloads", [{}])[0].get("filepath")
                if not path:
                    path = ydl.prepare_filename(entry)
                if path and os.path.isfile(path) and path not in downloaded:
                    downloaded.append(path)
                if len(downloaded) >= limit:
                    break
    except Exception as exc:
        logger.warning(f"yt-dlp news video search failed: {exc}")
    return downloaded
