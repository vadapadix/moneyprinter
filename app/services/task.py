import math
import os
import os.path
import re
from os import path

from loguru import logger

from app.config import config
from app.models import const
from app.models.schema import PublishPrivacy, VideoConcatMode, VideoParams
from app.services import (
    llm,
    material,
    news_diagnostics,
    news_history,
    news_pipeline,
    news_video_search,
    social_metadata,
    social_publisher,
    subtitle,
    video,
    voice,
    youtube_oauth,
)
from app.services.social_platform_utils import platform_values
from app.services import state as sm
from app.utils import utils


def generate_script(task_id, params):
    logger.info("\n\n## generating video script")
    video_script = params.video_script.strip()
    if not video_script:
        if params.video_source == "news":
            video_script = llm.generate_news_script(
                video_subject=params.video_subject,
                language=params.video_language or "en",
                paragraph_number=params.paragraph_number,
                source_context=params.news_source_context,
            )
            news_diagnostics.record_event(
                task_id,
                "news_script_ready",
                word_count=len(re.findall(r"\S+", video_script or "")),
                language=params.video_language or "en",
                title=(params.news_source_context or {}).get("title", ""),
                source_url=(params.news_source_context or {}).get("source_url", ""),
            )
        else:
            video_script = llm.generate_script(
                video_subject=params.video_subject,
                language=params.video_language,
                paragraph_number=params.paragraph_number,
            )
    else:
        logger.debug(f"video script: \n{video_script}")

    if not video_script:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error("failed to generate video script.")
        return None

    return video_script


def generate_terms(task_id, params, video_script):
    logger.info("\n\n## generating video terms")
    video_terms = params.video_terms
    if not video_terms:
        video_terms = llm.generate_terms(
            video_subject=params.video_subject, video_script=video_script, amount=5
        )
        if isinstance(video_terms, str) and video_terms.startswith("Error: "):
            logger.warning("falling back to local search terms after LLM terms failure")
            video_terms = _fallback_search_terms(params, video_script)
    else:
        if isinstance(video_terms, str):
            video_terms = [term.strip() for term in re.split(r"[,，]", video_terms)]
        elif isinstance(video_terms, list):
            video_terms = [term.strip() for term in video_terms]
        else:
            raise ValueError("video_terms must be a string or a list of strings.")

        logger.debug(f"video terms: {utils.to_json(video_terms)}")

    if not video_terms:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error("failed to generate video terms.")
        return None

    return video_terms


def _fallback_search_terms(params, video_script: str, amount: int = 5) -> list[str]:
    source = " ".join(
        [
            str(getattr(params, "news_query", "") or ""),
            str(getattr(params, "video_subject", "") or ""),
            video_script or "",
        ]
    )
    source = re.sub(r"https?://\S+", " ", source)
    source = re.sub(r"[^A-Za-z0-9\s'-]", " ", source)
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "with",
        "write",
        "short",
        "factual",
        "news",
        "voiceover",
        "english",
        "headline",
        "story",
        "source",
        "material",
        "script",
        "video",
    }
    words = [
        word.strip("'-").lower()
        for word in source.split()
        if len(word.strip("'-")) > 2
    ]
    words = [word for word in words if word not in stop_words]

    terms = []
    proper_phrases = re.findall(r"\b[A-Z][A-Za-z0-9'-]*(?:\s+[A-Z][A-Za-z0-9'-]*){0,2}", source)
    for phrase in proper_phrases:
        cleaned = " ".join(phrase.split())
        if len(cleaned) > 2 and cleaned.lower() not in stop_words:
            terms.append(cleaned)

    for index, word in enumerate(words):
        phrase = word
        if index + 1 < len(words):
            phrase = f"{word} {words[index + 1]}"
        terms.append(phrase)

    deduped = []
    seen = set()
    for term in terms:
        normalized = " ".join(term.split()).strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
        if len(deduped) >= amount:
            break

    return deduped or ["news report"]


def save_script_data(task_id, video_script, video_terms, params):
    script_file = path.join(utils.task_dir(task_id), "script.json")
    script_data = {
        "script": video_script,
        "search_terms": video_terms,
        "params": params,
    }

    with open(script_file, "w", encoding="utf-8") as f:
        f.write(utils.to_json(script_data))


