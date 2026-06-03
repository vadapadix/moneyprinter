# News Automation Features

This document describes the news shorts automation pipeline in operational detail.

## 1. Article Discovery

The default source is `auto`. In this mode the app searches every provider listed in `news_auto_sources`:

- `telethon`: Telegram MTProto channels from `telegram_user_channels`.
- `newsdata`: NewsData.io latest news API.
- `guardian`: Guardian Open Platform.
- `telegram`: Telegram Bot API channels that the bot can read.

Provider results are normalized to `NewsStory` objects with title, summary, source URL, publication date, keywords, and media assets. Auto mode gathers candidates from every configured provider before ranking, and duplicate URLs are removed before the automation queue is built.

When `telegram_global_search = true`, Telethon does not use Telegram's premium-only global `SearchPostsRequest`. It scans accessible dialogs and joined channels instead, using `telegram_global_search_dialog_limit` and `telegram_recent_scan_limit`, so regular Telegram accounts can still find matching recent posts from sources the account can access.

## 2. Unique Story Memory

Every queued story is reserved in `storage/news/history.json`. The primary key is the source URL when available, otherwise a provider/title/date hash. For sufficiently specific headlines, the ledger also stores a title signature, so the same article can be skipped even when it appears at a different URL.

Title signatures are Unicode-aware, so non-English sources such as Ukrainian Telegram posts are deduplicated by headline as well as URL. The selector also applies `news_title_similarity_threshold` to avoid queuing near-duplicate headlines in the same run or across previous runs.

When the first fetched batch is mostly old/reserved stories, the automation increases the provider fetch limit in waves until it finds the requested number of unique articles or reaches `news_unique_selection_max_fetch_multiplier`. Each queued task receives the selection attempt summary in diagnostics, so a user can see whether the run stopped because the providers had no new stories or because the limit was reached.

Story result status is updated after generation:

- `reserved`: selected for a run.
- `completed`: generated at least one video.
- `failed`: selected but no video was produced.

## 3. Story Quality Ranking

Stories are scored before they are selected. The score favors:

- clear headlines;
- detailed summaries;
- source URLs;
- direct video media;
- image/media assets;
- keywords;
- fresh publication dates.

Weak headlines, missing summaries, and missing source URLs are penalized. This keeps the automation from wasting video generation on thin posts when richer stories are available.

## 4. English Script Generation

News videos force English output through `news_output_language = "en"` unless a run explicitly overrides it. The source can be Ukrainian, English, Telegram, Guardian, or NewsData, but the generated voiceover prompt asks for a factual English newsreader script grounded only in the source material.

The prompt asks for 160-220 spoken words when the source has enough facts and avoids invented details, filler, broad lessons, and generic intros. Thin source material stays shorter instead of being padded.

## 5. Media Discovery Order

The media pipeline tries sources in this order:

1. Direct media attached to the story, especially Telegram/downloaded video assets.
2. Video URLs discovered from article pages, `og:video`, embedded `<video>` tags, and page metadata.
3. Web search variants based on headline, provider, and category.
4. Related Telegram video search across configured Telethon channels using the selected headline.
5. `yt-dlp` source URL extraction, then multiple YouTube search variants around the headline, provider, category, latest footage, official video, and eyewitness video.
6. Stock fallback from `news_stock_fallback_source`.

The target clip count is controlled by `news_min_clips`.

For news tasks, `news_preserve_media_order = true` keeps direct news media, related Telegram clips, article videos, and `yt-dlp` footage ahead of stock fallback in the final edit. Stock clips are still allowed as filler, but they are not randomly shuffled in front of real news material.

The `yt-dlp` stage records every attempted target in diagnostics, including downloaded counts, skipped weakly relevant entries, matched terms, keyword coverage, and target errors. The relevance gate is controlled by `news_ytdlp_min_keyword_overlap` and `news_ytdlp_min_keyword_coverage`; this makes it harder for a random popular video with only one weak word match to enter the final edit.

## 6. Social Metadata

After the final video is generated, the app asks the LLM for:

