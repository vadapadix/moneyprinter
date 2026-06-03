import html
import json
import os
import shutil
import time
import webbrowser
from pathlib import Path

from loguru import logger

from app.config import config
from app.models.schema import PublishPrivacy, SocialMetadata
from app.services.publishers.base import PublishResult, Publisher


class TikTokBrowserPublisher(Publisher):
    platform = "tiktok"

    def __init__(self):
        self.enabled = bool(config.app.get("tiktok_browser_upload_enabled", False))
        self.upload_url = str(
            config.app.get(
                "tiktok_browser_upload_url",
                "https://www.tiktok.com/tiktokstudio/upload",
            )
        )
        self.upload_dir = str(
            config.app.get("tiktok_browser_upload_dir", "storage/social_uploads/tiktok")
        )
        self.open_upload_page = bool(config.app.get("tiktok_browser_open_upload_page", True))
        self.copy_caption = bool(config.app.get("tiktok_browser_copy_caption", True))

    def is_configured(self) -> bool:
        return self.enabled

    def publish(
        self,
        video_path: str,
        metadata: SocialMetadata,
        privacy: PublishPrivacy = PublishPrivacy.private,
    ) -> PublishResult:
        if not self.is_configured():
            return PublishResult(
                platform=self.platform,
                success=False,
                status="not_configured",
                error="TikTok browser-assisted upload is not enabled",
            )

        if not video_path or not os.path.exists(video_path):
            return PublishResult(
                platform=self.platform,
                success=False,
                status="failed",
                error=f"Video file not found: {video_path}",
            )

        caption = build_tiktok_caption(metadata)
        package = self._write_upload_package(video_path, metadata, caption, privacy)
        clipboard_copied = False
        browser_opened = False

        if self.copy_caption:
            clipboard_copied = copy_text_to_clipboard(caption)
        if self.open_upload_page:
            browser_opened = open_upload_page(self.upload_url)

        return PublishResult(
            platform=self.platform,
            success=True,
            status="manual_review_required",
            url=self.upload_url,
            raw={
                "mode": "browser_assist",
                "requires_user_action": True,
                "message": (
                    "TikTok upload package is ready. Review the opened TikTok page, "
                    "select the prepared MP4 if needed, paste the copied caption, "
                    "then click Post manually."
                ),
                "video_path": os.path.abspath(video_path),
                "package_dir": package["package_dir"],
                "caption_path": package["caption_path"],
                "metadata_path": package["metadata_path"],
                "helper_page_path": package["helper_page_path"],
                "clipboard_copied": clipboard_copied,
                "browser_opened": browser_opened,
                "privacy": privacy.value,
            },
        )

    def _write_upload_package(
        self,
        video_path: str,
        metadata: SocialMetadata,
        caption: str,
        privacy: PublishPrivacy,
    ) -> dict[str, str]:
        base_dir = Path(self.upload_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        package_dir = base_dir / time.strftime("%Y%m%d-%H%M%S")
        package_dir.mkdir(parents=True, exist_ok=False)

        source_video = Path(video_path)
        prepared_video = package_dir / source_video.name
        shutil.copy2(source_video, prepared_video)

        caption_path = package_dir / "caption.txt"
        caption_path.write_text(caption, encoding="utf-8")

        metadata_path = package_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "platform": self.platform,
                    "mode": "browser_assist",
                    "title": metadata.title,
                    "description": metadata.description,
                    "hashtags": metadata.hashtags,
                    "caption": caption,
                    "privacy": privacy.value,
                    "source_video_path": os.path.abspath(video_path),
                    "prepared_video_path": str(prepared_video.resolve()),
                    "upload_url": self.upload_url,
                    "created_at": int(time.time()),
                    "requires_user_action": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        helper_page_path = package_dir / "open_upload.html"
        helper_page_path.write_text(
            render_helper_page(
                upload_url=self.upload_url,
                video_path=str(prepared_video.resolve()),
                caption=caption,
            ),
            encoding="utf-8",
        )

        logger.info(f"TikTok browser upload package prepared: {package_dir}")
        return {
            "package_dir": str(package_dir.resolve()),
            "caption_path": str(caption_path.resolve()),
            "metadata_path": str(metadata_path.resolve()),
            "helper_page_path": str(helper_page_path.resolve()),
        }


def build_tiktok_caption(metadata: SocialMetadata) -> str:
    caption = (metadata.platform_captions or {}).get("tiktok", "").strip()
    if not caption:
        parts = [metadata.title.strip(), metadata.description.strip()]
        caption = "\n\n".join(part for part in parts if part)

    hashtags = normalize_hashtags(metadata.hashtags)
    if hashtags:
        existing_words = {word.lower() for word in caption.split()}
        missing_hashtags = [
            tag for tag in hashtags if tag.lower() not in existing_words
        ]
        if missing_hashtags:
            caption = f"{caption}\n\n{' '.join(missing_hashtags)}".strip()
    return caption.strip() or "Generated short video"


def normalize_hashtags(hashtags: list[str]) -> list[str]:
    normalized = []
    seen = set()
    for tag in hashtags or []:
        value = str(tag).strip()
        if not value:
            continue
        if not value.startswith("#"):
            value = f"#{value}"
        key = value.lower()
        if key in seen:
            continue
        normalized.append(value)
        seen.add(key)
    return normalized


def copy_text_to_clipboard(text: str) -> bool:
    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception as ex:
        logger.warning(f"Failed to copy TikTok caption to clipboard: {ex}")
        return False


def open_upload_page(upload_url: str) -> bool:
    try:
        return bool(webbrowser.open(upload_url, new=2, autoraise=True))
    except Exception as ex:
        logger.warning(f"Failed to open TikTok upload page: {ex}")
        return False


def render_helper_page(upload_url: str, video_path: str, caption: str) -> str:
    escaped_caption = html.escape(caption)
    escaped_video_path = html.escape(video_path)
    escaped_upload_url = html.escape(upload_url, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>TikTok Upload Helper</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{ font-family: Arial, sans-serif; max-width: 880px; margin: 40px auto; line-height: 1.5; }}
    textarea {{ width: 100%; height: 220px; }}
    code {{ background: #f3f3f3; padding: 2px 4px; }}
    a {{ display: inline-block; margin: 12px 0; }}
  </style>
</head>
<body>
  <h1>TikTok upload is ready</h1>
  <p>Open TikTok Studio, select this video file, paste the caption, review, then post manually.</p>
  <p><a href="{escaped_upload_url}" target="_blank" rel="noreferrer">Open TikTok Studio upload</a></p>
  <p><strong>Video file:</strong> <code>{escaped_video_path}</code></p>
  <label for="caption"><strong>Caption</strong></label>
  <textarea id="caption" readonly>{escaped_caption}</textarea>
</body>
</html>
"""
