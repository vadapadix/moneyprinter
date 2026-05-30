# Plan: automated trend-to-video-to-social publishing

Date: 2026-05-30
Scope: MoneyPrinterTurbo backend and WebUI automation for trend discovery, video generation, metadata generation, and publishing to TikTok plus YouTube Shorts.

## Question

Automate the application so it can discover popular trends, create videos from them, generate title/description/hashtags/metadata, and automatically publish completed short videos to TikTok and YouTube Shorts.

## Ranked synthesis

| Rank | Explanation | Confidence | Basis |
| --- | --- | --- | --- |
| 1 | The current app already has the correct main pipeline hook: video generation ends in `app.services.task.start`, and a post-generation upload step already exists. | High | `app/services/task.py:248` starts the pipeline, `app/services/task.py:343` creates final videos, and `app/services/task.py:356` runs cross-posting after final video generation. |
| 2 | The upload layer is incomplete for the requested goal: it supports Upload-Post-style TikTok/Instagram only, not YouTube Shorts, and does not model title/description/hashtags per platform. | High | `app/services/upload_post.py:1` describes TikTok/Instagram; `config.example.toml:301` lists `["tiktok", "instagram"]`; `app/services/task.py:363` passes only `params.video_subject` as title. |
| 3 | The LLM layer can be reused for metadata generation, but needs a new structured function because current prompts produce only scripts and stock-video search terms. | High | `app/services/llm.py:461` generates scripts; `app/services/llm.py:535` generates stock-video terms as JSON arrays. |
| 4 | Trend discovery is a new subsystem, not a small extension of existing `material.py`; current external discovery is for stock media, not social trend mining. | High | `app/services/material.py:55` and `app/services/material.py:112` search Pexels/Pixabay video assets from terms, not platform trends. |
| 5 | Fully automatic public publishing has external approval constraints; the first production-safe design should support private/draft/unlisted modes and explicit status tracking. | High | TikTok and YouTube official docs both mention audit/private restrictions for unaudited clients. |

## Evidence

- `app/controllers/v1/video.py:115` exposes `POST /videos`; `app/controllers/v1/video.py:150` queues `tm.start`.
- `app/controllers/manager/base_manager.py:22` runs queued tasks through the task manager, with concurrency and queue limits.
- `app/services/task.py:252` to `app/services/task.py:345` shows the ordered generation pipeline: script, terms, audio, subtitle, materials, final videos.
- `app/services/task.py:356` to `app/services/task.py:380` is the existing post-generation upload hook and result storage.
- `app/services/upload_post.py:12` to `app/services/upload_post.py:147` provides one cross-post service using an API key, username, platforms, and title.
- `config.example.toml:288` to `config.example.toml:305` documents Upload-Post config for TikTok/Instagram and auto-upload.
- `app/models/schema.py:58` to `app/models/schema.py:109` defines `VideoParams`; it has no social metadata, trend source, campaign, schedule, privacy, or platform upload fields.
- `app/services/state.py:35` to `app/services/state.py:51` stores arbitrary task kwargs, so upload and trend metadata can be persisted without first changing the state backend contract.
- `app/router.py:12` to `app/router.py:17` registers only video and LLM routers; a new trend/social router must be added explicitly.
- YouTube official docs: `videos.insert` uploads videos, can set metadata, uses OAuth scopes, has quota cost, and unaudited post-July-2020 projects upload as private until audit.
- TikTok official docs: Content Posting API supports Direct Post / Upload API, requires creator info, metadata, user consent, `video.publish` scope, and unaudited clients are restricted to private visibility.

Sources:
- YouTube Data API videos.insert: https://developers.google.com/youtube/v3/docs/videos/insert
- YouTube Data API videos resource: https://developers.google.com/youtube/v3/docs/videos
- TikTok Content Posting API Direct Post: https://developers.tiktok.com/doc/content-posting-api-reference-direct-post
- TikTok Content Posting API product page: https://developers.tiktok.com/products/content-posting-api
- TikTok Creative Center Trends help: https://ads.tiktok.com/help/article/how-to-use-trends

## Inference

- The least disruptive architecture is to keep `task.start()` as the generation owner and add a separate social publishing service invoked after final video creation.
- Metadata should be generated before upload but after script creation, because it can use `video_subject`, `video_script`, generated `terms`, platform policy limits, and trend context.
- Trend discovery should create ordinary `TaskVideoRequest` jobs rather than bypassing the existing generation pipeline.
- Because YouTube and TikTok both have OAuth/audit/privacy constraints, the app should default to draft/private/unlisted publishing until credentials and approval are verified.

## Unknowns / limits

- Whether the user wants direct native TikTok/YouTube APIs or a third-party aggregator such as Upload-Post for all platforms.
- Whether the account has approved TikTok Content Posting API access and an audited YouTube API project.
- Which regions/languages/niches should drive trend selection.
- Whether publication should be fully automatic or require a review queue before public posting.

## Requirements summary