def generate_audio(task_id, params, video_script):
    '''
    Generate audio for the video script.
    If a custom audio file is provided, it will be used directly.
    There will be no subtitle maker object returned in this case.
    Otherwise, TTS will be used to generate the audio.
    Returns:
        - audio_file: path to the generated or provided audio file
        - audio_duration: duration of the audio in seconds
        - sub_maker: subtitle maker object if TTS is used, None otherwise
    '''
    logger.info("\n\n## generating audio")
    # /audio 和 /subtitle 请求模型不包含 custom_audio_file，
    # 这里统一做兼容读取，避免直调接口时抛属性错误。
    custom_audio_file = getattr(params, "custom_audio_file", None)
    if not custom_audio_file or not os.path.exists(custom_audio_file):
        if custom_audio_file:
            logger.warning(
                f"custom audio file not found: {custom_audio_file}, using TTS to generate audio."
            )
        else:
            logger.info("no custom audio file provided, using TTS to generate audio.")
        audio_file = path.join(utils.task_dir(task_id), "audio.mp3")
        sub_maker = voice.tts(
            text=video_script,
            voice_name=voice.parse_voice_name(params.voice_name),
            voice_rate=params.voice_rate,
            voice_file=audio_file,
        )
        if sub_maker is None:
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            logger.error(
                """failed to generate audio:
1. check if the language of the voice matches the language of the video script.
2. check if the network is available. If you are in China, it is recommended to use a VPN and enable the global traffic mode.
            """.strip()
            )
            return None, None, None
        audio_duration = math.ceil(voice.get_audio_duration(sub_maker))
        if audio_duration == 0:
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            logger.error("failed to get audio duration.")
            return None, None, None
        return audio_file, audio_duration, sub_maker
    else:
        logger.info(f"using custom audio file: {custom_audio_file}")
        audio_duration = voice.get_audio_duration(custom_audio_file)
        if audio_duration == 0:
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            logger.error("failed to get audio duration from custom audio file.")
            return None, None, None
        return custom_audio_file, audio_duration, None

def generate_subtitle(task_id, params, video_script, sub_maker, audio_file):
    '''
    Generate subtitle for the video script.
    If subtitle generation is disabled or no subtitle maker is provided, it will return an empty string.
    Otherwise, it will generate the subtitle using the specified provider.
    Returns:
        - subtitle_path: path to the generated subtitle file
    '''
    logger.info("\n\n## generating subtitle")
    if not params.subtitle_enabled or sub_maker is None:
        return ""

    subtitle_path = path.join(utils.task_dir(task_id), "subtitle.srt")
    subtitle_provider = config.app.get("subtitle_provider", "edge").strip().lower()
    logger.info(f"\n\n## generating subtitle, provider: {subtitle_provider}")

    subtitle_fallback = False
    if subtitle_provider == "edge":
        voice.create_subtitle(
            text=video_script, sub_maker=sub_maker, subtitle_file=subtitle_path
        )
        if not os.path.exists(subtitle_path):
            subtitle_fallback = True
            logger.warning("subtitle file not found, fallback to whisper")

    if subtitle_provider == "whisper" or subtitle_fallback:
        subtitle.create(audio_file=audio_file, subtitle_file=subtitle_path)
        logger.info("\n\n## correcting subtitle")
        subtitle.correct(subtitle_file=subtitle_path, video_script=video_script)

    subtitle_lines = subtitle.file_to_subtitles(subtitle_path)
    if not subtitle_lines:
        logger.warning(f"subtitle file is invalid: {subtitle_path}")
        return ""

    return subtitle_path


