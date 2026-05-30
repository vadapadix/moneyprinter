import secrets
import time
from urllib.parse import urlencode

import requests
from loguru import logger

from app.config import config

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


def get_public_base_url() -> str:
    base_url = config.app.get("public_base_url", "").strip()
    if base_url:
        return base_url.rstrip("/")
    endpoint = config.app.get("endpoint", "").strip()
    return endpoint.rstrip("/")


def get_redirect_uri() -> str:
    configured = config.app.get("tiktok_redirect_uri", "").strip()
    if configured:
        return configured
    base_url = get_public_base_url()
    if not base_url:
        return ""
    return f"{base_url}/api/v1/tiktok/oauth/callback"


def build_authorize_url() -> tuple[str, str]:
    client_key = config.app.get("tiktok_client_key", "").strip()
    redirect_uri = get_redirect_uri()
    state = secrets.token_urlsafe(24)
    scopes = config.app.get("tiktok_scopes", ["user.info.basic", "video.publish"])
    if isinstance(scopes, str):
        scopes = [scope.strip() for scope in scopes.split(",") if scope.strip()]

    params = {
        "client_key": client_key,
        "scope": ",".join(scopes),
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}", state


def exchange_code_for_token(code: str) -> dict:
    client_key = config.app.get("tiktok_client_key", "").strip()
    client_secret = config.app.get("tiktok_client_secret", "").strip()
    redirect_uri = get_redirect_uri()
    if not client_key or not client_secret or not redirect_uri:
        return {
            "success": False,
            "error": "TikTok OAuth is not configured. Set public_base_url, tiktok_client_key, and tiktok_client_secret.",
        }

    try:
        response = requests.post(
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": client_key,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.RequestException as exc:
        logger.error(f"TikTok OAuth token exchange failed: {str(exc)}")
        return {"success": False, "error": str(exc)}

    error = payload.get("error")
    if error:
        return {"success": False, "error": error, "raw": payload}

    access_token = payload.get("access_token", "")
    refresh_token = payload.get("refresh_token", "")
    if access_token:
        config.app["tiktok_access_token"] = access_token
        config.app["tiktok_refresh_token"] = refresh_token
        config.app["tiktok_token_expires_at"] = int(time.time()) + int(
            payload.get("expires_in") or 0
        )
        config.app["tiktok_refresh_expires_at"] = int(time.time()) + int(
            payload.get("refresh_expires_in") or 0
        )
        config.app["tiktok_upload_enabled"] = True
        config.save_config()

    return {
        "success": bool(access_token),
        "access_token_saved": bool(access_token),
        "refresh_token_saved": bool(refresh_token),
        "scope": payload.get("scope", ""),
        "expires_in": payload.get("expires_in"),
        "open_id": payload.get("open_id", ""),
    }


def refresh_access_token() -> dict:
    client_key = config.app.get("tiktok_client_key", "").strip()
    client_secret = config.app.get("tiktok_client_secret", "").strip()
    refresh_token = config.app.get("tiktok_refresh_token", "").strip()
    if not client_key or not client_secret or not refresh_token:
        return {"success": False, "error": "TikTok refresh token is not configured."}

    try:
        response = requests.post(
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": client_key,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.RequestException as exc:
        logger.error(f"TikTok OAuth refresh failed: {str(exc)}")
        return {"success": False, "error": str(exc)}

    error = payload.get("error")
    if error:
        return {"success": False, "error": error, "raw": payload}

    access_token = payload.get("access_token", "")
    new_refresh_token = payload.get("refresh_token", "")
    if access_token:
        now = int(time.time())
        config.app["tiktok_access_token"] = access_token
        if new_refresh_token:
            config.app["tiktok_refresh_token"] = new_refresh_token
        config.app["tiktok_token_expires_at"] = now + int(payload.get("expires_in") or 0)
        config.app["tiktok_refresh_expires_at"] = now + int(
            payload.get("refresh_expires_in") or 0
        )
        config.app["tiktok_upload_enabled"] = True
        config.save_config()

    return {
        "success": bool(access_token),
        "access_token_saved": bool(access_token),
        "refresh_token_saved": bool(new_refresh_token),
        "scope": payload.get("scope", ""),
        "expires_in": payload.get("expires_in"),
        "open_id": payload.get("open_id", ""),
    }


def get_valid_access_token() -> str:
    access_token = config.app.get("tiktok_access_token", "").strip()
    expires_at = int(config.app.get("tiktok_token_expires_at") or 0)
    if access_token and (not expires_at or expires_at - int(time.time()) > 300):
        return access_token

    refreshed = refresh_access_token()
    if refreshed.get("success"):
        return config.app.get("tiktok_access_token", "").strip()
    return access_token
