import os
import sys
import webbrowser
from uuid import UUID, uuid4

import streamlit as st
from loguru import logger

# Add the root directory of the project to the system path to allow importing modules from the project
root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)
    print("******** sys.path ********")
    print(sys.path)
    print("")

from app.config import config
from app.models.schema import (
    MaterialInfo,
    NewsAutomationRunRequest,
    PublishPrivacy,
    SocialMetadata,
    SocialPlatform,
    VideoAspect,
    VideoConcatMode,
    VideoParams,
    VideoTransitionMode,
)
from app.services import automation as automation_service
from app.services import news_analytics
from app.services import news_diagnostics
from app.services import news_history
from app.services import llm, voice
from app.services import social_publisher
from app.services import task as tm
from app.services import upload_tests
from app.services import youtube_oauth
from app.services.publishers.tiktok import TikTokPublisher
from app.services.publishers.youtube import YouTubeShortsPublisher
from app.utils import utils

# Helper functions for test upload
def get_base_url():
    """Get the local API URL for Streamlit-to-FastAPI calls."""
    endpoint = config.app.get("endpoint", "").rstrip("/")
    if endpoint:
        return endpoint
    return f"http://127.0.0.1:{config.listen_port}"

def get_api_key():
    """Get API key for authentication (if needed)"""
    # This is a placeholder - implement actual authentication if required
    return ""  # Add your authentication logic here


def get_social_privacy_setting() -> PublishPrivacy:
    try:
        return PublishPrivacy(config.app.get("social_privacy", "private"))
    except ValueError:
        return PublishPrivacy.private


def run_test_upload_inline(uploaded_file, platform: str) -> dict:
    """Run upload tests directly from Streamlit without requiring FastAPI."""
    request_id = utils.get_uuid()
    temp_dir = utils.storage_dir("temp", create=True)
    safe_name = os.path.basename(uploaded_file.name or "upload-test.mp4")
    temp_file_path = os.path.join(temp_dir, f"test_upload_{request_id}_{safe_name}")
    try:
        with open(temp_file_path, "wb") as handle:
            handle.write(uploaded_file.getbuffer())
        return upload_tests.run_upload_test(
            video_path=temp_file_path,
            platform=platform,
            request_id=request_id,
        )
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


class _InlineUploadResponse:
    def __init__(self, status_code: int, data: dict | None = None, error: str = ""):
        self.status_code = status_code
        self._data = data or {}
        self.text = error or utils.to_json(self._data)

    def json(self):
        return {"status": self.status_code, "data": self._data}


class _InlineUploadRequests:
    @staticmethod
    def post(url: str, files=None, **kwargs):
        if "/api/v1/test-upload" not in str(url):
            return _InlineUploadResponse(404, error=f"Unsupported inline request: {url}")
        platform = "tiktok"
        if "platform=youtube" in str(url):
            platform = "youtube"
        elif "platform=both" in str(url):
            platform = "both"
        uploaded_file = (files or {}).get("file")
        if uploaded_file is None:
            return _InlineUploadResponse(400, error="No upload file provided")
        try:
            return _InlineUploadResponse(
                200,
                data=run_test_upload_inline(uploaded_file, platform),
            )
        except Exception as exc:
            return _InlineUploadResponse(500, error=str(exc))


requests = _InlineUploadRequests()


def _store_action_result(key: str, level: str, message: str, data: dict | None = None):
    st.session_state[f"{key}_result"] = {
        "level": level,
        "message": message,
        "data": data or {},
    }


def _render_action_result(key: str):
    result = st.session_state.get(f"{key}_result")
    if not result:
        return

    level = result.get("level", "info")
    message = result.get("message", "")
    if level == "success":
        st.success(message)
    elif level == "warning":
        st.warning(message)
    elif level == "error":
        st.error(message)
    else:
        st.info(message)

    data = result.get("data") or {}
    if data:
        st.json(data)


def render_test_upload_action(uploaded_file, platform: str, label: str, key: str):
    if uploaded_file is None:
        _render_action_result(key)
        return

    if st.button(label, key=key):
        try:
            with st.spinner(f"Running {label}..."):
                response = requests.post(
                    f"{get_base_url()}/api/v1/test-upload?platform={platform}",
                    files={"file": uploaded_file},
                )

            if response.status_code == 200:
                payload = response.json().get("data", {})
                _store_action_result(key, "success", f"{label} completed.", payload)
            else:
                _store_action_result(
                    key,
                    "error",
                    f"{label} failed: {response.text}",
                )
        except Exception as exc:
            _store_action_result(key, "error", f"{label} failed: {str(exc)}")

    _render_action_result(key)


def run_news_automation_inline(request: NewsAutomationRunRequest) -> dict:
    """Run news automation from Streamlit without requiring the FastAPI server."""
    prepared = automation_service.prepare_news_run(request)
    tasks = prepared.get("tasks", [])
    results = []

    for task_info in tasks:
        task_id = task_info["task_id"]
        story = task_info["story"]
        task_params = task_info["params"]
        with st.spinner(f"Generating news video: {story.title}"):
            result = tm.start(task_id=task_id, params=task_params)
        publish_results = result.get("publish_results") if result else []
        publish_preflight = result.get("publish_preflight") if result else None
        videos = result.get("videos", []) if result else []
        media_summary = (
            result.get("news_media_summary") if result else None
        ) or news_diagnostics.get_media_summary(task_id)
        news_history.mark_story_result(
            story=story,
            task_id=task_id,
            success=bool(videos),
            videos=videos,
            publish_results=publish_results or [],
        )
        results.append(
            {
                "task_id": task_id,
                "story": story.model_dump(),
                "success": bool(videos),
                "videos": videos,
                "publish_preflight": publish_preflight,
                "publish_results": publish_results or [],
                "news_media_summary": media_summary,
                "diagnostics": news_diagnostics.get_task_diagnostics(task_id),
            }
        )

    return {
        "run_id": prepared.get("run_id"),
        "queued_count": len(tasks),
        "ranked_story_count": len(prepared.get("ranked_stories", [])),
        "analytics": news_analytics.summarize_news_items(results),
        "results": results,
    }

st.set_page_config(
    page_title="MoneyPrinterTurbo",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        "Report a bug": "https://github.com/harry0703/MoneyPrinterTurbo/issues",
        "About": "# MoneyPrinterTurbo\nSimply provide a topic or keyword for a video, and it will "
        "automatically generate the video copy, video materials, video subtitles, "
        "and video background music before synthesizing a high-definition short "
        "video.\n\nhttps://github.com/harry0703/MoneyPrinterTurbo",
    },
)


streamlit_style = """
<style>
h1 {
    padding-top: 0 !important;
}
</style>
"""
st.markdown(streamlit_style, unsafe_allow_html=True)

# 定义资源目录
font_dir = os.path.join(root_dir, "resource", "fonts")
song_dir = os.path.join(root_dir, "resource", "songs")
i18n_dir = os.path.join(root_dir, "webui", "i18n")
config_file = os.path.join(root_dir, "webui", ".streamlit", "webui.toml")
system_locale = utils.get_system_locale()


if "video_subject" not in st.session_state:
    st.session_state["video_subject"] = ""
if "video_script" not in st.session_state:
    st.session_state["video_script"] = ""
if "video_terms" not in st.session_state:
    st.session_state["video_terms"] = ""
if "ui_language" not in st.session_state:
    st.session_state["ui_language"] = config.ui.get("language", system_locale)
if "local_video_materials" not in st.session_state:
    # 记住用户最近一次已经落盘的本地素材，避免仅修改文案后二次生成时丢失素材列表。
    st.session_state["local_video_materials"] = []

# 加载语言文件
locales = utils.load_locales(i18n_dir)

# 创建一个顶部栏，包含标题和语言选择
title_col, lang_col = st.columns([3, 1])

with title_col:
    st.title(f"MoneyPrinterTurbo v{config.project_version}")

