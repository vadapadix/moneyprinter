import os
from math import floor

import requests
from loguru import logger

from app.config import config
from app.models.schema import PublishPrivacy, SocialMetadata
from app.services import tiktok_oauth
from app.services.publishers.base import PublishResult, Publisher


class TikTokPublisher(Publisher):
    platform = "tiktok"
    INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"

    def __init__(self):
        self.enabled = config.app.get("tiktok_upload_enabled", False)
        self.access_token = tiktok_oauth.get_valid_access_token()
        self.chunk_size = int(config.app.get("tiktok_chunk_size", 10_000_000))
        self.disable_duet = bool(config.app.get("tiktok_disable_duet", False))
        self.disable_comment = bool(config.app.get("tiktok_disable_comment", False))
        self.disable_stitch = bool(config.app.get("tiktok_disable_stitch", False))

    def is_configured(self) -> bool:
        return bool(self.enabled and self.access_token)

    def query_creator_info(self) -> dict:
        if not self.is_configured():
            return {
                "success": False,
                "error": "TikTok upload is not configured",
                "data": {},
            }

        try:
            response = requests.post(
                self.CREATOR_INFO_URL,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as exc:
            logger.error(f"TikTok creator info query failed: {str(exc)}")
            return {"success": False, "error": str(exc), "data": {}}

        error = payload.get("error", {})
        if error.get("code") not in ("ok", None):
            return {
                "success": False,
                "error": error.get("message", "TikTok creator info query failed"),
                "raw": payload,
                "data": {},
            }
        return {"success": True, "data": payload.get("data", {}), "raw": payload}

    @staticmethod
    def _privacy_level(privacy: PublishPrivacy) -> str:
        if privacy == PublishPrivacy.public:
            return "PUBLIC_TO_EVERYONE"
        if privacy == PublishPrivacy.private or privacy == PublishPrivacy.draft:
            return "SELF_ONLY"
        return "SELF_ONLY"

    def _caption(self, metadata: SocialMetadata) -> str:
        caption = metadata.platform_captions.get(self.platform) or metadata.description
        if metadata.hashtags:
            caption = f"{caption}\n\n{' '.join(metadata.hashtags)}"
        return caption[:2200]

    def _source_info(self, video_size: int) -> dict:
        if video_size <= 0:
            return {
                "source": "FILE_UPLOAD",
                "video_size": 0,
                "chunk_size": 0,
                "total_chunk_count": 0,
            }
        
        # TikTok API constraints
        MIN_CHUNK_SIZE = 5_000_000  # 5MB
        MAX_CHUNK_SIZE = 64_000_000  # 64MB
        MAX_TOTAL_CHUNKS = 1000  # Maximum number of chunks TikTok allows
        
        if video_size <= MAX_CHUNK_SIZE:
            # TikTok is strict for single-chunk uploads: send the whole file as
            # one chunk and make source_info.chunk_size equal to video_size.
            chunk_size = video_size
            total_chunk_count = 1
        else:
            # Calculate chunk size ensuring we don't exceed max chunks
            chunk_size = max(MIN_CHUNK_SIZE, min(self.chunk_size, MAX_CHUNK_SIZE, video_size))
            total_chunk_count = max(1, min(MAX_TOTAL_CHUNKS, floor(video_size / chunk_size)))
            
        return {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunk_count,
        }

    @staticmethod
    def _read_chunks(video_file, video_size: int, chunk_size: int, total_chunk_count: int):
        start = 0
        logger.info(f"Starting chunk upload - Total chunks: {total_chunk_count}, Chunk size: {chunk_size}")
        
        for chunk_index in range(total_chunk_count):
            read_size = chunk_size
            if chunk_index == total_chunk_count - 1:
                read_size = video_size - start
            
            data = video_file.read(read_size)
            if not data:
                logger.warning(f"Chunk {chunk_index}: No data read, ending upload")
                break
                
            end = start + len(data) - 1
            logger.debug(f"Chunk {chunk_index + 1}/{total_chunk_count}: Bytes {start}-{end} ({len(data)} bytes)")
            yield start, end, data
            start = end + 1

    def publish(
        self,
        video_path: str,
        metadata: SocialMetadata,
        privacy: PublishPrivacy = PublishPrivacy.private,
    ) -> PublishResult:
        if not self.is_configured():
            return PublishResult(
                platform=self.platform,
                success=False,
                status="disabled",
                error="TikTok upload is not configured",
            )

        if not os.path.exists(video_path):
            return PublishResult(
                platform=self.platform,
                success=False,
                status="failed",
                error=f"Video file not found: {video_path}",
            )

        video_size = os.path.getsize(video_path)
        source_info = self._source_info(video_size)
        logger.info(f"TikTok upload - Video size: {video_size}, Chunk size: {source_info['chunk_size']}, Total chunks: {source_info['total_chunk_count']}")
        
        # Validate source_info before making API call
        if source_info['total_chunk_count'] <= 0:
            return PublishResult(
                platform=self.platform,
                success=False,
                status="failed",
                error="Invalid chunk count calculated",
            )
        
        if source_info['chunk_size'] <= 0:
            return PublishResult(
                platform=self.platform,
                success=False,
                status="failed",
                error="Invalid chunk size calculated",
            )
        
        # Verify chunk calculation math
        calculated_size = source_info['chunk_size'] * source_info['total_chunk_count']
        if calculated_size < video_size:
            logger.warning(f"Chunk calculation mismatch: {calculated_size} < {video_size}")
            # This might be acceptable for the last chunk, but let's log it
        elif calculated_size > video_size + source_info['chunk_size']:
            logger.error(f"Chunk calculation error: {calculated_size} > {video_size} + {source_info['chunk_size']}")
            return PublishResult(
                platform=self.platform,
                success=False,
                status="failed",
                error="Chunk calculation error detected",
            )
        
        payload = {
            "post_info": {
                "title": self._caption(metadata),
                "privacy_level": self._privacy_level(privacy or PublishPrivacy.private),
                "disable_duet": self.disable_duet,
                "disable_comment": self.disable_comment,
                "disable_stitch": self.disable_stitch,
                "brand_content_toggle": False,
                "brand_organic_toggle": False,
                "is_aigc": metadata.contains_synthetic_media,
            },
            "source_info": source_info,
        }

        try:
            init_response = requests.post(
                self.INIT_URL,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                },
                json=payload,
                timeout=60,
            )
            init_response.raise_for_status()
            init_payload = init_response.json()
            error = init_payload.get("error", {})
            if error.get("code") not in ("ok", None):
                return PublishResult(
                    platform=self.platform,
                    success=False,
                    status="failed",
                    error=error.get("message", "TikTok init failed"),
                    raw=init_payload,
                )

            data = init_payload.get("data", {})
            upload_url = data.get("upload_url")
            publish_id = data.get("publish_id", "")
            if not upload_url:
                return PublishResult(
                    platform=self.platform,
                    success=False,
                    status="failed",
                    post_id=publish_id,
                    error="TikTok did not return an upload_url",
                    raw=init_payload,
                )

            with open(video_path, "rb") as video_file:
                for start, end, chunk in self._read_chunks(
                    video_file,
                    video_size,
                    source_info["chunk_size"],
                    source_info["total_chunk_count"],
                ):
                    upload_response = requests.put(
                        upload_url,
                        data=chunk,
                        headers={
                            "Content-Type": "video/mp4",
                            "Content-Length": str(len(chunk)),
                            "Content-Range": f"bytes {start}-{end}/{video_size}",
                        },
                        timeout=300,
                    )
                    upload_response.raise_for_status()
            return PublishResult(
                platform=self.platform,
                success=True,
                status="processing",
                post_id=publish_id,
                raw=init_payload,
            )
        except requests.exceptions.HTTPError as exc:
            response_text = ""
            if exc.response is not None:
                response_text = exc.response.text[:2000]
            logger.error(f"TikTok upload failed: {str(exc)} {response_text}")
            error = str(exc)
            if response_text:
                error = f"{error}; response={response_text}"
            if "unaudited_client_can_only_post_to_private_accounts" in response_text:
                error = (
                    "TikTok rejected the upload because this app is not audited yet. "
                    "Until TikTok approves the Content Posting API review, the connected "
                    "TikTok account itself must be set to Private, and posts can only use "
                    "SELF_ONLY visibility. "
                    f"Raw error: {error}"
                )
            return PublishResult(
                platform=self.platform,
                success=False,
                status="failed",
                error=error,
            )
        except requests.exceptions.RequestException as exc:
            logger.error(f"TikTok upload failed: {str(exc)}")
            return PublishResult(
                platform=self.platform,
                success=False,
                status="failed",
                error=str(exc),
            )