def get_video_materials(task_id, params, video_terms, audio_duration):
    def record_news_material_mix(non_stock_paths, stock_paths=None):
        stock_paths = stock_paths or []
        news_diagnostics.record_event(
            task_id,
            "news_material_mix_ready",
            non_stock_video_count=len(non_stock_paths),
            stock_video_count=len(stock_paths),
            total_video_count=len(non_stock_paths) + len(stock_paths),
            non_stock_paths=non_stock_paths,
            stock_paths=stock_paths,
            stock_fallback_used=bool(stock_paths),
            required_clip_count=min_news_clips,
            ready_without_stock=len(non_stock_paths) >= min_news_clips,
            preserved_order=True,
        )

    if params.video_source == "local":
        logger.info("\n\n## preprocess local materials")
        materials = video.preprocess_video(
            materials=params.video_materials, clip_duration=params.video_clip_duration
        )
        if not materials:
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            logger.error(
                "no valid materials found, please check the materials and try again."
            )
            return None
        return [material_info.url for material_info in materials]
    if params.video_source == "news":
        logger.info("\n\n## preparing news video materials")
        direct_materials = news_pipeline.build_materials_from_assets(
            params.news_media_assets or []
        )
        video_paths = []
        for item in direct_materials:
            if os.path.isfile(item.url):
                saved_video_path = item.url
            else:
                saved_video_path = material.save_video(item.url, utils.task_dir(task_id))
            if saved_video_path:
                video_paths.append(saved_video_path)
        min_news_clips = int(config.app.get("news_min_clips", 3))
        if len(video_paths) >= min_news_clips:
            news_diagnostics.record_event(
                task_id,
                "news_direct_media_ready",
                direct_video_count=len(video_paths),
                required_clip_count=min_news_clips,
                source="news_assets",
                downloaded_paths=video_paths,
            )
            record_news_material_mix(video_paths)
            return video_paths

        search_query = (
            (params.news_source_context or {}).get("title")
            or params.news_query
            or params.video_subject
        )
        related_limit = max(0, min_news_clips - len(video_paths))
        news_diagnostics.record_event(
            task_id,
            "news_related_telegram_search_started",
            query=search_query,
            requested_count=related_limit,
            existing_video_count=len(video_paths),
        )
        related_materials = news_pipeline.discover_related_telegram_video_materials(
            query=search_query,
            limit=related_limit,
        )
        related_paths = []
        for item in related_materials:
            if os.path.isfile(item.url):
                saved_video_path = item.url
            else:
                saved_video_path = material.save_video(item.url, utils.task_dir(task_id))
            if saved_video_path and saved_video_path not in video_paths:
                video_paths.append(saved_video_path)
                related_paths.append(saved_video_path)
        news_diagnostics.record_event(
            task_id,
            "news_related_telegram_search_completed",
            query=search_query,
            downloaded_count=len(related_paths),
            total_video_count=len(video_paths),
            downloaded_paths=related_paths,
        )
        if len(video_paths) >= min_news_clips:
            record_news_material_mix(video_paths)
            return video_paths

        news_diagnostics.record_event(
            task_id,
            "news_ytdlp_search_started",
            query=search_query,
            requested_count=max(0, min_news_clips - len(video_paths)),
            existing_direct_video_count=len(video_paths),
        )
        ytdlp_result = news_video_search.search_and_download_report(
            query=search_query,
            save_dir=utils.task_dir(task_id),
            limit=max(0, min_news_clips - len(video_paths)),
            source_context=params.news_source_context,
        )
        ytdlp_paths = ytdlp_result.paths
        for ytdlp_path in ytdlp_paths:
            if ytdlp_path not in video_paths:
                video_paths.append(ytdlp_path)
        news_diagnostics.record_event(
            task_id,
            "news_ytdlp_search_completed",
            query=search_query,
            downloaded_count=len(ytdlp_paths),
            total_video_count=len(video_paths),
            downloaded_paths=ytdlp_paths,
            attempts=ytdlp_result.attempts,
        )
        if len(video_paths) >= min_news_clips:
            record_news_material_mix(video_paths)
            return video_paths

        fallback_source = config.app.get("news_stock_fallback_source", "pexels")
        stock_needed_count = max(0, min_news_clips - len(video_paths))
        logger.info(
            f"adding {fallback_source} stock fallback clips after {len(video_paths)} direct news clips"
        )
        news_diagnostics.record_event(
            task_id,
            "news_stock_fallback_started",
            source=fallback_source,
            existing_video_count=len(video_paths),
            existing_non_stock_video_count=len(video_paths),
            needed_count=stock_needed_count,
            required_clip_count=min_news_clips,
            search_terms=video_terms or [params.video_subject],
        )
        downloaded_videos = material.download_videos(
            task_id=task_id,
            search_terms=video_terms or [params.video_subject],
            source=fallback_source,
            video_aspect=params.video_aspect,
            video_contact_mode=params.video_concat_mode,
            audio_duration=audio_duration * params.video_count,
            max_clip_duration=params.video_clip_duration,
        )
        if not downloaded_videos:
            if video_paths:
                record_news_material_mix(video_paths)
                return video_paths
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            logger.error("failed to download fallback videos for news story")
            return None
        final_video_paths = video_paths + downloaded_videos
        news_diagnostics.record_event(
            task_id,
            "news_stock_fallback_completed",
            source=fallback_source,
            downloaded_count=len(downloaded_videos),
            total_video_count=len(final_video_paths),
            downloaded_paths=downloaded_videos,
        )
        record_news_material_mix(video_paths, downloaded_videos)
        return final_video_paths
    else:
        logger.info(f"\n\n## downloading videos from {params.video_source}")
        downloaded_videos = material.download_videos(
            task_id=task_id,
            search_terms=video_terms,
            source=params.video_source,
            video_aspect=params.video_aspect,
            video_contact_mode=params.video_concat_mode,
            audio_duration=audio_duration * params.video_count,
            max_clip_duration=params.video_clip_duration,
        )
        if not downloaded_videos:
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            logger.error(
                "failed to download videos, maybe the network is not available. if you are in China, please use a VPN."
            )
            return None
        return downloaded_videos