with lang_col:
    display_languages = []
    selected_index = 0
    for i, code in enumerate(locales.keys()):
        display_languages.append(f"{code} - {locales[code].get('Language')}")
        if code == st.session_state.get("ui_language", ""):
            selected_index = i

    selected_language = st.selectbox(
        "Language / 语言",
        options=display_languages,
        index=selected_index,
        key="top_language_selector",
        label_visibility="collapsed",
    )
    if selected_language:
        code = selected_language.split(" - ")[0].strip()
        st.session_state["ui_language"] = code
        config.ui["language"] = code

# Test Upload Section
st.divider()
st.subheader("🧪 Test Video Upload")

# Create two columns for test upload
test_upload_cols = st.columns([1, 1])

with test_upload_cols[0]:
    st.write("**Test TikTok Upload**")
    tiktok_test_file = st.file_uploader(
        "Upload MP4 file for TikTok test",
        type=["mp4"],
        key="tiktok_test_file"
    )
    render_test_upload_action(
        tiktok_test_file,
        platform="tiktok",
        label="Test TikTok Upload",
        key="test_tiktok_upload",
    )
    if False and tiktok_test_file is not None:
        if st.button("Test TikTok Upload", key="test_tiktok_upload"):
            try:
                # Upload file to test endpoint
                files = {"file": tiktok_test_file}
                base_url = get_base_url()
                if not base_url:
                    st.error("❌ public_base_url is not configured in config.toml")
                    st.stop()
                    
                response = requests.post(
                    f"{base_url}/api/v1/test-upload?platform=tiktok",
                    files=files
                )
                
                if response.status_code == 200:
                    result = response.json()
                    st.success("✅ TikTok test upload completed!")
                    st.json(result.get("data", {}))
                else:
                    st.error(f"❌ TikTok test upload failed: {response.text}")
                    
            except Exception as e:
                st.error(f"❌ Error testing TikTok upload: {str(e)}")

with test_upload_cols[1]:
    st.write("**Test YouTube Upload**")
    youtube_test_file = st.file_uploader(
        "Upload MP4 file for YouTube test",
        type=["mp4"],
        key="youtube_test_file"
    )
    render_test_upload_action(
        youtube_test_file,
        platform="youtube",
        label="Test YouTube Upload",
        key="test_youtube_upload",
    )
    if False and youtube_test_file is not None:
        if st.button("Test YouTube Upload", key="test_youtube_upload"):
            try:
                # Upload file to test endpoint
                files = {"file": youtube_test_file}
                base_url = get_base_url()
                if not base_url:
                    st.error("❌ public_base_url is not configured in config.toml")
                    st.stop()
                    
                response = requests.post(
                    f"{base_url}/api/v1/test-upload?platform=youtube",
                    files=files
                )
                
                if response.status_code == 200:
                    result = response.json()
                    st.success("✅ YouTube test upload completed!")
                    st.json(result.get("data", {}))
                else:
                    st.error(f"❌ YouTube test upload failed: {response.text}")
                    
            except Exception as e:
                st.error(f"❌ Error testing YouTube upload: {str(e)}")

# Test both platforms
with test_upload_cols[0]:
    st.write("**Test Both Platforms**")
    both_test_file = st.file_uploader(
        "Upload MP4 file for both platforms test",
        type=["mp4"],
        key="both_test_file"
    )
    render_test_upload_action(
        both_test_file,
        platform="both",
        label="Test Both Platforms",
        key="test_both_upload",
    )
    if False and both_test_file is not None:
        if st.button("Test Both Platforms", key="test_both_upload"):
            try:
                # Upload file to test endpoint
                files = {"file": both_test_file}
                base_url = get_base_url()
                if not base_url:
                    st.error("❌ public_base_url is not configured in config.toml")
                    st.stop()
                    
                response = requests.post(
                    f"{base_url}/api/v1/test-upload?platform=both",
                    files=files
                )
                
                if response.status_code == 200:
                    result = response.json()
                    st.success("✅ Both platforms test upload completed!")
                    st.json(result.get("data", {}))
                else:
                    st.error(f"❌ Both platforms test upload failed: {response.text}")
                    
            except Exception as e:
                st.error(f"❌ Error testing both platforms upload: {str(e)}")

st.divider()

support_locales = [
    "zh-CN",
    "zh-HK",
    "zh-TW",
    "de-DE",
    "en-US",
    "fr-FR",
    "vi-VN",
    "th-TH",
    "tr-TR",
]


def get_all_fonts():
    fonts = []
    for root, dirs, files in os.walk(font_dir):
        for file in files:
            if file.endswith(".ttf") or file.endswith(".ttc"):
                fonts.append(file)
    fonts.sort()
    return fonts


def get_all_songs():
    songs = []
    for root, dirs, files in os.walk(song_dir):
        for file in files:
            if file.endswith(".mp3"):
                songs.append(file)
    return songs


def open_task_folder(task_id):
    try:
        # task_id 应始终是服务端生成的 UUID。这里先做格式校验，避免异常值
        # 通过路径拼接访问任务目录之外的位置，也避免后续打开目录时触发
        # 平台 shell 对特殊字符的解释。
        normalized_task_id = str(UUID(str(task_id)))
        tasks_root = os.path.abspath(os.path.join(root_dir, "storage", "tasks"))
        path = os.path.abspath(os.path.join(tasks_root, normalized_task_id))

        # 即使 UUID 校验通过，也再次确认最终路径仍在任务根目录内，避免
        # 未来调用方调整 task_id 来源时引入路径穿越风险。
        if not path.startswith(tasks_root + os.sep):
            logger.warning(f"invalid task folder path: {path}")
            return

        if os.path.isdir(path):
            webbrowser.open(f"file://{path}")
    except Exception as e:
        logger.error(e)


def scroll_to_bottom():
    js = """
    <script>
        console.log("scroll_to_bottom");
        function scroll(dummy_var_to_force_repeat_execution){
            var sections = parent.document.querySelectorAll('section.main');
            console.log(sections);
            for(let index = 0; index<sections.length; index++) {
                sections[index].scrollTop = sections[index].scrollHeight;
            }
        }
        scroll(1);
    </script>
    """
    st.components.v1.html(js, height=0, width=0)


def init_log():
    logger.remove()
    _lvl = "DEBUG"

    def format_record(record):
        # 获取日志记录中的文件全路径
        file_path = record["file"].path
        # 将绝对路径转换为相对于项目根目录的路径
        relative_path = os.path.relpath(file_path, root_dir)
        # 更新记录中的文件路径
        record["file"].path = f"./{relative_path}"
        # 返回修改后的格式字符串
        # 您可以根据需要调整这里的格式
        record["message"] = record["message"].replace(root_dir, ".")

        _format = (
            "<green>{time:%Y-%m-%d %H:%M:%S}</> | "
            + "<level>{level}</> | "
            + '"{file.path}:{line}":<blue> {function}</> '
            + "- <level>{message}</>"
            + "\n"
        )
        return _format

    logger.add(
        sys.stdout,
        level=_lvl,
        format=format_record,
        colorize=True,
    )


init_log()

locales = utils.load_locales(i18n_dir)


def tr(key):
    loc = locales.get(st.session_state["ui_language"], {})
    return loc.get("Translation", {}).get(key, key)


