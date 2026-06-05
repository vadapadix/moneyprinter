import json
import re
from typing import Iterable

from loguru import logger

from app.models.schema import SocialMetadata
from app.services import llm


def _normalize_hashtag(value: str) -> str:
    tag = re.sub(r"[^0-9A-Za-z_]", "", value.strip().lstrip("#"))
    return f"#{tag}" if tag else ""


def _unique_strings(values: Iterable[str], limit: int) -> list[str]:
    seen = set()
    results = []
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            results.append(cleaned)
        if len(results) >= limit:
            break
    return results


def _usable_title(value: str) -> bool:
    normalized = re.sub(r"[^0-9a-z]+", " ", (value or "").strip().lower()).strip()
    if not normalized:
        return False
    bad_titles = {
        "unknown",
        "untitled",
        "n a",
        "na",
        "none",
        "generated short video",
    }
    return normalized not in bad_titles


def _select_title(title: str, default_title: str = "") -> str:
    if _usable_title(title):
        return title.strip()
    if _usable_title(default_title):
        return default_title.strip()
    return "Generated short video"


def _source_title(source_context: dict | None) -> str:
    if not isinstance(source_context, dict):
        return ""
    return str(source_context.get("title") or "").strip()


def _source_summary(source_context: dict | None) -> str:
    if not isinstance(source_context, dict):
        return ""
    return str(source_context.get("summary") or "").strip()


def _source_url(source_context: dict | None) -> str:
    if not isinstance(source_context, dict):
        return ""
    return str(source_context.get("source_url") or "").strip()


def _source_keywords(source_context: dict | None) -> list[str]:
    if not isinstance(source_context, dict):
        return []
    return [
        str(keyword).strip()
        for keyword in source_context.get("keywords") or []
        if str(keyword).strip()
    ]


def _plain_tags_from_title(title: str, limit: int = 6) -> list[str]:
    return [
        token.title()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", title or "")
        if token.lower() not in {"the", "and", "for", "with", "from", "this", "that"}
    ][:limit]


def normalize_metadata(metadata: SocialMetadata, default_title: str = "") -> SocialMetadata:
    title = _select_title(metadata.title, default_title)
    if len(title) > 95:
        title = title[:92].rstrip() + "..."

    description = (metadata.description or title).strip()
    hashtags = [
        tag for tag in (_normalize_hashtag(value) for value in metadata.hashtags) if tag
    ]
    hashtags = ["#Shorts" if tag.lower() == "#shorts" else tag for tag in hashtags]
    hashtags = _unique_strings([*hashtags, "#Shorts"], 12)

    if "#shorts" not in {tag.lower() for tag in hashtags}:
        hashtags.append("#Shorts")

    if "#shorts" not in title.lower() and "#shorts" not in description.lower():
        description = f"{description}\n\n#Shorts"

    youtube_tags = [
        tag.strip().lstrip("#") for tag in metadata.youtube_tags if isinstance(tag, str)
    ]
    youtube_tags = _unique_strings(youtube_tags, 15)

    platform_captions = {}
    for platform, caption in (metadata.platform_captions or {}).items():
        if isinstance(platform, str) and isinstance(caption, str):
            platform_captions[platform.lower()] = caption.strip()

    return SocialMetadata(
        title=title,
        description=description,
        hashtags=hashtags,
        youtube_tags=youtube_tags,
        category_id=metadata.category_id or "22",
        contains_synthetic_media=bool(metadata.contains_synthetic_media),
        platform_captions=platform_captions,
    )


def fallback_metadata(
    video_subject: str, video_terms=None, default_title: str = ""
) -> SocialMetadata:
    terms = video_terms or []
    if isinstance(terms, str):
        terms = re.split(r"[,，]", terms)

    hashtags = [_normalize_hashtag(term) for term in terms]
    metadata = SocialMetadata(
        title=default_title or video_subject or "Generated short video",
        description=default_title or video_subject or "Generated short video",
        hashtags=[tag for tag in hashtags if tag],
        youtube_tags=[str(term).strip() for term in terms if str(term).strip()],
    )
    return normalize_metadata(metadata, default_title=default_title or video_subject)


