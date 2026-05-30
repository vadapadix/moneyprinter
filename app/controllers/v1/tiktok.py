from fastapi import Query
from fastapi.responses import HTMLResponse, RedirectResponse

from app.controllers.v1.base import new_router
from app.services import tiktok_oauth
from app.utils import utils

router = new_router()


@router.get("/tiktok/oauth/start", summary="Start TikTok OAuth")
def start_oauth():
    authorize_url, state = tiktok_oauth.build_authorize_url()
    if not authorize_url or "client_key=&" in authorize_url or "redirect_uri=&" in authorize_url:
        return utils.get_response(
            400,
            {
                "error": "TikTok OAuth is not configured",
                "required_config": [
                    "public_base_url",
                    "tiktok_client_key",
                    "tiktok_client_secret",
                    "tiktok_redirect_uri",
                ],
            },
        )
    return RedirectResponse(authorize_url)


@router.get(
    "/tiktok/oauth/callback",
    response_class=HTMLResponse,
    summary="TikTok OAuth callback",
)
def oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    if error:
        return HTMLResponse(
            f"<h1>TikTok connection failed</h1><p>{error}: {error_description or ''}</p>",
            status_code=400,
        )
    if not code:
        return HTMLResponse("<h1>TikTok connection failed</h1><p>Missing code.</p>", status_code=400)

    result = tiktok_oauth.exchange_code_for_token(code)
    if not result.get("success"):
        return HTMLResponse(
            f"<h1>TikTok connection failed</h1><pre>{utils.to_json(result)}</pre>",
            status_code=400,
        )

    return HTMLResponse(
        """
        <h1>TikTok connected</h1>
        <p>Access token was saved to config.toml. You can close this page.</p>
        """.strip()
    )
