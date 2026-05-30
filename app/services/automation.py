from app.models.schema import AutomationRunRequest, VideoParams
from app.services import trends
from app.utils import utils


def build_video_params_from_trend(request: AutomationRunRequest, topic: str) -> VideoParams:
    return VideoParams(
        video_subject=topic,
        video_language=request.video_language or "",
        video_aspect="9:16",
        paragraph_number=1,
        social_auto_publish=request.auto_publish,
        social_platforms=request.platforms,
    )


def prepare_run(request: AutomationRunRequest) -> dict:
    run_id = utils.get_uuid()
    candidates = trends.discover_trends(
        source=request.trend_source,
        region=request.region,
        category_id=request.category_id,
        limit=request.limit,
    )
    tasks = []
    for candidate in candidates[: request.limit]:
        task_id = utils.get_uuid()
        params = build_video_params_from_trend(request, candidate.topic)
        tasks.append(
            {
                "task_id": task_id,
                "params": params,
                "trend": candidate,
                "auto_publish": request.auto_publish,
                "platforms": [platform.value for platform in request.platforms],
            }
        )

    return {
        "run_id": run_id,
        "candidates": candidates,
        "tasks": tasks,
    }
