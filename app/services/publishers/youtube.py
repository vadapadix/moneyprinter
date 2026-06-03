import json
import os

import requests
from loguru import logger

from app.config import config
from app.models.schema import PublishPrivacy, SocialMetadata
from app.services import social_metadata, youtube_oauth
from app.services.publishers.base import PublishResult, Publisher


class YouTubeShortsPublisher(Publisher):
    platform = "youtube"
    API_URL = "https://www.googleapis.com/upload/youtube/v3/videos"

    def __init__(self):
        self.enabled = bool(
            config.app.get("youtube_upload_enabled", False) or youtube_oauth.is_configured()
        )
        self.access_token = youtube_oauth.get_valid_access_token()
        self.default_privacy = config.app.get("youtube_privacy_status", "private")

    def is_configured(self) -> bool:
        return bool(self.enabled and self.access_token)

    def build_upload_body(
        self,
        video_path: str,
        metadata: SocialMetadata,
        privacy: PublishPrivacy = PublishPrivacy.private,
    ) -> tuple[dict, SocialMetadata, dict]:
        normalized_metadata = social_metadata.normalize_metadata(
            metadata,
            default_title=os.path.splitext(os.path.basename(video_path))[0],
        )
        privacy_status = privacy.value if privacy else self.default_privacy
        if privacy_status == "draft":
            privacy_status = "private"

        body = {
            "snippet": {
                "title": normalized_metadata.title,
                "description": normalized_metadata.description,
                "tags": normalized_metadata.youtube_tags,
                "categoryId": normalized_metadata.category_id or "22",
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": normalized_metadata.contains_synthetic_media,
            },
        }
        quality = {
            "title": normalized_metadata.title,
            "title_source": "metadata" if metadata.title == normalized_metadata.title else "normalized_fallback",
            "description_length": len(normalized_metadata.description or ""),
            "tag_count": len(normalized_metadata.youtube_tags or []),
            "has_shorts_marker": "#shorts" in (
                f"{normalized_metadata.title} {normalized_metadata.description} "
                f"{' '.join(normalized_metadata.hashtags)}"
            ).lower(),
            "contains_synthetic_media": normalized_metadata.contains_synthetic_media,
            "privacy_status": privacy_status,
        }
        return body, normalized_metadata, quality

    def _upload_once(self, video_path: str, body: dict) -> requests.Response:
        with open(video_path, "rb") as video_file:
            return requests.post(
                self.API_URL,
                params={"part": "snippet,status", "uploadType": "multipart"},
                headers={"Authorization": f"Bearer {self.access_token}"},
                files={
                    "metadata": (
                        "metadata",
                        json.dumps(body),
                        "application/json; charset=UTF-8",
                    ),
                    "media": (os.path.basename(video_path), video_file, "video/*"),
                },
                timeout=300,
            )

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
                status="disabled",
                error="YouTube upload is not configured",
            )

        if not os.path.exists(video_path):
            return PublishResult(
                platform=self.platform,
                success=False,
                status="failed",
                error=f"Video file not found: {video_path}",
            )

        body, normalized_metadata, quality = self.build_upload_body(
            video_path=video_path,
            metadata=metadata,
            privacy=privacy,
        )

        try:
            response = self._upload_once(video_path, body)
            if response.status_code == 401:
                refresh_result = youtube_oauth.refresh_access_token()
                if refresh_result.get("success"):
                    self.access_token = config.app.get("youtube_access_token", "")
                    response = self._upload_once(video_path, body)
            response.raise_for_status()
            payload = response.json()
            video_id = str(payload.get("id", ""))
            return PublishResult(
                platform=self.platform,
                success=bool(video_id),
                status="uploaded" if video_id else "failed",
                post_id=video_id,
                url=f"https://www.youtube.com/shorts/{video_id}" if video_id else "",
                raw={
                    **payload,
                    "upload_body": body,
                    "normalized_metadata": normalized_metadata.model_dump(),
                    "metadata_quality": quality,
                },
            )
        except requests.exceptions.HTTPError as exc:
            response_text = ""
            if exc.response is not None:
                response_text = exc.response.text[:2000]
            logger.error(f"YouTube upload failed: {str(exc)} {response_text}")
            error = str(exc)
            if response_text:
                error = f"{error}; response={response_text}"
            return PublishResult(
                platform=self.platform,
                success=False,
                status="failed",
                error=error,
            )
        except requests.exceptions.RequestException as exc:
            logger.error(f"YouTube upload failed: {str(exc)}")
            return PublishResult(
                platform=self.platform,
                success=False,
                status="failed",
                error=str(exc),
            )