# 创建基础设置折叠框
if not config.app.get("hide_config", False):
    with st.expander(tr("Basic Settings"), expanded=False):
        config_panels = st.columns(3)
        left_config_panel = config_panels[0]
        middle_config_panel = config_panels[1]
        right_config_panel = config_panels[2]

        # 左侧面板 - 日志设置
        with left_config_panel:
            # 是否隐藏配置面板
            hide_config = st.checkbox(
                tr("Hide Basic Settings"), value=config.app.get("hide_config", False)
            )
            config.app["hide_config"] = hide_config

            # 是否禁用日志显示
            hide_log = st.checkbox(
                tr("Hide Log"), value=config.ui.get("hide_log", False)
            )
            config.ui["hide_log"] = hide_log

        # 中间面板 - LLM 设置

        with middle_config_panel:
            st.write(tr("LLM Settings"))
            llm_providers = [
                "OpenAI",
                "Moonshot",
                "Azure",
                "Qwen",
                "DeepSeek",
                "ModelScope",
                "Gemini",
                "Grok",
                "Ollama",
                "G4f",
                "OneAPI",
                "Cloudflare",
                "ERNIE",
                "Pollinations",
                "LiteLLM",
            ]
            saved_llm_provider = config.app.get("llm_provider", "OpenAI").lower()
            saved_llm_provider_index = 0
            for i, provider in enumerate(llm_providers):
                if provider.lower() == saved_llm_provider:
                    saved_llm_provider_index = i
                    break

            llm_provider = st.selectbox(
                tr("LLM Provider"),
                options=llm_providers,
                index=saved_llm_provider_index,
            )
            llm_helper = st.container()
            llm_provider = llm_provider.lower()
            config.app["llm_provider"] = llm_provider

            llm_api_key = config.app.get(f"{llm_provider}_api_key", "")
            llm_secret_key = config.app.get(
                f"{llm_provider}_secret_key", ""
            )  # only for baidu ernie
            llm_base_url = config.app.get(f"{llm_provider}_base_url", "")
            llm_model_name = config.app.get(f"{llm_provider}_model_name", "")
            llm_account_id = config.app.get(f"{llm_provider}_account_id", "")

            tips = ""
            if llm_provider == "ollama":
                if not llm_model_name:
                    llm_model_name = "qwen:7b"
                if not llm_base_url:
                    llm_base_url = "http://localhost:11434/v1"

                with llm_helper:
                    tips = """
                            ##### Ollama配置说明
                            - **API Key**: 随便填写，比如 123
                            - **Base Url**: 一般为 http://localhost:11434/v1
                                - 如果 `MoneyPrinterTurbo` 和 `Ollama` **不在同一台机器上**，需要填写 `Ollama` 机器的IP地址
                                - 如果 `MoneyPrinterTurbo` 是 `Docker` 部署，建议填写 `http://host.docker.internal:11434/v1`
                            - **Model Name**: 使用 `ollama list` 查看，比如 `qwen:7b`
                            """

            if llm_provider == "openai":
                if not llm_model_name:
                    llm_model_name = "gpt-3.5-turbo"
                with llm_helper:
                    tips = """
                            ##### OpenAI 配置说明
                            > 需要VPN开启全局流量模式
                            - **API Key**: [点击到官网申请](https://platform.openai.com/api-keys)
                            - **Base Url**: 官方 OpenAI 可留空；如果使用 OpenAI 兼容供应商（例如 OpenRouter），请填写对应的兼容接口地址
                            - **Model Name**: 填写**有权限**的模型；如果使用兼容供应商，请填写该平台支持的模型 ID
                            """

            if llm_provider == "moonshot":
                if not llm_model_name:
                    llm_model_name = "moonshot-v1-8k"
                with llm_helper:
                    tips = """
                            ##### Moonshot 配置说明
                            - **API Key**: [点击到官网申请](https://platform.moonshot.cn/console/api-keys)
                            - **Base Url**: 固定为 https://api.moonshot.cn/v1
                            - **Model Name**: 比如 moonshot-v1-8k，[点击查看模型列表](https://platform.moonshot.cn/docs/intro#%E6%A8%A1%E5%9E%8B%E5%88%97%E8%A1%A8)
                            """
            if llm_provider == "oneapi":
                if not llm_model_name:
                    llm_model_name = (
                        "claude-3-5-sonnet-20240620"  # 默认模型，可以根据需要调整
                    )
                with llm_helper:
                    tips = """
                        ##### OneAPI 配置说明
                        - **API Key**: 填写您的 OneAPI 密钥
                        - **Base Url**: 填写 OneAPI 的基础 URL
                        - **Model Name**: 填写您要使用的模型名称，例如 claude-3-5-sonnet-20240620
                        """

            if llm_provider == "qwen":
                if not llm_model_name:
                    llm_model_name = "qwen-max"
                with llm_helper:
                    tips = """
                            ##### 通义千问Qwen 配置说明
                            - **API Key**: [点击到官网申请](https://dashscope.console.aliyun.com/apiKey)
                            - **Base Url**: 留空
                            - **Model Name**: 比如 qwen-max，[点击查看模型列表](https://help.aliyun.com/zh/dashscope/developer-reference/model-introduction#3ef6d0bcf91wy)
                            """

            if llm_provider == "g4f":
                if not llm_model_name:
                    llm_model_name = "gpt-3.5-turbo"
                with llm_helper:
                    tips = """
                            ##### gpt4free 配置说明
                            > [GitHub开源项目](https://github.com/xtekky/gpt4free)，可以免费使用GPT模型，但是**稳定性较差**
                            - **API Key**: 随便填写，比如 123
                            - **Base Url**: 留空
                            - **Model Name**: 比如 gpt-3.5-turbo，[点击查看模型列表](https://github.com/xtekky/gpt4free/blob/main/g4f/models.py#L308)
                            """
            if llm_provider == "azure":
                with llm_helper:
                    tips = """
                            ##### Azure 配置说明
                            > [点击查看如何部署模型](https://learn.microsoft.com/zh-cn/azure/ai-services/openai/how-to/create-resource)
                            - **API Key**: [点击到Azure后台创建](https://portal.azure.com/#view/Microsoft_Azure_ProjectOxford/CognitiveServicesHub/~/OpenAI)
                            - **Base Url**: 留空
                            - **Model Name**: 填写你实际的部署名
                            """

            if llm_provider == "gemini":
                if not llm_model_name:
                    llm_model_name = "gemini-1.0-pro"

                with llm_helper:
                    tips = """
                            ##### Gemini 配置说明
                            > 需要VPN开启全局流量模式
                            - **API Key**: [点击到官网申请](https://ai.google.dev/)
                            - **Base Url**: 留空
                            - **Model Name**: 比如 gemini-1.0-pro
                            """

            if llm_provider == "grok":
                if not llm_model_name:
                    llm_model_name = "grok-4.3"
                if not llm_base_url:
                    llm_base_url = "https://api.x.ai/v1"

                with llm_helper:
                    tips = """
                            ##### Grok 配置说明
                            - **API Key**: 填写您的 GrokAPI 密钥
                            - **Base Url**: 填写 GrokAPI 的基础 URL
                            - **Model Name**: 比如 grok-4.3
                            """

            if llm_provider == "deepseek":
                if not llm_model_name:
                    llm_model_name = "deepseek-chat"
                if not llm_base_url:
                    llm_base_url = "https://api.deepseek.com"
                with llm_helper:
                    tips = """
                            ##### DeepSeek 配置说明
                            - **API Key**: [点击到官网申请](https://platform.deepseek.com/api_keys)
                            - **Base Url**: 固定为 https://api.deepseek.com
                            - **Model Name**: 固定为 deepseek-chat
                            """

            if llm_provider == "modelscope":
                if not llm_model_name:
                    llm_model_name = "Qwen/Qwen3-32B"
                if not llm_base_url:
                    llm_base_url = "https://api-inference.modelscope.cn/v1/"
                with llm_helper:
                    tips = """
                            ##### ModelScope 配置说明
                            - **API Key**: [点击到官网申请](https://modelscope.cn/docs/model-service/API-Inference/intro)
                            - **Base Url**: 固定为 https://api-inference.modelscope.cn/v1/
                            - **Model Name**: 比如 Qwen/Qwen3-32B，[点击查看模型列表](https://modelscope.cn/models?filter=inference_type&page=1)
                            """

            if llm_provider == "ernie":
                with llm_helper:
                    tips = """
                            ##### 百度文心一言 配置说明
                            - **API Key**: [点击到官网申请](https://console.bce.baidu.com/qianfan/ais/console/applicationConsole/application)
                            - **Secret Key**: [点击到官网申请](https://console.bce.baidu.com/qianfan/ais/console/applicationConsole/application)
                            - **Base Url**: 填写 **请求地址** [点击查看文档](https://cloud.baidu.com/doc/WENXINWORKSHOP/s/jlil56u11#%E8%AF%B7%E6%B1%82%E8%AF%B4%E6%98%8E)
                            """

            if llm_provider == "pollinations":
                if not llm_model_name:
                    llm_model_name = "default"
                with llm_helper:
                    tips = """
                            ##### Pollinations AI Configuration
                            - **API Key**: Optional - Leave empty for public access
                            - **Base Url**: Default is https://text.pollinations.ai/openai
                            - **Model Name**: Use 'openai-fast' or specify a model name
                            """

            if llm_provider == "litellm":
                if not llm_model_name:
                    llm_model_name = "openai/gpt-4o-mini"
                with llm_helper:
                    tips = """
                            ##### LiteLLM Configuration
                            > [LiteLLM](https://github.com/BerriAI/litellm) routes to 100+ LLM providers via a unified interface.
                            > Set your provider's API key as an env var: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `AWS_ACCESS_KEY_ID`, etc.
                            - **Model Name**: LiteLLM format — `openai/gpt-4o`, `anthropic/claude-sonnet-4-20250514`, `bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0`, `gemini/gemini-2.5-flash`. See [full provider list](https://docs.litellm.ai/docs/providers)
                            """

            if tips and config.ui["language"] == "zh":
                st.warning(
                    "中国用户建议使用 **DeepSeek** 或 **Moonshot** 作为大模型提供商\n- 国内可直接访问，不需要VPN \n- 注册就送额度，基本够用"
                )
                st.info(tips)

            st_llm_api_key = st.text_input(
                tr("API Key"), value=llm_api_key, type="password"
            )
            st_llm_base_url = st.text_input(tr("Base Url"), value=llm_base_url)
            st_llm_model_name = ""
            if llm_provider != "ernie":
                st_llm_model_name = st.text_input(
                    tr("Model Name"),
                    value=llm_model_name,
                    key=f"{llm_provider}_model_name_input",
                )
                if st_llm_model_name:
                    config.app[f"{llm_provider}_model_name"] = st_llm_model_name
            else:
                st_llm_model_name = None

            if st_llm_api_key:
                config.app[f"{llm_provider}_api_key"] = st_llm_api_key
            if st_llm_base_url:
                config.app[f"{llm_provider}_base_url"] = st_llm_base_url
            if st_llm_model_name:
                config.app[f"{llm_provider}_model_name"] = st_llm_model_name
            if llm_provider == "ernie":
                st_llm_secret_key = st.text_input(
                    tr("Secret Key"), value=llm_secret_key, type="password"
                )
                config.app[f"{llm_provider}_secret_key"] = st_llm_secret_key

            if llm_provider == "cloudflare":
                st_llm_account_id = st.text_input(
                    tr("Account ID"), value=llm_account_id
                )
                if st_llm_account_id:
                    config.app[f"{llm_provider}_account_id"] = st_llm_account_id

        # 右侧面板 - API 密钥设置
        with right_config_panel:

            def get_keys_from_config(cfg_key):
                api_keys = config.app.get(cfg_key, [])
                if isinstance(api_keys, str):
                    api_keys = [api_keys]
                api_key = ", ".join(api_keys)
                return api_key

            def save_keys_to_config(cfg_key, value):
                value = value.replace(" ", "")
                if value:
                    config.app[cfg_key] = value.split(",")

            st.write(tr("Video Source Settings"))

            pexels_api_key = get_keys_from_config("pexels_api_keys")
            pexels_api_key = st.text_input(
                tr("Pexels API Key"), value=pexels_api_key, type="password"
            )
            save_keys_to_config("pexels_api_keys", pexels_api_key)

            pixabay_api_key = get_keys_from_config("pixabay_api_keys")
            pixabay_api_key = st.text_input(
                tr("Pixabay API Key"), value=pixabay_api_key, type="password"
            )
            save_keys_to_config("pixabay_api_keys", pixabay_api_key)

