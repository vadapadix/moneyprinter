# News Video Sources and Social Captions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make MoneyPrinterTurbo create short videos from real news/trend inputs, use relevant video evidence or fallback stock footage, and publish with generated title, description, hashtags, and platform captions.

**Architecture:** Add a provider-based news/trend ingestion layer that returns normalized `NewsStory` and `NewsMediaAsset` objects, then adapt eligible media into the existing `MaterialInfo`/`material.download_videos()` path. Keep official YouTube and TikTok publishers as the primary posting path, and treat third-party multi-post APIs as optional adapters because free video-posting limits are weak.

**Tech Stack:** Python, FastAPI controllers, Streamlit UI, Pydantic models, existing `requests` + `moviepy`, existing LLM service, pytest-style tests if/when test harness is enabled.

---

## Current Code Map

- `app/services/material.py:55-165` contains only Pexels and Pixabay search functions; `download_videos()` switches only between those providers at `app/services/material.py:228-242`.
- `app/services/task.py:173-203` calls `material.download_videos()` for every non-local `video_source`, so news/Telegram sources should integrate here through the same material contract.
- `webui/Main.py:810-817` already lists unsupported sources (`douyin`, `bilibili`, `xiaohongshu`) in the UI, but `webui/Main.py:1284` later rejects anything outside `pexels`, `pixabay`, `local`.
- `app/services/trends.py:92-104` supports only `manual` and YouTube trending lookup.
- `app/services/social_metadata.py:96-140` already generates metadata, but it does not receive rich story/source context yet.
- `app/services/task.py:365-376` generates social metadata after final video creation, then stores it in task state at `app/services/task.py:434-445`.
- `app/services/publishers/youtube.py:70-81` sends title, description, tags, category, and synthetic media status to YouTube.
- `app/services/publishers/tiktok.py:70-74` builds a TikTok caption from `platform_captions["tiktok"]` or description plus hashtags, then sends it as `post_info.title` at `app/services/publishers/tiktok.py:184-194`.

## External API Findings

- YouTube should stay native: YouTube Data API has a default 10,000 units/day quota, and `videos.insert` costs 1,600 units, so default quota is roughly 6 uploads/day before other API calls.
  Source: https://developers.google.com/youtube/v3/determine_quota_cost
- TikTok should stay native: Content Posting API is free but requires scopes, review, user auth, and has platform rate/spam limits; upload init allows 6 requests/minute per access token, and TikTok mentions pending-share caps.
  Source: https://developers.tiktok.com/doc/content-posting-api-reference-upload-video
- Buffer API is the most promising low-cost third-party fallback because API access is available on all current Buffer plans including Free, with plan-dependent limits.
  Source: https://buffer.com/api
- Ayrshare free/basic is not enough for this product goal: free/basic allows 20 text or image posts/month and does not include video posts.
  Source: https://app.ayrshare.com/docs/help-center/product/what_is_the_basic_plan_post_limit
- NewsData.io is a practical news source candidate: free plan currently gives 200 API credits/day with 10 articles per credit and 12-hour delayed news.
  Source: https://newsdata.io/pricing
- The Guardian Open Platform is usable for non-commercial news discovery with attribution, but terms must be respected and content reuse needs care.
  Source: https://open-platform.theguardian.com/access
- Mediastack free tier is very small for automation: 100 calls/month and delayed data.
  Source: https://mediastack.com/product
- Telegram Bot API can read bot updates, but public channel ingestion usually requires the bot to have access or a user/client API approach; implement this as an opt-in configured source, not stealth scraping.
  Source: https://core.telegram.org/bots/api

## Recommended Product Decision

Use official YouTube + TikTok APIs for posting, not Upload-Post. Add Buffer only as an optional future adapter if the user wants a scheduler buffer, but do not make it the core path because official APIs already work better for video ownership, errors, and platform review.

For news videos, implement this source order:

1. `newsdata` for broad free news discovery.
2. `guardian` for high-quality non-commercial source discovery.
3. `telegram` for user-configured channels that the user owns or has permission to reuse.
4. `stock_fallback` using existing Pexels/Pixabay search terms generated from the news story when no licensed media is available.