def generate_final_videos(
    task_id, params, downloaded_videos, audio_file, subtitle_path
):
    final_video_paths = []
    combined_video_paths = []
    video_concat_mode = (
        params.video_concat_mode if params.video_count == 1 else VideoConcatMode.random
    )
    video_transition_mode = params.video_transition_mode

    _progress = 50
    for i in range(params.video_count):
        index = i + 1
        combined_video_path = path.join(
            utils.task_dir(task_id), f"combined-{index}.mp4"
        )
        logger.info(f"\n\n## combining video: {index} => {combined_video_path}")
        video.combine_videos(
            combined_video_path=combined_video_path,
            video_paths=downloaded_videos,
            audio_file=audio_file,
            video_aspect=params.video_aspect,
            video_concat_mode=video_concat_mode,
            video_transition_mode=video_transition_mode,
            max_clip_duration=params.video_clip_duration,
            threads=params.n_threads,
        )

        _progress += 50 / params.video_count / 2
        sm.state.update_task(task_id, progress=_progress)

        final_video_path = path.join(utils.task_dir(task_id), f"final-{index}.mp4")

        logger.info(f"\n\n## generating video: {index} => {final_video_path}")
        video.generate_video(
            video_path=combined_video_path,
            audio_path=audio_file,
            subtitle_path=subtitle_path,
            output_file=final_video_path,
            params=params,
        )

        _progress += 50 / params.video_count / 2
        sm.state.update_task(task_id, progress=_progress)

        final_video_paths.append(final_video_path)
        combined_video_paths.append(combined_video_path)

    return final_video_paths, combined_video_paths


def _mark_news_story_result(
    task_id: str,
    params: VideoParams,
    success: bool,
    videos: list[str] | None = None,
    publish_results: list[dict] | None = None,
    reason: str = "",
) -> None:
    if params.video_source != "news" or not params.news_source_context:
        return

    story = news_pipeline.story_from_source_context(params.news_source_context)
    news_history.mark_story_result(
        story,
        task_id=task_id,
        success=success,
        videos=videos or [],
        publish_results=publish_results or [],
    )
    news_diagnostics.record_event(
        task_id,
        "news_history_finalized",
        success=success,
        status="completed" if success else "failed",
        reason=reason,
        video_count=len(videos or []),
        publish_count=len(publish_results or []),
    )


