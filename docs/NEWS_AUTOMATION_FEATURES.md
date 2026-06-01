# News Automation Features

This document describes the news shorts automation pipeline in operational detail.

## 1. Article Discovery

The default source is `auto`. In this mode the app searches every provider listed in `news_auto_sources`:

- `telethon`: Telegram MTProto channels from `telegram_user_channels`.
- `newsdata`: NewsData.io latest news API.
- `guardian`: Guardian Open Platform.
- `telegram`: Telegram Bot API channels that the bot can read.

Provider results are normalized to `NewsStory` objects with title, summary, source URL, publication date, keywords, and media assets. Duplicate URLs are removed before the automation queue is built.

## 2. Unique Story Memory

Every queued story is reserved in `storage/news/history.json`. The key is the source URL when available, otherwise a provider/title/date hash. This prevents repeated articles between runs.

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

The prompt asks for 90-130 spoken words and avoids invented details, filler, broad lessons, and generic intros.

## 5. Media Discovery Order

The media pipeline tries sources in this order:

1. Direct media attached to the story, especially Telegram/downloaded video assets.
2. Video URLs discovered from article pages, `og:video`, embedded `<video>` tags, and page metadata.
3. Web search variants based on headline, provider, and category.
4. `yt-dlp` source URL extraction, then multiple YouTube search variants around the headline, provider, category, latest footage, official video, and eyewitness video.
5. Stock fallback from `news_stock_fallback_source`.

The target clip count is controlled by `news_min_clips`.

The `yt-dlp` stage records every attempted target in diagnostics, including downloaded counts, skipped weakly relevant entries, and target errors. This makes it easier to tell whether a task used real source media, YouTube/news footage, or stock fallback.

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

Important events:

- `news_story_reserved`;
- `news_direct_media_ready`;
- `news_ytdlp_search_started`;
- `news_ytdlp_search_completed`;
- `news_stock_fallback_started`;
- `news_stock_fallback_completed`;
- `social_metadata_ready`;
- `social_publish_skipped`;
- `social_publish_completed`.

Use these events to see exactly why a run used stock footage, skipped a platform, or uploaded with specific metadata.