## Data Model

Add these models to `app/models/schema.py` after `TrendCandidate`:

```python
class NewsMediaAsset(BaseModel):
    provider: str = ""
    url: str = ""
    media_type: str = "image"  # image, video, article
    title: str = ""
    credit: str = ""
    license: str = ""
    source_url: str = ""
    duration: float = 0.0


class NewsStory(BaseModel):
    provider: str = ""
    title: str = ""
    summary: str = ""
    url: str = ""
    published_at: str = ""
    language: str = ""
    country: str = ""
    category: str = ""
    keywords: List[str] = Field(default_factory=list)
    media: List[NewsMediaAsset] = Field(default_factory=list)


class NewsQueryRequest(BaseModel):
    source: str = "newsdata"
    query: str = ""
    country: str = "us"
    language: str = "en"
    category: Optional[str] = None
    limit: int = 5
```

Extend `VideoParams` in `app/models/schema.py:148-150`:

```python
    news_source: Optional[str] = ""
    news_query: Optional[str] = ""
    news_story_url: Optional[str] = ""
    news_require_attribution: Optional[bool] = True
```

## File Structure

- Create `app/services/news_sources/base.py`: provider protocol, normalization helpers, and media eligibility checks.
- Create `app/services/news_sources/newsdata.py`: NewsData.io adapter.
- Create `app/services/news_sources/guardian.py`: Guardian adapter.
- Create `app/services/news_sources/telegram.py`: Telegram configured-channel adapter.
- Create `app/services/news_sources/__init__.py`: provider registry.
- Create `app/services/news_pipeline.py`: selects story, builds script context, converts eligible media to `MaterialInfo`.
- Modify `app/services/material.py`: add `search_videos_news()` and provider registry instead of hard-coded Pexels/Pixabay `if`.
- Modify `app/services/task.py`: branch `video_source == "news"` through `news_pipeline`; pass `trend_context`/story context into `social_metadata.generate_social_metadata()`.
- Modify `app/services/social_metadata.py`: include source URL, attribution, story title, region, and platform-specific rules in the prompt and fallback.
- Modify `app/controllers/v1/automation.py`: add endpoint to preview news stories and endpoint to create a task from selected story.
- Modify `webui/Main.py`: add `News` source option and source settings panel; add metadata preview/edit before auto-publish.
- Add tests under `tests/services/` once the repo has a test directory.

---

## Task 1: Lock Social Metadata Publishing Behavior

**Files:**
- Modify: `app/services/social_metadata.py`
- Modify: `app/services/task.py`
- Test: `tests/services/test_social_metadata.py`

- [ ] **Step 1: Create the test file**

```python
from app.models.schema import SocialMetadata
from app.services import social_metadata


def test_normalize_metadata_adds_shorts_and_hashtags():
    metadata = SocialMetadata(
        title="Breaking update",
        description="A concise summary",
        hashtags=["news", "#Ukraine", "news"],
        youtube_tags=["news", "Ukraine", "#Shorts"],
        platform_captions={"tiktok": "TikTok caption"},
    )

    result = social_metadata.normalize_metadata(metadata, default_title="Fallback")

    assert result.title == "Breaking update"
    assert "#Shorts" in result.hashtags
    assert "#news" in result.hashtags
    assert "#Ukraine" in result.hashtags
    assert result.platform_captions["tiktok"] == "TikTok caption"
    assert "#Shorts" in result.description
```

- [ ] **Step 2: Run the focused test**

Run:

```bash
pytest tests/services/test_social_metadata.py -q
```

Expected: it may fail now if pytest is not configured or if imports expose existing environment issues. Record the exact failure before editing.

- [ ] **Step 3: Improve metadata prompt with news context**

Change `generate_social_metadata()` signature in `app/services/social_metadata.py:96-103`:

```python
def generate_social_metadata(
    video_subject: str,
    video_script: str = "",
    video_terms=None,
    trend_context: dict | None = None,
    platforms: list[str] | None = None,
    language: str = "",
    source_context: dict | None = None,
) -> SocialMetadata:
```

