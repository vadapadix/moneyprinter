# TikTok Browser Assisted Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe TikTok browser-assisted publishing mode that prepares the video, caption, hashtags, and upload page without storing TikTok credentials or using the paid/API-only direct-post path.

**Architecture:** Keep the existing publisher interface and add a second TikTok publisher implementation selected by config. The browser-assisted publisher creates a local upload package, copies the ready caption to clipboard when possible, opens TikTok Studio, and returns a structured result that clearly says human review is required.

**Tech Stack:** Python stdlib (`webbrowser`, `json`, `tkinter` clipboard fallback), existing `Publisher` / `PublishResult` interfaces, Streamlit UI config, unittest.

---

## File Structure

- `app/services/publishers/tiktok_browser.py`: new browser-assisted TikTok publisher, upload package writer, caption builder, clipboard/browser helpers.
- `app/services/social_publisher.py`: choose API TikTok publisher or browser-assisted publisher from config.
- `app/services/task.py`: treat TikTok as enabled when browser-assisted mode is configured, and record a manual-review preflight note.
- `config.example.toml`: add TikTok browser-assisted settings.
- `webui/Main.py`: expose TikTok API vs browser-assisted status and selection.
- `tests/services/test_tiktok_browser_publisher.py`: unit tests for package creation, metadata, clipboard/browser calls.
- `tests/services/test_social_publisher.py`: unit tests for publisher selection.
- `tests/services/test_task_news_history.py`: unit test for preflight accepting browser-assisted TikTok.

## Task 1: Browser-Assisted TikTok Publisher

**Files:**
- Create: `app/services/publishers/tiktok_browser.py`
- Test: `tests/services/test_tiktok_browser_publisher.py`

- [x] **Step 1: Write tests for caption/package/open behavior**

Test that publishing creates `caption.txt`, `metadata.json`, `open_upload.html`, copies the caption when enabled, opens TikTok Studio when enabled, and returns `status="manual_review_required"`.

- [x] **Step 2: Implement publisher**

Implement `TikTokBrowserPublisher` using the existing `Publisher` interface and no TikTok password storage.

- [x] **Step 3: Verify tests pass**

Run: `python -m unittest tests.services.test_tiktok_browser_publisher -v`

## Task 2: Publisher Selection and Preflight

**Files:**
- Modify: `app/services/social_publisher.py`
- Modify: `app/services/task.py`
- Test: `tests/services/test_social_publisher.py`
- Test: `tests/services/test_task_news_history.py`

- [x] **Step 1: Add mode selection tests**

Test `tiktok_publish_mode="browser_assist"` returns the browser-assisted publisher and that preflight enables TikTok when `tiktok_browser_upload_enabled=true`.

- [x] **Step 2: Implement mode selection and preflight**

Select API publisher by default; select browser-assisted publisher only when config requests it. Add preflight metadata so results explain that TikTok still needs a final manual review click.

- [x] **Step 3: Verify tests pass**

Run: `python -m unittest tests.services.test_social_publisher tests.services.test_task_news_history -v`

## Task 3: Config, UI, and Regression

**Files:**
- Modify: `config.example.toml`
- Modify: `webui/Main.py`
- Test: existing social/news regression suite

- [x] **Step 1: Add config defaults**

Add `tiktok_publish_mode`, `tiktok_browser_upload_enabled`, `tiktok_browser_upload_url`, `tiktok_browser_open_upload_page`, `tiktok_browser_copy_caption`, and `tiktok_browser_upload_dir`.

- [x] **Step 2: Expose in Streamlit**

Show browser-assisted TikTok as connected when enabled, allow selecting TikTok without API tokens, and explain that final TikTok posting still requires review in the opened browser.

- [x] **Step 3: Run focused and broad tests**

Run focused publisher/preflight tests, compile changed files, then run the existing social/news regression suite.
