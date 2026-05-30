"""Application implementation - ASGI."""

import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.config import config
from app.models.exception import HttpException
from app.router import root_api_router
from app.utils import utils


def exception_handler(request: Request, e: HttpException):
    return JSONResponse(
        status_code=e.status_code,
        content=utils.get_response(e.status_code, e.data, e.message),
    )


def validation_exception_handler(request: Request, e: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content=utils.get_response(
            status=400, data=e.errors(), message="field required"
        ),
    )


def get_application() -> FastAPI:
    """Initialize FastAPI application.

    Returns:
       FastAPI: Application object instance.

    """
    instance = FastAPI(
        title=config.project_name,
        description=config.project_description,
        version=config.project_version,
        debug=False,
    )
    instance.include_router(root_api_router)
    instance.add_exception_handler(HttpException, exception_handler)
    instance.add_exception_handler(RequestValidationError, validation_exception_handler)
    return instance


app = get_application()

# Configures the CORS middleware for the FastAPI app
cors_allowed_origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "")
origins = cors_allowed_origins_str.split(",") if cors_allowed_origins_str else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

task_dir = utils.task_dir()
app.mount(
    "/tasks", StaticFiles(directory=task_dir, html=True, follow_symlink=True), name=""
)

public_dir = utils.public_dir()
app.mount("/", StaticFiles(directory=public_dir, html=True), name="")


@app.on_event("shutdown")
def shutdown_event():
    logger.info("shutdown event")


@app.on_event("startup")
def startup_event():
    logger.info("startup event")


@app.get("/terms", response_class=HTMLResponse)
def terms_page():
    return """
    <!doctype html>
    <html lang="en">
      <head><meta charset="utf-8"><title>Terms of Service</title></head>
      <body>
        <main style="max-width: 760px; margin: 40px auto; font-family: Arial, sans-serif; line-height: 1.6;">
          <h1>Terms of Service</h1>
          <p>MoneyPrinterTurbo is a local automation tool for creating short videos and publishing them to connected social accounts.</p>
          <p>Users are responsible for the topics, media, captions, hashtags, and publishing settings they choose. Users must only publish content they have the right to use and must follow the rules of each connected platform.</p>
          <p>The service does not sell user data and does not publish to social platforms unless the user connects an account and enables publishing.</p>
          <p>Contact: support@example.com</p>
        </main>
      </body>
    </html>
    """


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page():
    return """
    <!doctype html>
    <html lang="en">
      <head><meta charset="utf-8"><title>Privacy Policy</title></head>
      <body>
        <main style="max-width: 760px; margin: 40px auto; font-family: Arial, sans-serif; line-height: 1.6;">
          <h1>Privacy Policy</h1>
          <p>MoneyPrinterTurbo stores configuration and generated task data locally on the user's machine unless the user deploys it elsewhere.</p>
          <p>When a user connects TikTok or YouTube, OAuth tokens may be stored in the local config file so the app can publish videos on behalf of the authorized user.</p>
          <p>The app uses connected platform APIs only for the features the user enables, such as uploading videos and reading trend data. The app does not sell personal data.</p>
          <p>Users can revoke platform access from their TikTok or Google account settings and remove tokens from config.toml at any time.</p>
          <p>Contact: support@example.com</p>
        </main>
      </body>
    </html>
    """


@app.get("/tiktok/connect", response_class=HTMLResponse)
def tiktok_connect_page():
    return """
    <!doctype html>
    <html lang="en">
      <head><meta charset="utf-8"><title>Connect TikTok</title></head>
      <body>
        <main style="max-width: 760px; margin: 40px auto; font-family: Arial, sans-serif; line-height: 1.6;">
          <h1>Connect TikTok</h1>
          <p>Use this page in your TikTok review demo to show the user starting TikTok Login Kit authorization.</p>
          <p><a href="/api/v1/tiktok/oauth/start">Continue with TikTok</a></p>
        </main>
      </body>
    </html>
    """