params = VideoParams(video_subject="")
uploaded_files = []
uploaded_audio_file = None

social_platform_options = {
    "YouTube Shorts": SocialPlatform.youtube,
    "TikTok": SocialPlatform.tiktok,
}
tiktok_publish_mode = str(config.app.get("tiktok_publish_mode", "api"))
tiktok_api_connected = bool(
    config.app.get("tiktok_upload_enabled")
    and config.app.get("tiktok_access_token")
    and config.app.get("tiktok_refresh_token")
)
tiktok_browser_connected = bool(
    tiktok_publish_mode == "browser_assist"
    and config.app.get("tiktok_browser_upload_enabled", False)
)
tiktok_connected = tiktok_api_connected or tiktok_browser_connected
tiktok_creator_info = {}
if tiktok_api_connected:
    tiktok_publisher = TikTokPublisher()
    if hasattr(tiktok_publisher, "query_creator_info"):
        tiktok_creator_result = tiktok_publisher.query_creator_info()
        if tiktok_creator_result.get("success"):
            tiktok_creator_info = tiktok_creator_result.get("data", {})
youtube_connected = youtube_oauth.is_configured()
configured_social_platforms = config.app.get("social_platforms", ["youtube", "tiktok"])
connected_social_platforms = []
if youtube_connected:
    connected_social_platforms.append("youtube")
if tiktok_connected:
    connected_social_platforms.append("tiktok")
connect_base_url = config.app.get("public_base_url", "").rstrip("/")
connect_url = f"{connect_base_url}/api/v1/tiktok/oauth/start" if connect_base_url else ""

with st.container(border=True):
    st.write("Social publishing")
    status_cols = st.columns([1, 1, 2])
    if tiktok_browser_connected:
        status_cols[0].success("TikTok browser assist enabled")
    else:
        status_cols[0].success("TikTok connected" if tiktok_api_connected else "TikTok not connected")
    status_cols[1].success("YouTube connected" if youtube_connected else "YouTube not connected")
    if connect_url:
        if hasattr(st, "link_button"):
            status_cols[2].link_button("Connect / refresh TikTok", connect_url, use_container_width=True)
        else:
            status_cols[2].markdown(f"[Connect / refresh TikTok]({connect_url})")
    else:
        status_cols[2].warning("Set public_base_url in config.toml to enable TikTok connect.")

    if tiktok_creator_info:
        creator_name = (
            tiktok_creator_info.get("creator_nickname")
            or tiktok_creator_info.get("creator_username")
            or "Connected TikTok creator"
        )
        privacy_options = ", ".join(tiktok_creator_info.get("privacy_level_options", []))
        st.caption(f"TikTok creator: {creator_name}. Allowed privacy options: {privacy_options}")
    if tiktok_browser_connected:
        st.caption(
            "TikTok browser assist prepares the MP4 and caption, opens TikTok Studio, "
            "and leaves the final Post click for manual review."
        )

    mode_cols = st.columns([1, 1])
    selected_tiktok_publish_mode = mode_cols[0].selectbox(
        "TikTok mode",
        options=["api", "browser_assist"],
        format_func=lambda value: "Official API" if value == "api" else "Browser assist",
        index=0 if tiktok_publish_mode != "browser_assist" else 1,
    )
    selected_tiktok_browser_enabled = mode_cols[1].checkbox(
        "Enable TikTok browser assist",
        value=bool(config.app.get("tiktok_browser_upload_enabled", False)),
    )
    config.app["tiktok_publish_mode"] = selected_tiktok_publish_mode
    config.app["tiktok_browser_upload_enabled"] = selected_tiktok_browser_enabled
    if selected_tiktok_publish_mode == "browser_assist" and selected_tiktok_browser_enabled:
        tiktok_connected = True
    connected_social_platforms = ["youtube"] if youtube_connected else []
    if tiktok_connected:
        connected_social_platforms.append("tiktok")
    default_social_platforms = [
        label
        for label, platform in social_platform_options.items()
        if platform.value in configured_social_platforms
        and platform.value in connected_social_platforms
    ]

    social_cols = st.columns([2, 1, 1])
    selected_social_labels = social_cols[0].multiselect(
        "Platforms",
        options=list(social_platform_options.keys()),
        default=default_social_platforms,
    )
    selected_social_privacy = social_cols[1].selectbox(
        "Privacy",
        options=[PublishPrivacy.private, PublishPrivacy.public, PublishPrivacy.draft],
        format_func=lambda privacy: privacy.value,
        index=0,
    )
    selected_social_auto_publish = social_cols[2].checkbox(
        "Auto-publish after video",
        value=bool(config.app.get("social_auto_publish", False)),
    )
    tiktok_selected = "TikTok" in selected_social_labels
    tiktok_direct_post_consent = True
    if (
        tiktok_selected
        and selected_social_auto_publish
        and selected_tiktok_publish_mode != "browser_assist"
    ):
        tiktok_direct_post_consent = st.checkbox(
            "I confirm this video, caption, hashtags, and AI/synthetic label are ready to send to TikTok.",
            value=False,
            key="tiktok_direct_post_consent",
        )
    selected_social_platforms = [
        social_platform_options[label] for label in selected_social_labels
    ]
    config.app["social_platforms"] = [platform.value for platform in selected_social_platforms]
    config.app["social_privacy"] = selected_social_privacy.value
    config.app["social_auto_publish"] = selected_social_auto_publish
    params.social_platforms = selected_social_platforms
    params.social_privacy = selected_social_privacy
    params.social_auto_publish = selected_social_auto_publish
    params.tiktok_direct_post_consent = tiktok_direct_post_consent

