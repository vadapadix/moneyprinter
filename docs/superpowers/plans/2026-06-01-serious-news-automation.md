# Serious News Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the app into an automated English-language news shorts pipeline that finds real stories, gathers relevant media, generates useful scripts and captions, posts to connected social platforms, and avoids repeating the same article.

**Architecture:** Keep the existing task generator as the execution core, but feed it with normalized news stories, enriched media assets, and a persistent story history ledger. Publishing remains on the official YouTube and TikTok integrations, with metadata generated from the source story and hardened by deterministic fallbacks.

**Tech Stack:** Python, Streamlit, FastAPI controllers, Pydantic models, MoviePy, existing LLM service, Telethon, NewsData, Guardian, direct web media discovery, `unittest` tests.

---

## File Structure

- Create `app/services/news_history.py`: persistent processed-story ledger stored under `storage/news/history.json`.
- Modify `app/services/automation.py`: request extra stories, skip previously used stories, reserve selected story keys, and build richer news params.
- Modify `webui/Main.py`: mark finished news tasks as completed/failed in the ledger when Streamlit runs automation inline.
- Modify `app/services/social_metadata.py`: reject unusable titles such as `unknown`, use story titles as deterministic defaults, and keep captions/tags populated.
- Modify `app/services/task.py`: pass source story title as the default social metadata title and keep auto-publish diagnostics visible.
- Modify `app/services/video.py`: add configurable `DOLIDE News` intro and watermark overlays to every generated short.
- Create `app/services/news_diagnostics.py`: append-only task diagnostics for story selection, media search, metadata, and publishing.
- Modify `config.example.toml`: document news history, web media, narration speed, and watermark settings.
- Test `tests/services/test_news_history.py`: story key, filtering, reserving, marking.
- Test `tests/controllers/test_news_automation.py`: automation skips repeated stories and keeps English/news defaults.
- Test `tests/services/test_social_metadata.py`: bad LLM title falls back to story title.
- Test `tests/services/test_news_diagnostics.py`: diagnostic events persist as JSON.

## Task 1: Persist Unique Story Selection

**Files:**
- Create: `app/services/news_history.py`
- Modify: `app/services/automation.py`
- Modify: `webui/Main.py`
- Test: `tests/services/test_news_history.py`
- Test: `tests/controllers/test_news_automation.py`

- [ ] **Step 1: Add a test for filtering repeated stories**

Run: `D:\moneyprinter\lib\python\python.exe -m unittest tests.services.test_news_history -v`
Expected before implementation: import failure for `app.services.news_history`.

- [ ] **Step 2: Implement `story_key`, `filter_new_stories`, `reserve_story`, and `mark_story_result`**

Use URL as the primary key, with a normalized provider/title hash fallback when the URL is missing.

- [ ] **Step 3: Wire `prepare_news_run()` to over-fetch and reserve selected stories**

Fetch `limit * news_story_fetch_multiplier` stories, filter already used items, and reserve only the stories placed into tasks.

- [ ] **Step 4: Mark task outcomes in Streamlit inline runs**

After each `tm.start()` call, update the ledger with success, task id, generated video paths, and publish result count.

## Task 2: Harden Social Publishing Metadata

**Files:**
- Modify: `app/services/social_metadata.py`
- Modify: `app/services/task.py`
- Test: `tests/services/test_social_metadata.py`

- [ ] **Step 1: Add a test where the LLM returns `unknown` title**

Expected behavior: final title uses the source story title, description still includes `#Shorts`, and captions remain populated.

- [ ] **Step 2: Add deterministic title sanitizing**

Reject empty titles and low-value titles such as `unknown`, `untitled`, `n/a`, and `generated short video` when a real default title exists.

- [ ] **Step 3: Pass the source story title from task publishing**

Use `params.news_source_context["title"]` as the metadata default title before falling back to the prompt subject.

## Task 3: Brand News Output

**Files:**
- Modify: `app/services/video.py`
- Modify: `config.example.toml`

- [ ] **Step 1: Add intro and watermark config keys**

Add `brand_intro_enabled`, `brand_intro_text`, `brand_intro_label`, `brand_intro_duration`, `brand_watermark_enabled`, `brand_watermark_text`, `brand_watermark_position`, `brand_watermark_font_size`, and `brand_watermark_opacity`.

- [ ] **Step 2: Composite the intro and watermark after subtitles**

Create a first-seconds news intro overlay and a small persistent `TextClip` for `DOLIDE News`; keep rendering non-fatal if either branding layer cannot be created.

## Task 4: Verify

**Files:**
- All changed files above.

- [ ] **Step 1: Compile changed Python files**

Run: `D:\moneyprinter\lib\python\python.exe -m compileall app\services\news_history.py app\services\automation.py app\services\social_metadata.py app\services\task.py app\services\video.py webui\Main.py tests\services\test_news_history.py tests\services\test_social_metadata.py tests\controllers\test_news_automation.py`
Expected: compile success.