- title;
- description;
- hashtags;
- YouTube tags;
- platform captions;
- source attribution.

If the LLM returns weak titles such as `unknown`, `untitled`, or `generated short video`, the app falls back to the real source headline before uploading. `#Shorts` is guaranteed in metadata.

## 7. Publishing

When `social_auto_publish` or the news run request enables publishing, the task publishes before completing the task result. Platforms come from the UI request or `social_platforms` in config.

YouTube uses the official YouTube upload path. TikTok uses the configured TikTok Content Posting API path and still depends on TikTok review/scope constraints.

TikTok can also run in `tiktok_publish_mode = "browser_assist"`. In this mode the app does not store a TikTok password and does not call the Content Posting API. It creates a local upload package with the MP4, `caption.txt`, `metadata.json`, and a helper HTML page, copies the caption to the clipboard when possible, opens TikTok Studio, and returns `manual_review_required` so the creator can review and click Post manually.

Upload tests use the same configured publisher selector as real task publishing. This means the Streamlit upload-test buttons and `/api/v1/test-upload` exercise YouTube upload, TikTok API upload, or TikTok browser assist according to the current config instead of bypassing the selected mode.

Every completed task includes `publish_preflight`, which explains whether publishing was requested and which platforms were enabled or skipped before upload. Common skip reasons are:

- `auto_publish_disabled`;
- `youtube_not_connected`;
- `tiktok_upload_disabled`;
- `tiktok_browser_upload_disabled`;
- `tiktok_direct_post_consent_missing`;
- `no_enabled_platforms`.

This makes a non-uploading run visible in the API/Streamlit result instead of only in terminal logs.

## 8. Branding

Every rendered video can receive a `DOLIDE News` intro overlay during the first seconds and a persistent watermark.

Intro overlay config:

- `brand_intro_enabled`;
- `brand_intro_text`;
- `brand_intro_label`;
- `brand_intro_duration`;
- `brand_intro_background_opacity`;
- `brand_intro_font_size`;
- `brand_intro_headline_font_size`.

Watermark config:

- `brand_watermark_enabled`;
- `brand_watermark_text`;
- `brand_watermark_position`;
- `brand_watermark_font_size`;
- `brand_watermark_opacity`.

## 9. Diagnostics

Each task writes diagnostics to `storage/news/diagnostics/{task_id}.json`. Streamlit automation output and `/tasks/{task_id}/publish` include those diagnostics.

The same responses also include `news_media_summary`, a compact view of the media decision path:

- `status`: whether the run used news media, only fallback media, or no media.
- `total_video_count`: clips collected for the edit.
- `non_stock_video_count`: clips from direct story media, Telegram, article/video pages, or `yt-dlp`.
- `stock_fallback_used`: whether stock footage had to fill gaps.
- `used_sources`: sources that actually supplied clips.
- `stages`: per-stage requested/downloaded counts, paths, `yt-dlp` attempt count, and skipped relevance count.

Important events:

- `news_story_reserved`;
- `news_direct_media_ready`;
- `news_related_telegram_search_started`;
- `news_related_telegram_search_completed`;
- `news_ytdlp_search_started`;
- `news_ytdlp_search_completed`;
- `news_stock_fallback_started`;
- `news_stock_fallback_completed`;
- `social_metadata_ready`;
- `social_publish_skipped`;
- `social_publish_completed`.

Use these events to see exactly why a run used stock footage, skipped a platform, or uploaded with specific metadata.

## 10. Local Analytics

Streamlit inline news runs include an `analytics` object, and the API exposes `/api/v1/automation/news/analytics`.

The analytics summary is local operational telemetry. It does not send data to an external analytics service. It tracks:

- generated task and video counts;
- generation success/failure rate;
- upload attempts, successful uploads, and failed uploads;
- tasks blocked before upload and their preflight skip reasons;
- per-platform upload success/failure counts;
- non-stock video count;
- stock fallback and stock-only task counts;
- `unknown` or otherwise weak metadata title count.

Use this summary to confirm that automation is actually moving from article selection to video generation to publishing, not just producing files locally.