1. Discover trending topics from configured sources by region, language, category/niche, and freshness window.
2. Convert selected trends into video subjects and generation params.
3. Generate script, stock-video search terms, title, description, hashtags, tags, category, privacy, and synthetic-media flags.
4. Create portrait short videos using the existing MoneyPrinterTurbo pipeline.
5. Publish completed videos to TikTok and YouTube Shorts automatically when enabled.
6. Persist trend inputs, generated metadata, upload attempts, platform IDs, URLs, failures, and retry status.
7. Expose API and WebUI controls for credentials, trend settings, platform settings, preview, retry, and status.

## Architecture decision

Decision: introduce three bounded services and one orchestration layer:

- `app/services/trends.py`: providers for trend discovery.
- `app/services/social_metadata.py`: LLM-backed metadata generation and validation.
- `app/services/publishers/`: platform-specific upload clients.
- `app/services/automation.py`: orchestrates trend selection, task creation, generation completion, upload, retry, and status.

Keep existing `app/services/task.py` generation flow intact. Add a small post-generation handoff from `task.start()` to the social publishing layer, replacing the current direct Upload-Post call over time.

## Viable options

Option A: native platform APIs.

- Pros: full control, YouTube Shorts support, better status model, fewer third-party lock-ins.
- Cons: OAuth, token storage, platform review/audit, more implementation work.

Option B: third-party posting aggregator.

- Pros: faster integration, one API for many platforms, less OAuth plumbing in this repo.
- Cons: dependency on aggregator support/limits, possible YouTube Shorts gaps, extra cost, less control over audit errors and metadata behavior.

Option C: hybrid.

- Pros: keep existing Upload-Post path for TikTok/Instagram while implementing native YouTube; later add native TikTok when account audit is ready.
- Cons: two upload abstractions initially.

Chosen path: hybrid first, with a normalized publisher interface. It fits the existing code and avoids blocking YouTube Shorts on a TikTok audit.

## Implementation steps

1. Add social domain models.
   - Extend `app/models/schema.py` with `SocialMetadata`, `PlatformPublishSettings`, `TrendSourceSettings`, `TrendCandidate`, `AutomationRequest`, `PublishResult`, and optional fields on `VideoParams`.
   - Acceptance: Pydantic validates platform names, privacy values, hashtags, max title lengths, and optional synthetic-media flags.

2. Replace direct Upload-Post coupling with a publisher interface.
   - Create `app/services/publishers/base.py`.
   - Move current Upload-Post logic behind `UploadPostPublisher`.
   - Add `YouTubeShortsPublisher` using YouTube Data API `videos.insert` with `snippet,status`.
   - Keep current `upload_post.py` as a compatibility wrapper or migrate callers gradually.
   - Acceptance: `task.start()` depends on a generic publisher service, not directly on Upload-Post.

3. Add metadata generation.
   - Add `llm.generate_social_metadata(video_subject, video_script, terms, trend_context, platforms, language)`.
   - Require strict JSON output: title, description, hashtags, youtube_tags, category hints, platform captions, safety flags.
   - Add sanitizer/fallback logic for invalid JSON and length limits.
   - Acceptance: unit tests cover valid JSON, markdown-wrapped JSON, invalid JSON fallback, hashtag normalization, title length limits, and `#Shorts` injection for YouTube.

4. Add trend discovery providers.
   - Start with YouTube Data API `videos.list(chart=mostPopular, regionCode=...)` and optional `videoCategoryId`.
   - Add TikTok Creative Center provider as a configurable source only if a stable/allowed access path is available; otherwise support manual seed lists plus a documented connector boundary.
   - Add Google Trends or another allowed source only if explicitly selected later.
   - Acceptance: trend providers return normalized candidates with source, region, title/topic, score, URL/reference, tags, and fetched timestamp.

5. Add automation orchestration.
   - Add `app/services/automation.py` to select trends, deduplicate previous topics, build `TaskVideoRequest`, enqueue existing generation, and attach automation metadata.
   - Add retry/backoff for publishing failures separate from video-generation failures.
   - Acceptance: trend-to-task can run without publishing; publishing can retry an existing completed task without regenerating the video.

6. Add API endpoints.
   - Add `app/controllers/v1/automation.py` and register it in `app/router.py`.
   - Endpoints:
     - `GET /trends`
     - `POST /automation/runs`
     - `GET /automation/runs/{run_id}`
     - `POST /tasks/{task_id}/publish`
     - `GET /tasks/{task_id}/publish`
     - `POST /tasks/{task_id}/metadata/regenerate`
   - Acceptance: endpoints return stable IDs and never expose secrets.

7. Add config.
   - Extend `config.example.toml` with `[social]`, `[social.youtube]`, `[social.tiktok]`, `[automation]`, and `[trends]` settings.
   - Include defaults: `auto_publish=false`, YouTube `privacy_status="private"` or `"unlisted"`, TikTok direct post disabled until OAuth/audit configured.
   - Acceptance: missing credentials disable publishing with clear task status, not crashes.