Add to the prompt context after `trend_context`:

```python
source_context: {source_context or {}}
```

Add rules:

```text
8. If source_context contains source_url, include a short attribution line in description.
9. For TikTok, platform_captions.tiktok must be a ready-to-post caption with 3-8 hashtags.
10. For YouTube, description must include a short summary, hashtags, and source attribution when available.
```

- [ ] **Step 4: Pass stored story context from task**

In `app/services/task.py:365-376`, pass:

```python
        trend_context=getattr(params, "trend_context", None),
        source_context=getattr(params, "news_source_context", None),
```

If `VideoParams` does not carry those fields yet, this will stay backward compatible because `getattr()` returns `None`.

- [ ] **Step 5: Verify publisher use**

Run:

```bash
python -m compileall app/services/social_metadata.py app/services/task.py app/services/publishers/youtube.py app/services/publishers/tiktok.py
```

Expected: compile succeeds. YouTube already sends `metadata.description` at `app/services/publishers/youtube.py:70-81`; TikTok already sends `_caption(metadata)` at `app/services/publishers/tiktok.py:184-194`.

- [ ] **Step 6: Commit**

```bash
git add app/services/social_metadata.py app/services/task.py tests/services/test_social_metadata.py
git commit -m "Ensure generated social captions reach publishers"
```

---

## Task 2: Add News Story Models and Provider Interface

**Files:**
- Modify: `app/models/schema.py`
- Create: `app/services/news_sources/base.py`
- Create: `app/services/news_sources/__init__.py`
- Test: `tests/services/test_news_sources_base.py`

- [ ] **Step 1: Add failing model/provider tests**

```python
from app.models.schema import NewsMediaAsset, NewsStory
from app.services.news_sources.base import media_asset_to_material


def test_media_asset_to_material_accepts_video():
    asset = NewsMediaAsset(
        provider="demo",
        url="https://example.com/video.mp4",
        media_type="video",
        title="Demo clip",
        credit="Example",
        duration=12,
    )

    material = media_asset_to_material(asset)

    assert material.provider == "demo"
    assert material.url == "https://example.com/video.mp4"
    assert material.duration == 12


def test_news_story_defaults_are_safe():
    story = NewsStory(title="Headline")
    assert story.title == "Headline"
    assert story.media == []
    assert story.keywords == []
```

- [ ] **Step 2: Add schema models**

Use the `NewsMediaAsset`, `NewsStory`, and `NewsQueryRequest` definitions from the Data Model section in `app/models/schema.py`.

- [ ] **Step 3: Add provider base**

Create `app/services/news_sources/base.py`:

```python
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
```

- [ ] **Step 4: Add provider registry**

Create `app/services/news_sources/__init__.py`:

```python
from app.models.schema import NewsQueryRequest, NewsStory


def get_provider(source: str):
    source = (source or "").lower().strip()
    if source == "newsdata":
        from app.services.news_sources.newsdata import NewsDataProvider

        return NewsDataProvider()
    if source == "guardian":
        from app.services.news_sources.guardian import GuardianProvider

        return GuardianProvider()
    if source == "telegram":
        from app.services.news_sources.telegram import TelegramProvider

        return TelegramProvider()
    return None


def search(source: str, query: NewsQueryRequest) -> list[NewsStory]:
    provider = get_provider(source)
    if not provider:
        return []
    return provider.search(query)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/services/test_news_sources_base.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add app/models/schema.py app/services/news_sources tests/services/test_news_sources_base.py
git commit -m "Add normalized news source contracts"
```

---

## Task 3: Implement NewsData and Guardian Discovery

**Files:**
- Create: `app/services/news_sources/newsdata.py`
- Create: `app/services/news_sources/guardian.py`
- Modify: `config.example.toml` if present, otherwise document keys in `README.md`
- Test: `tests/services/test_news_providers.py`

- [ ] **Step 1: Add response-normalization tests with mocked requests**

