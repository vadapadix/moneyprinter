import time

import requests
from loguru import logger

from app.config import config

TOKEN_URL = "https://oauth2.googleapis.com/token"


def refresh_access_token() -> dict:
    client_id = config.app.get("youtube_client_id", "").strip()
    client_secret = config.app.get("youtube_client_secret", "").strip()
    refresh_token = config.app.get("youtube_refresh_token", "").strip()
    if not client_id or not client_secret or not refresh_token:
        return {"success": False, "error": "YouTube refresh token is not configured."}

    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.RequestException as exc:
        logger.error(f"YouTube OAuth refresh failed: {str(exc)}")
        return {"success": False, "error": str(exc)}

    access_token = payload.get("access_token", "")
    if access_token:
        config.app["youtube_access_token"] = access_token
        config.app["youtube_token_expires_at"] = int(time.time()) + int(
            payload.get("expires_in") or 0
        )
        config.app["youtube_upload_enabled"] = True
        config.save_config()

    return {
        "success": bool(access_token),
        "access_token_saved": bool(access_token),
        "expires_in": payload.get("expires_in"),
        "scope": payload.get("scope", ""),
    }


def get_valid_access_token() -> str:
    access_token = config.app.get("youtube_access_token", "").strip()
    expires_at = int(config.app.get("youtube_token_expires_at") or 0)
    if access_token and (not expires_at or expires_at - int(time.time()) > 300):
        return access_token

    refreshed = refresh_access_token()
    if refreshed.get("success"):
        return config.app.get("youtube_access_token", "").strip()
    return access_token


def is_configured() -> bool:
    if config.app.get("youtube_access_token", "").strip():
        return True
    return bool(
        config.app.get("youtube_refresh_token", "").strip()
        and config.app.get("youtube_client_id", "").strip()
        and config.app.get("youtube_client_secret", "").strip()
    )
