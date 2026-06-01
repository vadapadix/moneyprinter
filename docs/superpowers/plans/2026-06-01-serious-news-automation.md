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