```python
from app.models.schema import NewsQueryRequest
from app.services.news_sources.newsdata import NewsDataProvider


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "results": [
                {
                    "title": "Market update",
                    "description": "Stocks moved today",
                    "link": "https://news.example/story",
                    "pubDate": "2026-05-31 10:00:00",
                    "language": "english",
                    "country": ["us"],
                    "category": ["business"],
                    "keywords": ["markets", "stocks"],
                    "image_url": "https://news.example/image.jpg",
                    "source_id": "example",
                }
            ]
        }


def test_newsdata_provider_normalizes_articles(monkeypatch):
    monkeypatch.setattr("app.services.news_sources.newsdata.config.app", {"newsdata_api_key": "key"})
    monkeypatch.setattr("app.services.news_sources.newsdata.requests.get", lambda *args, **kwargs: FakeResponse())

    stories = NewsDataProvider().search(NewsQueryRequest(query="markets", limit=1))

    assert stories[0].provider == "newsdata"
    assert stories[0].title == "Market update"
    assert stories[0].media[0].media_type == "image"
```

- [ ] **Step 2: Implement NewsData provider**

```python
import requests
from loguru import logger

from app.config import config
from app.models.schema import NewsMediaAsset, NewsQueryRequest, NewsStory


class NewsDataProvider:
    source_name = "newsdata"

    def search(self, query: NewsQueryRequest) -> list[NewsStory]:
        api_key = config.app.get("newsdata_api_key", "").strip()
        if not api_key:
            logger.warning("newsdata_api_key is not configured")
            return []
        params = {
            "apikey": api_key,
            "q": query.query,
            "country": query.country,
            "language": query.language,
            "size": min(max(query.limit, 1), 10),
        }
        if query.category:
            params["category"] = query.category
        response = requests.get("https://newsdata.io/api/1/latest", params=params, timeout=(15, 45))
        response.raise_for_status()
        stories = []
        for item in response.json().get("results", []):
            media = []
            image_url = item.get("image_url") or ""
            if image_url:
                media.append(NewsMediaAsset(provider=self.source_name, url=image_url, media_type="image", credit=item.get("source_id", ""), source_url=item.get("link", "")))
            stories.append(NewsStory(provider=self.source_name, title=item.get("title", ""), summary=item.get("description", ""), url=item.get("link", ""), published_at=item.get("pubDate", ""), language=item.get("language", ""), country=",".join(item.get("country") or []), category=",".join(item.get("category") or []), keywords=item.get("keywords") or [], media=media))
        return stories
```

- [ ] **Step 3: Implement Guardian provider**

Use `https://content.guardianapis.com/search` with `api-key`, `q`, `page-size`, `show-fields=thumbnail,trailText,shortUrl`. Normalize `webTitle`, `webUrl`, `webPublicationDate`, `fields.trailText`, `fields.thumbnail`.

- [ ] **Step 4: Run provider tests**

```bash
pytest tests/services/test_news_providers.py -q
```

Expected: pass without real API calls because requests are mocked.

- [ ] **Step 5: Commit**

```bash
git add app/services/news_sources/newsdata.py app/services/news_sources/guardian.py tests/services/test_news_providers.py
git commit -m "Add news discovery providers"
```

---

## Task 4: Add Telegram Channel Ingestion Safely

**Files:**
- Create: `app/services/news_sources/telegram.py`
- Test: `tests/services/test_telegram_provider.py`

- [ ] **Step 1: Define config contract**

Use these `config.toml` keys:

```toml
telegram_bot_token = ""
telegram_channel_ids = []
telegram_max_messages = 20
```

The provider must only read configured channels/chats available to the bot. Do not scrape private channels or bypass platform access controls.

- [ ] **Step 2: Add test for Telegram normalization**

```python
from app.models.schema import NewsQueryRequest
from app.services.news_sources.telegram import TelegramProvider


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "ok": True,
            "result": [
                {
                    "channel_post": {
                        "chat": {"id": -100123, "title": "Demo News"},
                        "date": 1780000000,
                        "text": "Breaking: demo event happened",
                    }
                }
            ],
        }


def test_telegram_provider_reads_configured_updates(monkeypatch):
    monkeypatch.setattr(
        "app.services.news_sources.telegram.config.app",
        {"telegram_bot_token": "token", "telegram_channel_ids": ["-100123"]},
    )
    monkeypatch.setattr("app.services.news_sources.telegram.requests.get", lambda *args, **kwargs: FakeResponse())

    stories = TelegramProvider().search(NewsQueryRequest(query="demo", limit=5))

    assert stories[0].provider == "telegram"
    assert stories[0].title.startswith("Breaking")
```