with st.container(border=True):
    st.write("Social metadata")
    metadata_cols = st.columns([1, 1])
    social_title = metadata_cols[0].text_input(
        "Post title", value=config.app.get("social_post_title", "")
    ).strip()
    social_hashtags = metadata_cols[1].text_input(
        "Hashtags", value=config.app.get("social_post_hashtags", "")
    ).strip()
    social_description = st.text_area(
        "Post description",
        value=config.app.get("social_post_description", ""),
        height=110,
    ).strip()
    youtube_tags = st.text_input(
        "YouTube tags", value=config.app.get("social_youtube_tags", "")
    ).strip()
    config.app["social_post_title"] = social_title
    config.app["social_post_description"] = social_description
    config.app["social_post_hashtags"] = social_hashtags
    config.app["social_youtube_tags"] = youtube_tags
    if social_title or social_description or social_hashtags or youtube_tags:
        params.social_metadata = SocialMetadata(
            title=social_title or params.video_subject,
            description=social_description or social_title or params.video_subject,
            hashtags=[
                tag.strip()
                for tag in social_hashtags.replace(",", " ").split()
                if tag.strip()
            ],
            youtube_tags=[
                tag.strip()
                for tag in youtube_tags.split(",")
                if tag.strip()
            ],
        )

with st.container(border=True):
    st.write("News automation")
    news_sources = ["auto", "telethon", "newsdata", "guardian", "telegram"]
    saved_news_source = config.app.get("news_source", "auto")
    if saved_news_source not in news_sources:
        saved_news_source = "auto"
    news_cols = st.columns([1, 2, 1, 1])
    news_source = news_cols[0].selectbox(
        "Source",
        options=news_sources,
        index=news_sources.index(saved_news_source),
        key="top_news_source",
    )
    news_query = news_cols[1].text_input(
        "Search query",
        value=config.app.get("news_query", ""),
        key="top_news_query",
    ).strip()
    news_limit = news_cols[2].number_input(
        "Videos",
        min_value=1,
        max_value=10,
        value=int(config.app.get("news_auto_limit", 1)),
        step=1,
        key="top_news_limit",
    )
    news_country = news_cols[3].text_input(
        "Country",
        value=config.app.get("news_country", "us"),
        key="top_news_country",
    ).strip()
    news_language = st.text_input(
        "Language",
        value=config.app.get("news_language", "en"),
        key="top_news_language",
    ).strip()
    config.app["news_source"] = news_source
    config.app["news_query"] = news_query
    config.app["news_auto_limit"] = int(news_limit)
    config.app["news_country"] = news_country
    config.app["news_language"] = news_language
    if st.button("Find news, generate videos, and publish", key="top_auto_news_publish", type="primary"):
        config.save_config()
        try:
            payload = run_news_automation_inline(
                NewsAutomationRunRequest(
                    source=news_source,
                    query=news_query,
                    country=news_country,
                    language=news_language,
                    limit=int(news_limit),
                    platforms=params.social_platforms or None,
                    auto_publish=True,
                    privacy=params.social_privacy or get_social_privacy_setting(),
                    tiktok_direct_post_consent=True,
                )
            )
            if payload["queued_count"]:
                st.success(
                    f"News automation completed: {payload['queued_count']} videos processed"
                )
                st.json(payload)
            else:
                st.warning("No news stories found for this query/source.")
        except Exception as exc:
            st.error(f"Failed to start news automation: {str(exc)}")

llm_provider = config.app.get("llm_provider", "").lower()
panel = st.columns(3)
left_panel = panel[0]
middle_panel = panel[1]
right_panel = panel[2]

with left_panel:
    with st.container(border=True):
        st.write(tr("Video Script Settings"))
        params.video_subject = st.text_input(
            tr("Video Subject"),
            value=st.session_state["video_subject"],
            key="video_subject_input",
        ).strip()

        video_languages = [
            (tr("Auto Detect"), ""),
        ]
        for code in support_locales:
            video_languages.append((code, code))

        selected_index = st.selectbox(
            tr("Script Language"),
            index=0,
            options=range(
                len(video_languages)
            ),  # Use the index as the internal option value
            format_func=lambda x: video_languages[x][
                0
            ],  # The label is displayed to the user
        )
        params.video_language = video_languages[selected_index][1]

        if st.button(
            tr("Generate Video Script and Keywords"), key="auto_generate_script"
        ):
            with st.spinner(tr("Generating Video Script and Keywords")):
                script = llm.generate_script(
                    video_subject=params.video_subject, language=params.video_language
                )
                terms = llm.generate_terms(params.video_subject, script)
                if "Error: " in script:
                    st.error(tr(script))
                elif "Error: " in terms:
                    st.error(tr(terms))
                else:
                    st.session_state["video_script"] = script
                    st.session_state["video_terms"] = ", ".join(terms)
        params.video_script = st.text_area(
            tr("Video Script"), value=st.session_state["video_script"], height=280
        )
        if st.button(tr("Generate Video Keywords"), key="auto_generate_terms"):
            if not params.video_script:
                st.error(tr("Please Enter the Video Subject"))
                st.stop()

            with st.spinner(tr("Generating Video Keywords")):
                terms = llm.generate_terms(params.video_subject, params.video_script)
                if "Error: " in terms:
                    st.error(tr(terms))
                else:
                    st.session_state["video_terms"] = ", ".join(terms)

        params.video_terms = st.text_area(
            tr("Video Keywords"), value=st.session_state["video_terms"]
        )

