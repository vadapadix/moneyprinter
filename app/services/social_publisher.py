from app.config import config
from app.models.schema import PublishPrivacy, SocialMetadata
from app.services import state as sm
from app.services.publishers.base import PublishResult
from app.services.publishers.tiktok import TikTokPublisher
from app.services.publishers.youtube import YouTubeShortsPublisher


def _configured_platforms(platforms: list[str] | None = None) -> list[str]:
    if platforms:
        return [str(platform).lower() for platform in platforms]
    configured = config.app.get("social_platforms")
    if configured:
        return [str(platform).lower() for platform in configured]
    return []


def get_publisher(platform: str):
    platform = str(platform).lower()
    if platform == "youtube":
        return YouTubeShortsPublisher()
    if platform == "tiktok":
        return TikTokPublisher()
    return None


def publish_video(
    video_path: str,
    metadata: SocialMetadata,
    platforms: list[str] | None = None,
    privacy: PublishPrivacy = PublishPrivacy.private,
) -> list[dict]:
    privacy = privacy or PublishPrivacy.private
    results = []
    for platform in _configured_platforms(platforms):
        publisher = get_publisher(platform)
        if not publisher:
            results.append(
                PublishResult(
                    platform=platform,
                    success=False,
                    status="unsupported",
                    error=f"Unsupported platform: {platform}",
                ).to_dict()
            )
            continue

        results.append(publisher.publish(video_path, metadata, privacy).to_dict())
    return results


def publish_task_videos(
    task_id: str,
    video_paths: list[str],
    metadata: SocialMetadata,
    platforms: list[str] | None = None,
    privacy: PublishPrivacy = PublishPrivacy.private,
) -> list[dict]:
    privacy = privacy or PublishPrivacy.private
    publish_results = []
    for video_path in video_paths:
        for result in publish_video(video_path, metadata, platforms, privacy):
            result["video_path"] = video_path
            publish_results.append(result)

    current = sm.state.get_task(task_id) or {}
    current.pop("task_id", None)
    sm.state.update_task(
        task_id,
        **{
            **current,
            "social_metadata": metadata.model_dump(),
            "publish_results": publish_results,
        },
    )
    return publish_results


def publish_existing_task(
    task_id: str,
    metadata: SocialMetadata | None = None,
    platforms: list[str] | None = None,
    privacy: PublishPrivacy = PublishPrivacy.private,
) -> list[dict]:
    privacy = privacy or PublishPrivacy.private
    task = sm.state.get_task(task_id)
    if not task:
        return [
            PublishResult(
                platform="",
                success=False,
                status="failed",
                error=f"Task not found: {task_id}",
            ).to_dict()
        ]

    video_paths = task.get("videos") or []
    if metadata is None:
        existing = task.get("social_metadata") or {}
        metadata = SocialMetadata(**existing) if existing else SocialMetadata()
    return publish_task_videos(task_id, video_paths, metadata, platforms, privacy)