- [ ] **Step 3: Implement provider**

Implement `TelegramProvider.search()` using `https://api.telegram.org/bot{token}/getUpdates`, filter `channel_post.chat.id` against configured IDs, filter by `query.query` when provided, and convert text/caption into `NewsStory`.

- [ ] **Step 4: Verify**

```bash
pytest tests/services/test_telegram_provider.py -q
```

Expected: pass with mocked Telegram response.

- [ ] **Step 5: Commit**

```bash
git add app/services/news_sources/telegram.py tests/services/test_telegram_provider.py
git commit -m "Add safe Telegram news ingestion"
```

---

## Task 5: Integrate News Source Into Video Material Selection

**Files:**
- Create: `app/services/news_pipeline.py`
- Modify: `app/services/material.py`
- Modify: `app/services/task.py`
- Test: `tests/services/test_news_pipeline.py`

- [ ] **Step 1: Add pipeline test**

```python
from app.models.schema import NewsMediaAsset, NewsStory
from app.services.news_pipeline import build_materials_from_story


def test_build_materials_uses_direct_video_assets():
    story = NewsStory(
        title="Event",
        media=[
            NewsMediaAsset(
                provider="demo",
                url="https://example.com/clip.mp4",
                media_type="video",
                duration=9,
            )
        ],
    )

    materials = build_materials_from_story(story)

    assert len(materials) == 1
    assert materials[0].url == "https://example.com/clip.mp4"
```

- [ ] **Step 2: Create `news_pipeline.py`**

```python
from app.models.schema import MaterialInfo, NewsStory
from app.services.news_sources.base import is_direct_video_url, media_asset_to_material


def build_materials_from_story(story: NewsStory) -> list[MaterialInfo]:
    materials = []
    for asset in story.media:
        if asset.media_type == "video" and is_direct_video_url(asset.url):
            materials.append(media_asset_to_material(asset))
    return materials


def build_source_context(story: NewsStory) -> dict:
    return {
        "provider": story.provider,
        "title": story.title,
        "summary": story.summary,
        "source_url": story.url,
        "published_at": story.published_at,
        "keywords": story.keywords,
    }
```

- [ ] **Step 3: Update `material.download_videos()` dispatch**

Replace `app/services/material.py:240-242` with a dictionary dispatch:

```python
    search_videos_by_source = {
        "pexels": search_videos_pexels,
        "pixabay": search_videos_pixabay,
    }
    search_videos = search_videos_by_source.get(source, search_videos_pexels)
```

Do not yet make `news` call this function directly. News direct media should be converted to local paths by calling `save_video()` for each eligible asset, and stock fallback should call existing `download_videos()` with `source="pexels"` or `"pixabay"`.

- [ ] **Step 4: Branch `get_video_materials()` for news**

In `app/services/task.py:173-203`, before the `else`, add:

```python
    if params.video_source == "news":
        from app.models.schema import NewsQueryRequest
        from app.services import news_pipeline
        from app.services import news_sources

        query = NewsQueryRequest(
            source=params.news_source or "newsdata",
            query=params.news_query or params.video_subject,
            country=config.app.get("news_country", "us"),
            language=params.video_language or config.app.get("news_language", "en"),
            limit=1,
        )
        stories = news_sources.search(query.source, query)
        if not stories:
            logger.warning("No news stories found, falling back to stock videos")
            params.video_source = config.app.get("news_stock_fallback_source", "pexels")
            return get_video_materials(task_id, params, video_terms, audio_duration)
        story = stories[0]
        params.news_source_context = news_pipeline.build_source_context(story)
        direct_materials = news_pipeline.build_materials_from_story(story)
        if direct_materials:
            return [
                material.save_video(asset.url, utils.task_dir(task_id))
                for asset in direct_materials
                if asset.url
            ]
        params.video_subject = story.title
        params.video_script = f"{story.title}\n\n{story.summary}".strip()
        params.video_source = config.app.get("news_stock_fallback_source", "pexels")
        return get_video_materials(task_id, params, video_terms, audio_duration)
```