- [ ] **Step 2: Run focused regression tests**

Run: `D:\moneyprinter\lib\python\python.exe -m unittest tests.services.test_news_history tests.services.test_social_metadata tests.controllers.test_news_automation tests.services.test_news_pipeline tests.services.test_web_media tests.services.test_task_terms -v`
Expected: all tests pass.

## Task 5: Add Pipeline Diagnostics

**Files:**
- Create: `app/services/news_diagnostics.py`
- Modify: `app/services/automation.py`
- Modify: `app/services/task.py`
- Modify: `webui/Main.py`
- Modify: `app/controllers/v1/automation.py`
- Test: `tests/services/test_news_diagnostics.py`

- [ ] **Step 1: Persist task events**

Write events to `storage/news/diagnostics/{task_id}.json` with `event`, `created_at`, and JSON-safe `properties`.

- [ ] **Step 2: Record article and media stages**

Record `news_story_reserved`, `news_ytdlp_search_started`, `news_ytdlp_search_completed`, `news_stock_fallback_started`, and `news_stock_fallback_completed`.

- [ ] **Step 3: Record publishing stages**

Record `social_metadata_ready`, `social_publish_skipped`, and `social_publish_completed` so failed uploads can be diagnosed without reading terminal logs.

- [ ] **Step 4: Expose diagnostics**

Return diagnostics in Streamlit inline automation payloads and `/tasks/{task_id}/publish`.

## Task 6: Sequential Publishing And Deeper Video Search

**Files:**
- Modify: `app/controllers/v1/automation.py`
- Modify: `app/services/automation.py`
- Modify: `app/services/llm.py`
- Modify: `app/services/news_pipeline.py`
- Modify: `app/services/news_video_search.py`
- Modify: `app/services/web_media.py`
- Modify: `config.example.toml`
- Test: `tests/controllers/test_news_automation.py`
- Test: `tests/services/test_news_pipeline.py`
- Test: `tests/services/test_news_video_search.py`

- [x] **Step 1: Run news automation tasks sequentially**

API-created news runs now enqueue one sequential runner. Each story calls `tm.start()` and reaches its publish phase before the next story starts.

- [x] **Step 2: Make news scripts more substantial**

News defaults now request 3 paragraphs, a faster `news_voice_rate`, and a 160-220 spoken-word serious newsreader script when source facts are sufficient.

- [x] **Step 3: Add web-page candidates to yt-dlp search**

`news_video_search` now asks `web_media.search_video_pages()` for headline-matching video/article pages and tries those URLs with `yt-dlp` before the stock fallback path.

- [x] **Step 4: Verify**

Run: `D:\moneyprinter\lib\python\python.exe -m compileall app\controllers\v1\automation.py app\services\automation.py app\services\llm.py app\services\news_pipeline.py app\services\news_video_search.py app\services\web_media.py tests\controllers\test_news_automation.py tests\services\test_news_pipeline.py tests\services\test_news_video_search.py`
Result: PASS.

Run: `D:\moneyprinter\lib\python\python.exe -m unittest tests.services.test_social_metadata tests.services.test_news_history tests.services.test_news_story_quality tests.controllers.test_news_automation tests.services.test_news_video_search tests.services.test_web_media tests.services.test_news_pipeline tests.services.test_task_news_history tests.services.test_news_diagnostics tests.services.test_video_branding tests.services.test_youtube_publisher -v`
Result: PASS, 35 tests.

## Task 7: Broaden Unique Article Selection

**Files:**
- Modify: `app/services/news_sources/__init__.py`
- Modify: `app/services/news_history.py`
- Test: `tests/services/test_news_history.py`
- Test: `tests/services/test_news_providers.py`

- [x] **Step 1: Collect auto-source candidates from every configured provider**

`auto` now treats `limit` as a per-source candidate request instead of stopping as soon as the first provider fills the total limit. This gives ranking and history filtering enough candidates to find the next fresh article when early providers repeat old stories.

- [x] **Step 2: Detect duplicate articles by strong headline**

The news history ledger now stores an additional title signature for sufficiently specific headlines. A later story with a different URL but the same strong headline is skipped as a duplicate.

- [x] **Step 3: Verify**

Run: `D:\moneyprinter\lib\python\python.exe -m compileall app\services\news_sources\__init__.py app\services\news_history.py tests\services\test_news_history.py tests\services\test_news_providers.py`
Result: PASS.

Run: `D:\moneyprinter\lib\python\python.exe -m unittest tests.services.test_social_metadata tests.services.test_news_history tests.services.test_news_story_quality tests.services.test_news_providers tests.controllers.test_news_automation tests.services.test_news_video_search tests.services.test_web_media tests.services.test_news_pipeline tests.services.test_task_news_history tests.services.test_news_diagnostics tests.services.test_video_branding tests.services.test_youtube_publisher -v`
Result: PASS, 41 tests.

## Task 8: Tighten Deep Video Relevance