def _fail_news_task(task_id: str, params: VideoParams, reason: str) -> None:
    _mark_news_story_result(task_id, params, success=False, reason=reason)
    news_diagnostics.record_event(task_id, "news_task_failed", reason=reason)


def _social_publish_preflight(params: VideoParams) -> tuple[dict, PublishPrivacy]:
    auto_publish = (
        params.social_auto_publish
        if params.social_auto_publish is not None
        else config.app.get("social_auto_publish", False)
    )
    requested_platforms = (
        platform_values(params.social_platforms)
        if params.social_platforms
        else [str(platform).lower() for platform in config.app.get("social_platforms", [])]
    )
    try:
        privacy = params.social_privacy or PublishPrivacy(
            config.app.get("social_privacy", "private")
        )
    except ValueError:
        logger.warning("invalid social_privacy config, falling back to private")
        privacy = PublishPrivacy.private

    summary = {
        "auto_publish": bool(auto_publish),
        "requested_platforms": requested_platforms,
        "enabled_platforms": [],
        "skipped_platforms": [],
        "privacy": privacy.value,
    }
    if not auto_publish:
        summary["skip_reason"] = "auto_publish_disabled"
        return summary, privacy
    if not requested_platforms:
        summary["skip_reason"] = "no_requested_platforms"
        return summary, privacy

    for platform in requested_platforms:
        if platform == "youtube" and not youtube_oauth.is_configured():
            summary["skipped_platforms"].append(
                {"platform": platform, "reason": "youtube_not_connected"}
            )
            continue
        if platform == "tiktok":
            tiktok_mode = str(config.app.get("tiktok_publish_mode", "api"))
            if tiktok_mode == "browser_assist":
                if not config.app.get("tiktok_browser_upload_enabled", False):
                    summary["skipped_platforms"].append(
                        {
                            "platform": platform,
                            "reason": "tiktok_browser_upload_disabled",
                        }
                    )
                    continue
                summary.setdefault("manual_review_platforms", []).append(platform)
            else:
                if not config.app.get("tiktok_upload_enabled", False):
                    summary["skipped_platforms"].append(
                        {"platform": platform, "reason": "tiktok_upload_disabled"}
                    )
                    continue
                if not params.tiktok_direct_post_consent:
                    summary["skipped_platforms"].append(
                        {
                            "platform": platform,
                            "reason": "tiktok_direct_post_consent_missing",
                        }
                    )
                    continue
        summary["enabled_platforms"].append(platform)

    if not summary["enabled_platforms"]:
        summary["skip_reason"] = "no_enabled_platforms"
    return summary, privacy


def _social_publish_status(publish_preflight: dict, publish_results: list[dict]) -> dict:
    publish_preflight = publish_preflight or {}
    publish_results = publish_results or []
    enabled_platforms = publish_preflight.get("enabled_platforms") or []
    requested_platforms = publish_preflight.get("requested_platforms") or []
    success_count = len([item for item in publish_results if item.get("success")])
    failed_count = len([item for item in publish_results if not item.get("success")])
    result_count = len(publish_results)

    if not publish_preflight.get("auto_publish"):
        status = "skipped"
        reason = publish_preflight.get("skip_reason", "auto_publish_disabled")
    elif not enabled_platforms:
        status = "blocked"
        reason = publish_preflight.get("skip_reason", "no_enabled_platforms")
    elif result_count == 0:
        status = "not_attempted"
        reason = "no_publish_results"
    elif success_count == result_count:
        status = "uploaded"
        reason = ""
    elif success_count > 0:
        status = "partial"
        reason = "some_platforms_failed"
    else:
        status = "failed"
        reason = "all_platforms_failed"

    return {
        "status": status,
        "reason": reason,
        "requested_platforms": requested_platforms,
        "enabled_platforms": enabled_platforms,
        "result_count": result_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "skipped_platforms": publish_preflight.get("skipped_platforms") or [],
        "privacy": publish_preflight.get("privacy", ""),
    }