def fallback_metadata_from_context(
    video_subject: str,
    video_terms=None,
    default_title: str = "",
    source_context: dict | None = None,
) -> SocialMetadata:
    terms = video_terms or []
    if isinstance(terms, str):
        terms = re.split(r"[,пјЊ]", terms)

    title = _select_title(default_title, _source_title(source_context) or video_subject)
    summary = _source_summary(source_context)
    source_url = _source_url(source_context)
    keywords = _source_keywords(source_context)
    clean_terms = [str(term).strip() for term in terms if str(term).strip()]
    tag_terms = _unique_strings(
        [*clean_terms, *keywords, *_plain_tags_from_title(title), "News", "Shorts"],
        15,
    )
    hashtags = [_normalize_hashtag(term) for term in tag_terms]
    description_parts = [summary or title]
    if source_url:
        description_parts.append(f"Source: {source_url}")
    description = "\n\n".join(part for part in description_parts if part)

    metadata = SocialMetadata(
        title=title,
        description=description,
        hashtags=[tag for tag in hashtags if tag],
        youtube_tags=[tag.lstrip("#") for tag in tag_terms],
        platform_captions={
            "tiktok": " ".join(
                [
                    title,
                    *[
                        tag
                        for tag in hashtags
                        if tag and tag.lower() not in {"#shorts"}
                    ][:6],
                ]
            ).strip(),
            "youtube": description,
        },
    )
    return normalize_metadata(metadata, default_title=title)


def _extract_json_object(response: str) -> dict:
    try:
        return json.loads(response)
    except Exception:
        match = re.search(r"\{.*\}", response or "", re.DOTALL)
        if not match:
            raise
        return json.loads(match.group())


def generate_social_metadata(
    video_subject: str,
    video_script: str = "",
    video_terms=None,
    trend_context: dict | None = None,
    platforms: list[str] | None = None,
    language: str = "",
    source_context: dict | None = None,
    default_title: str = "",
) -> SocialMetadata:
    platforms = platforms or ["youtube", "tiktok"]
    prompt = f"""
# Role: Social short-video metadata generator

Return only a JSON object with these keys:
title, description, hashtags, youtube_tags, category_id, contains_synthetic_media, platform_captions.

Rules:
1. title must be concise and clickable, max 95 characters.
2. description must be suitable for YouTube Shorts and TikTok.
3. hashtags must be a JSON array of hashtag strings.
4. youtube_tags must be a JSON array without # characters.
5. platform_captions must be an object keyed by platform name.
6. Include #Shorts in either title, description, or hashtags for YouTube.
7. Do not include markdown.
8. If source_context contains source_url, include a short attribution line in description.
9. For TikTok, platform_captions.tiktok must be a ready-to-post caption with 3-8 hashtags.
10. For YouTube, description must include a short summary, hashtags, and source attribution when available.

Context:
subject: {video_subject}
language: {language}
platforms: {platforms}
stock_video_terms: {video_terms}
trend_context: {trend_context or {}}
source_context: {source_context or {}}
script: {video_script}
""".strip()

    response = llm._generate_response(prompt)
    if not response or "Error: " in response:
        logger.warning(f"failed to generate social metadata, using fallback: {response}")
        return fallback_metadata_from_context(
            video_subject,
            video_terms,
            default_title=default_title,
            source_context=source_context,
        )

    try:
        payload = _extract_json_object(response)
        if "category_id" in payload and payload["category_id"] is not None:
            payload["category_id"] = str(payload["category_id"])
        metadata = SocialMetadata(**payload)
        return normalize_metadata(metadata, default_title=default_title or video_subject)
    except Exception as exc:
        logger.warning(f"invalid social metadata response, using fallback: {str(exc)}")
        return fallback_metadata_from_context(
            video_subject,
            video_terms,
            default_title=default_title,
            source_context=source_context,
        )