**Files:**
- Modify: `app/services/news_video_search.py`
- Modify: `config.example.toml`
- Modify: `docs/NEWS_AUTOMATION_FEATURES.md`
- Test: `tests/services/test_news_video_search.py`

- [x] **Step 1: Require stronger keyword overlap for long headlines**

The `yt-dlp` relevance gate now computes query terms, entry terms, matched terms, and keyword coverage. Long headlines require at least `news_ytdlp_min_keyword_overlap` matching terms or enough coverage before a downloaded entry is accepted.

- [x] **Step 2: Record skipped relevance details**

Each `attempt` now includes `skipped_relevance` with the skipped title, matched terms, coverage, and required overlap. This makes diagnostics useful when the app falls back to stock clips.

- [x] **Step 3: Document production knobs**

Added `news_ytdlp_min_keyword_overlap` and `news_ytdlp_min_keyword_coverage` to the example config and documented the relevance gate in `docs/NEWS_AUTOMATION_FEATURES.md`.

## Task 9: Prefer Related Telegram Clips Before YouTube/Stock

**Files:**
- Modify: `app/services/news_pipeline.py`
- Modify: `app/services/task.py`
- Modify: `config.example.toml`
- Modify: `docs/NEWS_AUTOMATION_FEATURES.md`
- Test: `tests/services/test_news_pipeline.py`
- Test: `tests/services/test_task_news_history.py`

- [x] **Step 1: Add related Telegram video discovery**

`news_pipeline.discover_related_telegram_video_materials()` searches configured Telethon channels by the selected news headline and returns direct video materials.

- [x] **Step 2: Insert Telegram clips before yt-dlp**

News material preparation now tries direct story media, then related Telegram clips, then `yt-dlp`, then stock fallback.

- [x] **Step 3: Record diagnostics**

Tasks now record `news_related_telegram_search_started` and `news_related_telegram_search_completed` with query, requested count, downloaded paths, and total video count.

## Task 10: Expose Media Source Summary

**Files:**
- Modify: `app/services/news_diagnostics.py`
- Modify: `app/services/task.py`
- Modify: `app/controllers/v1/automation.py`
- Modify: `webui/Main.py`
- Test: `tests/services/test_news_diagnostics.py`
- Test: `tests/controllers/test_news_automation.py`

- [x] **Step 1: Summarize media provenance**

Diagnostics now produce `news_media_summary` with total clips, non-stock clip count, used sources, fallback status, and per-stage details for direct news media, related Telegram clips, `yt-dlp`, and stock fallback.

- [x] **Step 2: Return summary from task results**

Completed tasks and `stop_at="materials"` runs now persist `news_media_summary` alongside the generated materials.

- [x] **Step 3: Expose summary in UI/API**

Streamlit inline news automation payloads and `/api/v1/automation/tasks/{task_id}/publish` now include the same media summary so source/fallback behavior is visible without reading terminal logs.

## Task 11: Add Local Automation Analytics

**Files:**
- Create: `app/services/news_analytics.py`
- Modify: `app/controllers/v1/automation.py`
- Modify: `webui/Main.py`
- Modify: `docs/NEWS_AUTOMATION_FEATURES.md`
- Test: `tests/services/test_news_analytics.py`
- Test: `tests/controllers/test_news_automation.py`

- [x] **Step 1: Summarize run quality**

`news_analytics.summarize_news_items()` now counts generated videos, completed/failed tasks, upload attempts, upload success/failure, per-platform results, non-stock media, stock fallback usage, stock-only runs, no-media runs, and weak `unknown` titles.

- [x] **Step 2: Expose current-state analytics**

`/api/v1/automation/news/analytics` returns a local operational summary for news automation tasks currently in app state.

- [x] **Step 3: Include analytics in Streamlit inline runs**

Streamlit news automation responses now include an `analytics` object above the detailed per-task results.

## Task 12: Explain Publishing Readiness

**Files:**
- Modify: `app/services/task.py`
- Modify: `app/services/news_analytics.py`
- Modify: `app/controllers/v1/automation.py`
- Modify: `webui/Main.py`
- Modify: `docs/NEWS_AUTOMATION_FEATURES.md`
- Test: `tests/services/test_task_news_history.py`
- Test: `tests/services/test_news_analytics.py`
- Test: `tests/controllers/test_news_automation.py`

- [x] **Step 1: Add publishing preflight**

`_social_publish_preflight()` now reports whether auto-publish is enabled, requested platforms, enabled platforms, skipped platforms, privacy, and skip reasons such as `youtube_not_connected` or `tiktok_direct_post_consent_missing`.

- [x] **Step 2: Persist and expose preflight**

Tasks record `social_publish_preflight` diagnostics and include `publish_preflight` in task results, Streamlit inline output, and `/api/v1/tasks/{task_id}/publish`.

- [x] **Step 3: Count blocked publishing**

Local analytics now counts tasks blocked before upload and groups them by preflight skip reason.