def _prepare_news_concat_mode(task_id: str, params: VideoParams, material_count: int) -> None:
    if type(params.video_concat_mode) is str:
        params.video_concat_mode = VideoConcatMode(params.video_concat_mode)
    if params.video_source == "news" and config.app.get("news_preserve_media_order", True):
        params.video_concat_mode = VideoConcatMode.sequential
        news_diagnostics.record_event(
            task_id,
            "news_media_order_preserved",
            reason="news_source_media_before_stock",
            material_count=material_count,
        )


def start(task_id, params: VideoParams, stop_at: str = "video"):
    logger.info(f"start task: {task_id}, stop_at: {stop_at}")
    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=5)

    if params.video_source == "news":
        news_story = news_pipeline.prepare_news_context(params)
        if not news_story:
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            logger.error("failed to find a news story for the requested query")
            _fail_news_task(task_id, params, "news_story_not_found")
            return

    # 1. Generate script
    video_script = generate_script(task_id, params)
    if not video_script or "Error: " in video_script:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        _fail_news_task(task_id, params, "script_generation_failed")
        return

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=10)

    if stop_at == "script":
        sm.state.update_task(
            task_id, state=const.TASK_STATE_COMPLETE, progress=100, script=video_script
        )
        return {"script": video_script}

    # 2. Generate terms
    video_terms = ""
    if params.video_source != "local":
        video_terms = generate_terms(task_id, params, video_script)
        if not video_terms:
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            _fail_news_task(task_id, params, "terms_generation_failed")
            return

    save_script_data(task_id, video_script, video_terms, params)

    if stop_at == "terms":
        sm.state.update_task(
            task_id, state=const.TASK_STATE_COMPLETE, progress=100, terms=video_terms
        )
        return {"script": video_script, "terms": video_terms}

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=20)

    # 3. Generate audio
    audio_file, audio_duration, sub_maker = generate_audio(
        task_id, params, video_script
    )
    if not audio_file:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        _fail_news_task(task_id, params, "audio_generation_failed")
        return

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=30)

    if stop_at == "audio":
        sm.state.update_task(
            task_id,
            state=const.TASK_STATE_COMPLETE,
            progress=100,
            audio_file=audio_file,
        )
        return {"audio_file": audio_file, "audio_duration": audio_duration}

    # 4. Generate subtitle
    subtitle_path = generate_subtitle(
        task_id, params, video_script, sub_maker, audio_file
    )

    if stop_at == "subtitle":
        sm.state.update_task(
            task_id,
            state=const.TASK_STATE_COMPLETE,
            progress=100,
            subtitle_path=subtitle_path,
        )
        return {"subtitle_path": subtitle_path}

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=40)

    # 5. Get video materials
    downloaded_videos = get_video_materials(
        task_id, params, video_terms, audio_duration
    )
    if not downloaded_videos:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        _fail_news_task(task_id, params, "video_materials_failed")
        return

    if stop_at == "materials":
        news_media_summary = news_diagnostics.get_media_summary(task_id)
        sm.state.update_task(
            task_id,
            state=const.TASK_STATE_COMPLETE,
            progress=100,
            materials=downloaded_videos,
            news_media_summary=news_media_summary,
        )
        return {"materials": downloaded_videos, "news_media_summary": news_media_summary}

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=50)

    # 仅完整视频生成流程才需要处理视频拼接模式；
    # 这样可以避免 /subtitle 和 /audio 这类请求访问不存在的字段。
    _prepare_news_concat_mode(task_id, params, len(downloaded_videos))

    # 6. Generate final videos
    final_video_paths, combined_video_paths = generate_final_videos(
        task_id, params, downloaded_videos, audio_file, subtitle_path
    )

    if not final_video_paths:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        _fail_news_task(task_id, params, "final_video_generation_failed")
        return

    logger.success(
        f"task {task_id} finished, generated {len(final_video_paths)} videos."
    )

    # 7. Generate social metadata and publish if enabled.
    social_default_title = (
        (params.news_source_context or {}).get("title")
        if params.news_source_context
        else ""
    ) or params.video_subject
    generated_social_metadata = social_metadata.generate_social_metadata(
        video_subject=params.video_subject,
        video_script=video_script,
        video_terms=video_terms,
        platforms=platform_values(params.social_platforms) if params.social_platforms else config.app.get(
            "social_platforms", []
        ),
        language=params.video_language,
        trend_context=params.trend_context,
        source_context=params.news_source_context,
        default_title=social_default_title,
    )
    if params.social_metadata:
        generated_social_metadata = social_metadata.normalize_metadata(
            params.social_metadata, default_title=social_default_title
        )
    news_diagnostics.record_event(
        task_id,
        "social_metadata_ready",
        title=generated_social_metadata.title,
        default_title=social_default_title,
        hashtag_count=len(generated_social_metadata.hashtags),
        youtube_tag_count=len(generated_social_metadata.youtube_tags),
        has_tiktok_caption=bool(generated_social_metadata.platform_captions.get("tiktok")),
    )
    publish_results = []
    publish_preflight, privacy = _social_publish_preflight(params)
    news_diagnostics.record_event(
        task_id,
        "social_publish_preflight",
        **publish_preflight,
    )
    if not publish_preflight["auto_publish"]:
        news_diagnostics.record_event(
            task_id,
            "social_publish_skipped",
            reason="auto_publish_disabled",
            requested_platforms=publish_preflight["requested_platforms"],
        )
    elif not publish_preflight["enabled_platforms"]:
        logger.warning("No enabled social platforms available for auto-publish")
        news_diagnostics.record_event(
            task_id,
            "social_publish_skipped",
            reason=publish_preflight.get("skip_reason", "no_enabled_platforms"),
            requested_platforms=publish_preflight["requested_platforms"],
            skipped_platforms=publish_preflight["skipped_platforms"],
        )
    else:
        logger.info("\n\n## publishing videos to configured social platforms")
        platforms = publish_preflight["enabled_platforms"]
        for video_path in final_video_paths:
            for result in social_publisher.publish_video(
                video_path=video_path,
                metadata=generated_social_metadata,
                platforms=platforms,
                privacy=privacy,
            ):
                result["video_path"] = video_path
                publish_results.append(result)
                if result.get("success"):
                    logger.info(f"Published to {result.get('platform')}: {video_path}")
                else:
                    logger.warning(
                        f"Failed to publish to {result.get('platform')}: "
                        f"{result.get('error', 'Unknown error')}"
                    )
        news_diagnostics.record_event(
            task_id,
            "social_publish_completed",
            requested_platforms=publish_preflight["requested_platforms"],
            enabled_platforms=platforms,
            skipped_platforms=publish_preflight["skipped_platforms"],
            result_count=len(publish_results),
            success_count=len([item for item in publish_results if item.get("success")]),
            failed_count=len([item for item in publish_results if not item.get("success")]),
            results=publish_results,
        )

    publish_status = _social_publish_status(publish_preflight, publish_results)
    news_diagnostics.record_event(
        task_id,
        "social_publish_status",
        **publish_status,
    )

    _mark_news_story_result(
        task_id,
        params,
        success=True,
        videos=final_video_paths,
        publish_results=publish_results,
        reason="completed",
    )
    news_media_summary = news_diagnostics.get_media_summary(task_id)

    kwargs = {
        "videos": final_video_paths,
        "combined_videos": combined_video_paths,
        "script": video_script,
        "terms": video_terms,
        "audio_file": audio_file,
        "audio_duration": audio_duration,
        "subtitle_path": subtitle_path,
        "materials": downloaded_videos,
        "news_media_summary": news_media_summary,
        "publish_preflight": publish_preflight,
        "publish_status": publish_status,
        "social_metadata": generated_social_metadata.model_dump(),
        "publish_results": publish_results if publish_results else None,
        "cross_post_results": publish_results if publish_results else None,
    }
    sm.state.update_task(
        task_id, state=const.TASK_STATE_COMPLETE, progress=100, **kwargs
    )
    return kwargs


if __name__ == "__main__":
    task_id = "task_id"
    params = VideoParams(
        video_subject="金钱的作用",
        voice_name="zh-CN-XiaoyiNeural-Female",
        voice_rate=1.0,
    )
    start(task_id, params, stop_at="video")