8. Add WebUI controls.
   - Add a compact automation section in `webui/Main.py`: trend source, region, niche, count, platform toggles, privacy, review-before-publish toggle, run button, recent run status.
   - Add task-level publish retry and metadata preview.
   - Acceptance: current manual video generation still works unchanged.

9. Add storage/status.
   - Store `automation_run`, `trend_candidate`, `social_metadata`, and `publish_results` in task state.
   - For durable history, add JSON files under task folders or a small storage service; Redis state alone is not enough for long-term audit/history.
   - Acceptance: task query response includes publish status without breaking existing clients.

10. Verification and docs.
   - Add unit tests for metadata, trend normalization, publisher request construction, and task orchestration.
   - Add mocked integration tests for YouTube and TikTok/Upload-Post clients.
   - Update README/config docs with credential setup, audit/private restrictions, and safe defaults.

## Acceptance criteria

- Given configured trend source and `auto_generate=true`, the app creates at least one queued video task from a trend candidate.
- Given a completed video and generated social metadata, `POST /tasks/{task_id}/publish` uploads or returns a structured disabled/credential error.
- YouTube upload request includes title, description, tags, category, privacy status, and `#Shorts` in title or description.
- TikTok publishing path supports caption/hashtags/privacy and records audit/private-mode limitations.
- If upload fails, the task remains complete for video generation and stores per-platform publish failure details.
- Existing `POST /videos`, `/tasks/{task_id}`, `/scripts`, and `/terms` behavior remains backward compatible.
- No API keys, OAuth tokens, or refresh tokens are returned through task/query endpoints or logs.

## Risks and mitigations

- Platform audit restrictions: default to private/unlisted/draft and expose clear status.
- OAuth/token handling: isolate credential storage, redact logs, add config validation.
- Unstable TikTok trend data access: treat Creative Center as a provider behind an interface; support manual/YouTube trend sources first.
- LLM JSON brittleness: strict schema validation plus deterministic fallback metadata.
- Duplicate/low-quality trend videos: keep a recent-topic cache and minimum score/freshness thresholds.
- Posting policy issues: include review-before-public mode and platform-specific metadata limits.

## Verification steps

1. `python -m unittest test.services.test_llm`
2. Add and run new tests:
   - `test.services.test_social_metadata`
   - `test.services.test_publishers`
   - `test.services.test_trends`
   - `test.services.test_automation`
3. Run existing focused tests:
   - `python -m unittest test.services.test_task`
   - `python -m unittest test.services.test_video`
   - `python -m unittest test.services.test_material`
4. Run an API smoke test with mocked publishers:
   - create video task from manual trend
   - mark or mock video completion
   - publish to fake YouTube/TikTok clients
   - assert task state includes metadata and per-platform results.

## ADR

Decision: build a normalized social automation layer around the existing generation pipeline.

Drivers:
- Preserve current video generation behavior.
- Support YouTube Shorts, which current Upload-Post integration does not cover.
- Keep publishing failures separate from generation failures.
- Allow trend providers to evolve without rewriting video generation.

Alternatives considered:
- Only extend `upload_post.py`: rejected because it would keep platform-specific behavior in the task pipeline and does not address trend discovery or metadata modeling.
- Rewrite task generation as a new automation pipeline: rejected because `task.start()` already handles the expensive generation stages and has tests/state integration.
- Implement native TikTok first: rejected as the first milestone because TikTok Content Posting API requires approval/audit and consent UX, while existing Upload-Post can be preserved as a bridge.

Why chosen:
- It is the smallest change that creates clean boundaries for trends, metadata, upload, status, and retries.

Consequences:
- Requires new config and status models.
- Requires careful secret handling and mocked integration tests.
- Public auto-posting may remain blocked until platform audits/OAuth setup are completed.

Follow-ups:
- Decide whether TikTok should remain via Upload-Post initially or move to native Content Posting API immediately.
- Decide target regions/languages/niches for trend discovery.
- Decide whether public posting requires review approval.

## Follow-up staffing guidance

- `explore`: map exact WebUI insertion points and current config conventions.
- `executor`: implement models, services, publishers, and endpoints.
- `test-engineer`: add mocked publisher/trend/metadata tests and regression tests for existing task flow.
- `critic` or `code-reviewer`: review OAuth/secret handling and platform-policy edge cases.

Recommended execution path: Team + Ultragoal for durable implementation. Team handles parallel lanes (models/publishers, trends/automation, WebUI/tests); Ultragoal tracks acceptance criteria and platform-integration evidence. Ralph fallback is only useful if a single-owner sequential implementation is preferred.

Launch hints:

```text
$ultragoal .omx/plans/social-automation-plan-2026-05-30-091509.md
$team .omx/plans/social-automation-plan-2026-05-30-091509.md
```

## Team verification path

- Team proves local behavior with mocked API clients and no real uploads.
- Ultragoal checkpoints:
  - generation path unchanged
  - metadata schema validated
  - trend-to-task run works
  - publish retry works
  - secrets are redacted
  - docs explain YouTube/TikTok audit/private-mode constraints
