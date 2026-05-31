from __future__ import annotations

from typing import Protocol

from app.models.schema import MaterialInfo, NewsMediaAsset, NewsQueryRequest, NewsStory


class NewsSourceProvider(Protocol):
    source_name: str

    def search(self, query: NewsQueryRequest) -> list[NewsStory]:
        ...


def is_direct_video_url(url: str) -> bool:
    clean_url = (url or "").split("?", 1)[0].lower()
    return clean_url.endswith((".mp4", ".mov", ".m4v", ".webm"))


def media_asset_to_material(asset: NewsMediaAsset) -> MaterialInfo:
    material = MaterialInfo()
    material.provider = asset.provider
    material.url = asset.url
    material.duration = asset.duration or 10
    return material