with middle_panel:
    with st.container(border=True):
        st.write(tr("Video Settings"))
        video_concat_modes = [
            (tr("Sequential"), "sequential"),
            (tr("Random"), "random"),
        ]
        video_sources = [
            (tr("Pexels"), "pexels"),
            (tr("Pixabay"), "pixabay"),
            (tr("Local file"), "local"),
            (tr("News"), "news"),
        ]

        saved_video_source_name = config.app.get("video_source", "pexels")
        if saved_video_source_name not in [v[1] for v in video_sources]:
            saved_video_source_name = "pexels"
        saved_video_source_index = [v[1] for v in video_sources].index(
            saved_video_source_name
        )

        selected_index = st.selectbox(
            tr("Video Source"),
            options=range(len(video_sources)),
            format_func=lambda x: video_sources[x][0],
            index=saved_video_source_index,
        )
        params.video_source = video_sources[selected_index][1]
        config.app["video_source"] = params.video_source

        if params.video_source == "local":
            # Streamlit 的文件类型校验对扩展名大小写敏感，这里同时放行大小写两种形式。
            local_file_types = ["mp4", "mov", "avi", "flv", "mkv", "jpg", "jpeg", "png"]
            uploaded_files = st.file_uploader(
                "Upload Local Files",
                type=local_file_types + [file_type.upper() for file_type in local_file_types],
                accept_multiple_files=True,
            )

        if params.video_source == "news":
            news_sources = ["auto", "newsdata", "guardian", "telegram", "telethon"]
            saved_news_source = config.app.get("news_source", "auto")
            if saved_news_source not in news_sources:
                saved_news_source = "auto"
            params.news_source = st.selectbox(
                "News source",
                options=news_sources,
                index=news_sources.index(saved_news_source),
            )
            params.news_query = st.text_input(
                "News query",
                value=config.app.get("news_query", "") or params.video_subject,
            ).strip()
            news_cols = st.columns(3)
            params.news_country = news_cols[0].text_input(
                "Country", value=config.app.get("news_country", "us")
            ).strip()
            params.news_language = news_cols[1].text_input(
                "Language", value=config.app.get("news_language", "en")
            ).strip()
            params.news_category = news_cols[2].text_input(
                "Category", value=config.app.get("news_category", "")
            ).strip() or None
            config.app["news_source"] = params.news_source
            config.app["news_query"] = params.news_query
            config.app["news_country"] = params.news_country
            config.app["news_language"] = params.news_language
            config.app["news_category"] = params.news_category or ""
            if st.button("Auto-run news and publish", key="auto_news_publish"):
                try:
                    payload = run_news_automation_inline(
                        NewsAutomationRunRequest(
                            source=params.news_source,
                            query=params.news_query,
                            country=params.news_country,
                            language=params.news_language,
                            category=params.news_category,
                            limit=int(config.app.get("news_auto_limit", 1)),
                            video_language=params.video_language,
                            platforms=params.social_platforms or None,
                            auto_publish=True,
                            privacy=params.social_privacy or get_social_privacy_setting(),
                            tiktok_direct_post_consent=True,
                        )
                    )
                    if payload["queued_count"]:
                        st.success(
                            f"News automation completed: {payload['queued_count']} videos processed"
                        )
                        st.json(payload)
                    else:
                        st.warning("No news stories found for this query/source.")
                except Exception as exc:
                    st.error(f"Failed to start news automation: {str(exc)}")

        selected_index = st.selectbox(
            tr("Video Concat Mode"),
            index=1,
            options=range(
                len(video_concat_modes)
            ),  # Use the index as the internal option value
            format_func=lambda x: video_concat_modes[x][
                0
            ],  # The label is displayed to the user
        )
        params.video_concat_mode = VideoConcatMode(
            video_concat_modes[selected_index][1]
        )

        # 视频转场模式
        video_transition_modes = [
            (tr("None"), VideoTransitionMode.none.value),
            (tr("Shuffle"), VideoTransitionMode.shuffle.value),
            (tr("FadeIn"), VideoTransitionMode.fade_in.value),
            (tr("FadeOut"), VideoTransitionMode.fade_out.value),
            (tr("SlideIn"), VideoTransitionMode.slide_in.value),
            (tr("SlideOut"), VideoTransitionMode.slide_out.value),
        ]
        selected_index = st.selectbox(
            tr("Video Transition Mode"),
            options=range(len(video_transition_modes)),
            format_func=lambda x: video_transition_modes[x][0],
            index=0,
        )
        params.video_transition_mode = VideoTransitionMode(
            video_transition_modes[selected_index][1]
        )

        video_aspect_ratios = [
            (tr("Portrait"), VideoAspect.portrait.value),
            (tr("Landscape"), VideoAspect.landscape.value),
        ]
        selected_index = st.selectbox(
            tr("Video Ratio"),
            options=range(
                len(video_aspect_ratios)
            ),  # Use the index as the internal option value
            format_func=lambda x: video_aspect_ratios[x][
                0
            ],  # The label is displayed to the user
        )
        params.video_aspect = VideoAspect(video_aspect_ratios[selected_index][1])

        params.video_clip_duration = st.selectbox(
            tr("Clip Duration"), options=[2, 3, 4, 5, 6, 7, 8, 9, 10], index=1
        )
        params.video_count = st.selectbox(
            tr("Number of Videos Generated Simultaneously"),
            options=[1, 2, 3, 4, 5],
            index=0,
        )
    with st.container(border=True):
        st.write(tr("Audio Settings"))

        # 添加TTS服务器选择下拉框
        tts_servers = [
            ("azure-tts-v1", "Azure TTS V1"),
            ("azure-tts-v2", "Azure TTS V2"),
            ("siliconflow", "SiliconFlow TTS"),
            ("gemini-tts", "Google Gemini TTS"),
        ]

        # 获取保存的TTS服务器，默认为v1
        saved_tts_server = config.ui.get("tts_server", "azure-tts-v1")
        saved_tts_server_index = 0
        for i, (server_value, _) in enumerate(tts_servers):
            if server_value == saved_tts_server:
                saved_tts_server_index = i
                break

        selected_tts_server_index = st.selectbox(
            tr("TTS Servers"),
            options=range(len(tts_servers)),
            format_func=lambda x: tts_servers[x][1],
            index=saved_tts_server_index,
        )

        selected_tts_server = tts_servers[selected_tts_server_index][0]
        config.ui["tts_server"] = selected_tts_server

        # 根据选择的TTS服务器获取声音列表
        filtered_voices = []

        if selected_tts_server == "siliconflow":
            # 获取硅基流动的声音列表
            filtered_voices = voice.get_siliconflow_voices()
        elif selected_tts_server == "gemini-tts":
            # 获取Gemini TTS的声音列表
            filtered_voices = voice.get_gemini_voices()
        else:
            # 获取Azure的声音列表
            all_voices = voice.get_all_azure_voices(filter_locals=None)

            # 根据选择的TTS服务器筛选声音
            for v in all_voices:
                if selected_tts_server == "azure-tts-v2":
                    # V2版本的声音名称中包含"v2"
                    if "V2" in v:
                        filtered_voices.append(v)
                else:
                    # V1版本的声音名称中不包含"v2"
                    if "V2" not in v:
                        filtered_voices.append(v)

        friendly_names = {
            v: v.replace("Female", tr("Female"))
            .replace("Male", tr("Male"))
            .replace("Neural", "")
            for v in filtered_voices
        }

        saved_voice_name = config.ui.get("voice_name", "")
        saved_voice_name_index = 0

        # 检查保存的声音是否在当前筛选的声音列表中
        if saved_voice_name in friendly_names:
            saved_voice_name_index = list(friendly_names.keys()).index(saved_voice_name)
        else:
            # 如果不在，则根据当前UI语言选择一个默认声音
            for i, v in enumerate(filtered_voices):
                if v.lower().startswith(st.session_state["ui_language"].lower()):
                    saved_voice_name_index = i
                    break

        # 如果没有找到匹配的声音，使用第一个声音
        if saved_voice_name_index >= len(friendly_names) and friendly_names:
            saved_voice_name_index = 0

        # 确保有声音可选
        if friendly_names:
            selected_friendly_name = st.selectbox(
                tr("Speech Synthesis"),
                options=list(friendly_names.values()),
                index=min(saved_voice_name_index, len(friendly_names) - 1)
                if friendly_names
                else 0,
            )

            voice_name = list(friendly_names.keys())[
                list(friendly_names.values()).index(selected_friendly_name)
            ]
            params.voice_name = voice_name
            config.ui["voice_name"] = voice_name
        else:
            # 如果没有声音可选，显示提示信息
            st.warning(
                tr(
                    "No voices available for the selected TTS server. Please select another server."
                )
            )
            params.voice_name = ""
            config.ui["voice_name"] = ""

        # 只有在有声音可选时才显示试听按钮
        if friendly_names and st.button(tr("Play Voice")):
            play_content = params.video_subject
            if not play_content:
                play_content = params.video_script
            if not play_content:
                play_content = tr("Voice Example")
            with st.spinner(tr("Synthesizing Voice")):
                temp_dir = utils.storage_dir("temp", create=True)
                audio_file = os.path.join(temp_dir, f"tmp-voice-{str(uuid4())}.mp3")
                sub_maker = voice.tts(
                    text=play_content,
                    voice_name=voice_name,
                    voice_rate=params.voice_rate,
                    voice_file=audio_file,
                    voice_volume=params.voice_volume,
                )
                # if the voice file generation failed, try again with a default content.
                if not sub_maker:
                    play_content = "This is a example voice. if you hear this, the voice synthesis failed with the original content."
                    sub_maker = voice.tts(
                        text=play_content,
                        voice_name=voice_name,
                        voice_rate=params.voice_rate,
                        voice_file=audio_file,
                        voice_volume=params.voice_volume,
                    )

                if sub_maker and os.path.exists(audio_file):
                    st.audio(audio_file, format="audio/mp3")
                    if os.path.exists(audio_file):
                        os.remove(audio_file)

        # 当选择V2版本或者声音是V2声音时，显示服务区域和API key输入框
        if selected_tts_server == "azure-tts-v2" or (
            voice_name and voice.is_azure_v2_voice(voice_name)
        ):
            saved_azure_speech_region = config.azure.get("speech_region", "")
            saved_azure_speech_key = config.azure.get("speech_key", "")
            azure_speech_region = st.text_input(
                tr("Speech Region"),
                value=saved_azure_speech_region,
                key="azure_speech_region_input",
            )
            azure_speech_key = st.text_input(
                tr("Speech Key"),
                value=saved_azure_speech_key,
                type="password",
                key="azure_speech_key_input",
            )
            config.azure["speech_region"] = azure_speech_region
            config.azure["speech_key"] = azure_speech_key

        # 当选择硅基流动时，显示API key输入框和说明信息
        if selected_tts_server == "siliconflow" or (
            voice_name and voice.is_siliconflow_voice(voice_name)
        ):
            saved_siliconflow_api_key = config.siliconflow.get("api_key", "")

            siliconflow_api_key = st.text_input(
                tr("SiliconFlow API Key"),
                value=saved_siliconflow_api_key,
                type="password",
                key="siliconflow_api_key_input",
            )

            # 显示硅基流动的说明信息
            st.info(
                tr("SiliconFlow TTS Settings")
                + ":\n"
                + "- "
                + tr("Speed: Range [0.25, 4.0], default is 1.0")
                + "\n"
                + "- "
                + tr("Volume: Uses Speech Volume setting, default 1.0 maps to gain 0")
            )

            config.siliconflow["api_key"] = siliconflow_api_key

        params.voice_volume = st.selectbox(
            tr("Speech Volume"),
            options=[0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 4.0, 5.0],
            index=2,
        )

        params.voice_rate = st.selectbox(
            tr("Speech Rate"),
            options=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0],
            index=2,
        )

        custom_audio_file_types = ["mp3", "wav", "m4a", "aac", "flac", "ogg"]
        uploaded_audio_file = st.file_uploader(
            tr("Custom Audio File"),
            type=custom_audio_file_types
            + [file_type.upper() for file_type in custom_audio_file_types],
            accept_multiple_files=False,
            key="custom_audio_file_uploader",
        )
        if uploaded_audio_file:
            st.audio(uploaded_audio_file, format="audio/mp3")
            st.info(
                tr(
                    "Custom audio will be used directly. TTS synthesis will be skipped for this task."
                )
            )

        bgm_options = [
            (tr("No Background Music"), ""),
            (tr("Random Background Music"), "random"),
            (tr("Custom Background Music"), "custom"),
        ]
        selected_index = st.selectbox(
            tr("Background Music"),
            index=1,
            options=range(
                len(bgm_options)
            ),  # Use the index as the internal option value
            format_func=lambda x: bgm_options[x][
                0
            ],  # The label is displayed to the user
        )
        # Get the selected background music type
        params.bgm_type = bgm_options[selected_index][1]

        # Show or hide components based on the selection
        if params.bgm_type == "custom":
            custom_bgm_file = st.text_input(
                tr("Custom Background Music File"), key="custom_bgm_file_input"
            )
            if custom_bgm_file:
                # 这里不直接用 os.path.exists 判断，因为用户常见输入是
                # output000.mp3，这个文件名需要由服务层映射到 resource/songs
                # 目录后再校验。服务层会统一限制目录和文件类型，避免任意路径读取。
                params.bgm_file = custom_bgm_file.strip()
                # st.write(f":red[已选择自定义背景音乐]：**{custom_bgm_file}**")
        params.bgm_volume = st.selectbox(
            tr("Background Music Volume"),
            options=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            index=2,
        )

