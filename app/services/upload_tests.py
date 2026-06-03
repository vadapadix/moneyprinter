from loguru import logger

from app.models.schema import PublishPrivacy, SocialMetadata
from app.services import social_publisher
from app.utils import utils


TEST_UPLOAD_PLATFORMS = ("tiktok", "youtube", "both")


def build_test_upload_metadata() -> SocialMetadata:
    return SocialMetadata(
        title="DOLIDE News private upload test",
        description="Private upload test for DOLIDE News automation. #Shorts",
        hashtags=["#Shorts", "#DOLIDENews", "#test"],
        youtube_tags=["DOLIDE News", "Shorts", "test upload"],
        platform_captions={
            "tiktok": "Private DOLIDE News upload test #DOLIDENews #test",
            "youtube": "Private upload test for DOLIDE News automation. #Shorts",
        },
        contains_synthetic_media=True,
    )


def run_upload_test(
    video_path: str,
    platform: str = "tiktok",
    request_id: str | None = None,
) -> dict:
    platform = (platform or "tiktok").lower()
    if platform not in TEST_UPLOAD_PLATFORMS:
        raise ValueError(f"Unsupported upload test platform: {platform}")

    request_id = request_id or utils.get_uuid()
    metadata = build_test_upload_metadata()
    results = {}

    if platform in ("tiktok", "both"):
        logger.info(f"Testing TikTok upload for {request_id}")
        tiktok_result = social_publisher.get_publisher("tiktok").publish(
            video_path=video_path,
            metadata=metadata,
            privacy=PublishPrivacy.private,
        )
        results["tiktok"] = tiktok_result.to_dict()
        if not tiktok_result.success:
            logger.error(f"TikTok test upload failed: {tiktok_result.error}")

    if platform in ("youtube", "both"):
        logger.info(f"Testing YouTube upload for {request_id}")
        youtube_result = social_publisher.get_publisher("youtube").publish(
            video_path=video_path,
            metadata=metadata,
            privacy=PublishPrivacy.private,
        )
        results["youtube"] = youtube_result.to_dict()
        if not youtube_result.success:
            logger.error(f"YouTube test upload failed: {youtube_result.error}")

    return {
        "request_id": request_id,
        "platforms_tested": platform if platform != "both" else ["tiktok", "youtube"],
        "results": results,
    }