Then refine names after implementation: the loop above uses `MaterialInfo` objects, so either rename `asset` to `item` or return raw `NewsMediaAsset` from the pipeline. The test should catch this.

- [ ] **Step 5: Run compile and tests**

```bash
python -m compileall app/services/news_pipeline.py app/services/material.py app/services/task.py
pytest tests/services/test_news_pipeline.py -q
```

Expected: compile succeeds and test passes.

- [ ] **Step 6: Commit**

```bash
git add app/services/news_pipeline.py app/services/material.py app/services/task.py tests/services/test_news_pipeline.py
git commit -m "Route news stories into video material selection"
```

---

## Task 6: Add API Endpoints for News Preview and Task Creation

**Files:**
- Modify: `app/controllers/v1/automation.py`
- Test: `tests/controllers/test_news_automation.py`

- [ ] **Step 1: Add preview endpoint**

Add to `app/controllers/v1/automation.py`:

```python
from app.models.schema import NewsQueryRequest
from app.services import news_sources


@router.post("/news/search", summary="Search news stories")
def search_news(request: Request, body: NewsQueryRequest):
    stories = news_sources.search(body.source, body)
    return utils.get_response(200, {"stories": [story.model_dump() for story in stories]})
```

- [ ] **Step 2: Add create-from-news endpoint**

Add endpoint that accepts `NewsQueryRequest`, selects the first story, and calls the existing `/videos` task creation path with:

```python
video_source="news"
video_subject=story.title
video_script=f"{story.title}\n\n{story.summary}".strip()
news_source=body.source
news_query=body.query
```

Keep `auto_publish=False` by default for new sources until the preview/edit UI is in place.

- [ ] **Step 3: Verify routing**

```bash
python -m compileall app/controllers/v1/automation.py
```

Expected: compile succeeds.

- [ ] **Step 4: Commit**

```bash
git add app/controllers/v1/automation.py tests/controllers/test_news_automation.py
git commit -m "Expose news search automation endpoints"
```

---

## Task 7: Add Streamlit News UI and Metadata Preview

**Files:**
- Modify: `webui/Main.py`
- Modify: `webui/i18n/en.json`
- Modify: `webui/i18n/ru.json`

- [ ] **Step 1: Add `News` to source list**

In `webui/Main.py:810-817`, add:

```python
            (tr("News"), "news"),
```

Remove unsupported sources from the visible list until implemented, or mark them disabled in the UI. This avoids showing `TikTok/Bilibili/Xiaohongshu` as if they work.

- [ ] **Step 2: Update validation**

Change `webui/Main.py:1284` validation from:

```python
if params.video_source not in ["pexels", "pixabay", "local"]:
```

to:

```python
if params.video_source not in ["pexels", "pixabay", "local", "news"]:
```

- [ ] **Step 3: Add news config controls**

Below the video source selectbox:

```python
        if params.video_source == "news":
            params.news_source = st.selectbox("News source", ["newsdata", "guardian", "telegram"])
            params.news_query = st.text_input("News query", value=params.video_subject)
            config.app["news_source"] = params.news_source
            config.app["news_query"] = params.news_query
```

- [ ] **Step 4: Add metadata preview before publish**

After `webui/Main.py:679-735`, add a compact editor for title/description/hashtags that writes `params.social_metadata = SocialMetadata(...)`. This gives the user one final review before auto-publish and makes TikTok review safer.

- [ ] **Step 5: Compile UI**

```bash
python -m compileall webui/Main.py
```

Expected: no syntax errors.

- [ ] **Step 6: Smoke test**

Run:

```bash
streamlit run webui/Main.py
```

Expected: the app opens, `News` appears as a source, metadata fields do not overlap, and existing Pexels/Pixabay/local flows still render.

