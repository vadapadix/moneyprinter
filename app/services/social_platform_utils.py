from app.models.schema import SocialPlatform


def platform_value(platform: SocialPlatform | str) -> str:
    if isinstance(platform, SocialPlatform):
        return platform.value
    return str(platform).strip().lower()


def platform_values(platforms: list[SocialPlatform | str] | None) -> list[str]:
    return [value for value in (platform_value(platform) for platform in platforms or []) if value]
