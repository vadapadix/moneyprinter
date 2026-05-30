from dataclasses import dataclass
from typing import Any

from app.models.schema import PublishPrivacy, SocialMetadata


@dataclass
class PublishResult:
    platform: str
    success: bool
    status: str
    post_id: str = ""
    url: str = ""
    error: str = ""
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "success": self.success,
            "status": self.status,
            "post_id": self.post_id,
            "url": self.url,
            "error": self.error,
            "raw": self.raw or {},
        }


class Publisher:
    platform = ""

    def is_configured(self) -> bool:
        raise NotImplementedError

    def publish(
        self,
        video_path: str,
        metadata: SocialMetadata,
        privacy: PublishPrivacy = PublishPrivacy.private,
    ) -> PublishResult:
        raise NotImplementedError