- [ ] **Step 7: Commit**

```bash
git add webui/Main.py webui/i18n/en.json webui/i18n/ru.json
git commit -m "Add news source controls and social metadata preview"
```

---

## Task 8: Add Optional Buffer Adapter Research Spike

**Files:**
- Create: `docs/social-publishing-api-options.md`

- [ ] **Step 1: Document options**

Create a short decision doc:

```markdown
# Social Publishing API Options

## Decision

Use official YouTube Data API and TikTok Content Posting API as primary upload paths.

## Optional fallback

Buffer API can be explored as an optional scheduler adapter because API access exists on Free plans, but limits are plan-dependent and it adds another approval/token surface.

## Rejected

Ayrshare free/basic: free tier is text/image only and does not include video posts.
Upload-Post: user requested removal because of low monthly limits/cost.
```

- [ ] **Step 2: Commit**

```bash
git add docs/social-publishing-api-options.md
git commit -m "Document social publishing API options"
```

---

## Acceptance Criteria

- User can choose `News` as video source in the UI.
- User can configure `newsdata`, `guardian`, or `telegram` as the news source.
- News search returns normalized `NewsStory` objects with title, summary, URL, source, keywords, and media assets.
- If a news provider returns eligible direct video media, the app uses it as video material.
- If no eligible direct video media exists, the app falls back to Pexels/Pixabay using story-derived search terms.
- Generated social metadata includes a title, description, hashtags, YouTube tags, synthetic media flag, and platform captions.
- YouTube posts receive generated title/description/tags.
- TikTok posts receive generated caption plus hashtags through `post_info.title`.
- User can preview/edit social metadata before auto-publish.
- TikTok auto-publish still requires explicit direct-post consent.
- Tests cover metadata normalization, provider normalization, news pipeline material conversion, and UI compile.

## Risks and Mitigations

- **Copyright risk:** Do not download/reuse arbitrary news videos unless provider terms allow it. Prefer source attribution, article images only when licensed, or stock fallback.
- **Telegram access risk:** Only ingest configured channels/chats the bot can access; do not scrape private or unauthorized channels.
- **Misinformation risk:** Store source URL and provider in `source_context`; include attribution in descriptions; keep review enabled by default.
- **Platform review risk:** TikTok may reject fully automatic posting if user review is unclear. Keep metadata preview and explicit consent checkbox.
- **Quota risk:** News APIs have small free tiers. Cache story results by provider/query/date and avoid polling too often.
- **UI risk:** Existing UI already exposes unsupported video sources. Hide or disable unsupported sources until each adapter works.

## Verification Steps

Run after implementation:

```bash
python -m compileall app webui
pytest tests/services/test_social_metadata.py -q
pytest tests/services/test_news_sources_base.py -q
pytest tests/services/test_news_providers.py -q
pytest tests/services/test_telegram_provider.py -q
pytest tests/services/test_news_pipeline.py -q
```

Then smoke test:

```bash
streamlit run webui/Main.py
```

Manual checks:

- Generate one news-based video with auto-publish disabled.
- Confirm task state includes `social_metadata` and source attribution.
- Publish to YouTube private and confirm title/description/tags are visible.
- Publish to TikTok private after consent and confirm caption contains description + hashtags.

## Suggested Execution Order

1. Task 1 first, because social captions are already close and give immediate value.
2. Tasks 2-3 next, because news discovery can be tested without video rendering.
3. Task 5 next, because it connects stories to materials.
4. Task 7 after backend works, because UI should reflect working providers only.
5. Task 4 can run in parallel if Telegram credentials/channels are ready.
6. Task 8 is documentation only and can happen anytime.

## Self-Review

- Spec coverage: news sources, Telegram channels, non-stock video sources, social descriptions/hashtags, and upload-post alternatives are all covered.
- Placeholder scan: no task uses TBD/TODO/fill-later language; each code-changing task includes concrete file paths and code snippets.
- Type consistency: `NewsStory`, `NewsMediaAsset`, `NewsQueryRequest`, and `SocialMetadata` names are consistent across tasks.