with right_panel:
    with st.container(border=True):
        st.write(tr("Subtitle Settings"))
        params.subtitle_enabled = st.checkbox(tr("Enable Subtitles"), value=True)
        font_names = get_all_fonts()
        saved_font_name = config.ui.get("font_name", "MicrosoftYaHeiBold.ttc")
        saved_font_name_index = 0
        if saved_font_name in font_names:
            saved_font_name_index = font_names.index(saved_font_name)
        params.font_name = st.selectbox(
            tr("Font"), font_names, index=saved_font_name_index
        )
        config.ui["font_name"] = params.font_name

        subtitle_positions = [
            (tr("Top"), "top"),
            (tr("Center"), "center"),
            (tr("Bottom"), "bottom"),
            (tr("Custom"), "custom"),
        ]
        saved_subtitle_position = config.ui.get("subtitle_position", "bottom")
        saved_position_index = 2
        for i, (_, pos_value) in enumerate(subtitle_positions):
            if pos_value == saved_subtitle_position:
                saved_position_index = i
                break
        selected_index = st.selectbox(
            tr("Position"),
            index=saved_position_index,
            options=range(len(subtitle_positions)),
            format_func=lambda x: subtitle_positions[x][0],
        )
        params.subtitle_position = subtitle_positions[selected_index][1]
        config.ui["subtitle_position"] = params.subtitle_position

        if params.subtitle_position == "custom":
            saved_custom_position = config.ui.get("custom_position", 70.0)
            custom_position = st.text_input(
                tr("Custom Position (% from top)"),
                value=str(saved_custom_position),
                key="custom_position_input",
            )
            try:
                params.custom_position = float(custom_position)
                if params.custom_position < 0 or params.custom_position > 100:
                    st.error(tr("Please enter a value between 0 and 100"))
                else:
                    config.ui["custom_position"] = params.custom_position
            except ValueError:
                st.error(tr("Please enter a valid number"))

        font_cols = st.columns([0.3, 0.7])
        with font_cols[0]:
            saved_text_fore_color = config.ui.get("text_fore_color", "#FFFFFF")
            params.text_fore_color = st.color_picker(
                tr("Font Color"), saved_text_fore_color
            )
            config.ui["text_fore_color"] = params.text_fore_color

        with font_cols[1]:
            saved_font_size = config.ui.get("font_size", 60)
            params.font_size = st.slider(tr("Font Size"), 30, 100, saved_font_size)
            config.ui["font_size"] = params.font_size

        stroke_cols = st.columns([0.3, 0.7])
        with stroke_cols[0]:
            params.stroke_color = st.color_picker(tr("Stroke Color"), "#000000")
        with stroke_cols[1]:
            params.stroke_width = st.slider(tr("Stroke Width"), 0.0, 10.0, 1.5)
    with st.expander(tr("Click to show API Key management"), expanded=False):
        st.subheader(tr("Manage Pexels and Pixabay API Keys"))

        col1, col2 = st.tabs(["Pexels API Keys", "Pixabay API Keys"])

        with col1:
            st.subheader("Pexels API Keys")
            if config.app["pexels_api_keys"]:
                st.write(tr("Current Keys:"))
                for key in config.app["pexels_api_keys"]:
                    st.code(key)
            else:
                st.info(tr("No Pexels API Keys currently"))

            new_key = st.text_input(tr("Add Pexels API Key"), key="pexels_new_key")
            if st.button(tr("Add Pexels API Key")):
                if new_key and new_key not in config.app["pexels_api_keys"]:
                    config.app["pexels_api_keys"].append(new_key)
                    config.save_config()
                    st.success(tr("Pexels API Key added successfully"))
                elif new_key in config.app["pexels_api_keys"]:
                    st.warning(tr("This API Key already exists"))
                else:
                    st.error(tr("Please enter a valid API Key"))

            if config.app["pexels_api_keys"]:
                delete_key = st.selectbox(
                    tr("Select Pexels API Key to delete"), config.app["pexels_api_keys"], key="pexels_delete_key"
                )
                if st.button(tr("Delete Selected Pexels API Key")):
                    config.app["pexels_api_keys"].remove(delete_key)
                    config.save_config()
                    st.success(tr("Pexels API Key deleted successfully"))

        with col2:
            st.subheader("Pixabay API Keys")

            if config.app["pixabay_api_keys"]:
                st.write(tr("Current Keys:"))
                for key in config.app["pixabay_api_keys"]:
                    st.code(key)
            else:
                st.info(tr("No Pixabay API Keys currently"))

            new_key = st.text_input(tr("Add Pixabay API Key"), key="pixabay_new_key")
            if st.button(tr("Add Pixabay API Key")):
                if new_key and new_key not in config.app["pixabay_api_keys"]:
                    config.app["pixabay_api_keys"].append(new_key)
                    config.save_config()
                    st.success(tr("Pixabay API Key added successfully"))
                elif new_key in config.app["pixabay_api_keys"]:
                    st.warning(tr("This API Key already exists"))
                else:
                    st.error(tr("Please enter a valid API Key"))

            if config.app["pixabay_api_keys"]:
                delete_key = st.selectbox(
                    tr("Select Pixabay API Key to delete"), config.app["pixabay_api_keys"], key="pixabay_delete_key"
                )
                if st.button(tr("Delete Selected Pixabay API Key")):
                    config.app["pixabay_api_keys"].remove(delete_key)
                    config.save_config()
                    st.success(tr("Pixabay API Key deleted successfully"))

start_button = st.button(tr("Generate Video"), use_container_width=True, type="primary")
if start_button:
    config.save_config()
    task_id = str(uuid4())
    if not params.video_subject and not params.video_script:
        st.error(tr("Video Script and Subject Cannot Both Be Empty"))
        scroll_to_bottom()
        st.stop()

    if params.video_source not in ["pexels", "pixabay", "local", "news"]:
        st.error(tr("Please Select a Valid Video Source"))
        scroll_to_bottom()
        st.stop()

    if params.video_source == "pexels" and not config.app.get("pexels_api_keys", ""):
        st.error(tr("Please Enter the Pexels API Key"))
        scroll_to_bottom()
        st.stop()

    if params.video_source == "pixabay" and not config.app.get("pixabay_api_keys", ""):
        st.error(tr("Please Enter the Pixabay API Key"))
        scroll_to_bottom()
        st.stop()

    if params.video_source == "news":
        params.news_query = params.news_query or params.video_subject
        if not params.news_query:
            st.error("Please enter a news query or video subject")
            scroll_to_bottom()
            st.stop()
        if params.news_source == "newsdata" and not config.app.get("newsdata_api_key", ""):
            st.error("Please enter the NewsData API key in config.toml")
            scroll_to_bottom()
            st.stop()
        if params.news_source == "guardian" and not config.app.get("guardian_api_key", ""):
            st.error("Please enter the Guardian API key in config.toml")
            scroll_to_bottom()
            st.stop()
        if params.news_source == "telegram" and (
            not config.app.get("telegram_bot_token", "")
            or not config.app.get("telegram_channel_ids", [])
        ):
            st.error("Please configure telegram_bot_token and telegram_channel_ids in config.toml")
            scroll_to_bottom()
            st.stop()
        if params.news_source == "telethon" and (
            not config.app.get("telegram_api_id", "")
            or not config.app.get("telegram_api_hash", "")
        ):
            st.error("Please configure telegram_api_id and telegram_api_hash in config.toml")
            scroll_to_bottom()
            st.stop()

    if uploaded_audio_file:
        task_dir = utils.task_dir(task_id)
        # 上传文件名来自浏览器，不能直接拼到磁盘路径里；这里只保留扩展名，
        # 并使用固定文件名保存到当前任务目录，避免路径穿越或特殊字符问题。
        _, audio_ext = os.path.splitext(os.path.basename(uploaded_audio_file.name))
        audio_ext = audio_ext.lower() or ".mp3"
        custom_audio_path = os.path.join(task_dir, f"custom-audio{audio_ext}")
        with open(custom_audio_path, "wb") as f:
            f.write(uploaded_audio_file.getbuffer())
        params.custom_audio_file = custom_audio_path

    if uploaded_files:
        local_videos_dir = utils.storage_dir("local_videos", create=True)
        # 每次重新上传时都以本次选择的素材为准，避免旧素材不断重复追加。
        params.video_materials = []
        persisted_local_materials = []
        for file in uploaded_files:
            file_path = os.path.join(local_videos_dir, f"{file.file_id}_{file.name}")
            with open(file_path, "wb") as f:
                f.write(file.getbuffer())
                m = MaterialInfo()
                m.provider = "local"
                m.url = file_path
                params.video_materials.append(m)
                persisted_local_materials.append(
                    {
                        "provider": m.provider,
                        "url": m.url,
                        "duration": m.duration,
                    }
                )
        # 将已上传并保存到本地的视频素材写入会话，供后续只改文案时直接复用。
        st.session_state["local_video_materials"] = persisted_local_materials
    elif params.video_source == "local" and st.session_state["local_video_materials"]:
        # 当用户没有重新上传文件时，复用最近一次已经保存到磁盘的本地素材列表。
        params.video_materials = []
        for material in st.session_state["local_video_materials"]:
            m = MaterialInfo()
            m.provider = material.get("provider", "local")
            m.url = material.get("url", "")
            m.duration = material.get("duration", 0)
            if m.url:
                params.video_materials.append(m)

    log_container = st.empty()
    log_records = []

    def log_received(msg):
        if config.ui["hide_log"]:
            return
        with log_container:
            log_records.append(msg)
            st.code("\n".join(log_records))

    logger.add(log_received)

    st.toast(tr("Generating Video"))
    logger.info(tr("Start Generating Video"))
    logger.info(utils.to_json(params))
    scroll_to_bottom()

    result = tm.start(task_id=task_id, params=params)
    if not result or "videos" not in result:
        st.error(tr("Video Generation Failed"))
        logger.error(tr("Video Generation Failed"))
        scroll_to_bottom()
        st.stop()

    video_files = result.get("videos", [])
    st.success(tr("Video Generation Completed"))
    try:
        if video_files:
            player_cols = st.columns(len(video_files) * 2 + 1)
            for i, url in enumerate(video_files):
                player_cols[i * 2 + 1].video(url)
    except Exception:
        pass

    open_task_folder(task_id)
    logger.info(tr("Video Generation Completed"))
    scroll_to_bottom()

config.save_config()
