from fastapi import Path, Request

from app.controllers import base
from app.controllers.v1 import video as video_controller
from app.controllers.v1.base import new_router
from app.models import const
from app.models.exception import HttpException
from app.models.schema import (
    AutomationRunRequest,
    PublishRequest,
    SocialMetadata,
    TrendQueryRequest,
)
from app.services import automation, social_metadata, social_publisher, state as sm
from app.services import task as tm
from app.services import trends
from app.utils import utils

router = new_router()


@router.post("/trends", summary="Discover trend candidates")
def discover_trends(request: Request, body: TrendQueryRequest):
    candidates = trends.discover_trends(
        source=body.source,
        region=body.region,
        category_id=body.category_id,
        limit=body.limit,
    )
    return utils.get_response(
        200, {"trends": [candidate.model_dump() for candidate in candidates]}
    )


@router.post("/automation/runs", summary="Create videos from trend candidates")
def create_automation_run(request: Request, body: AutomationRunRequest):
    prepared = automation.prepare_run(body)
    queued_tasks = []

    for task_info in prepared["tasks"]:
        task_id = task_info["task_id"]
        trend = task_info["trend"]
        params = task_info["params"]
        sm.state.update_task(
            task_id,
            state=const.TASK_STATE_PROCESSING,
            progress=0,
            automation_run_id=prepared["run_id"],
            trend_candidate=trend.model_dump(),
        )
        video_controller.task_manager.add_task(
            tm.start, task_id=task_id, params=params, stop_at="video"
        )
        queued_tasks.append(
            {
                    "task_id": task_id,
                    "trend": trend.model_dump(),
                    "params": params.model_dump(mode="json"),
                }
            )

    return utils.get_response(
        200,
        {
            "run_id": prepared["run_id"],
            "tasks": queued_tasks,
            "candidate_count": len(prepared["candidates"]),
        },
    )


@router.get("/tasks/{task_id}/publish", summary="Get publish status")
def get_publish_status(request: Request, task_id: str = Path(..., description="Task ID")):
    request_id = base.get_task_id(request)
    task = sm.state.get_task(task_id)
    if not task:
        raise HttpException(
            task_id=task_id, status_code=404, message=f"{request_id}: task not found"
        )
    return utils.get_response(
        200,
        {
            "task_id": task_id,
            "social_metadata": task.get("social_metadata"),
            "publish_results": task.get("publish_results"),
            "cross_post_results": task.get("cross_post_results"),
        },
    )


@router.post("/tasks/{task_id}/metadata/regenerate", summary="Regenerate social metadata")
def regenerate_metadata(
    request: Request, task_id: str = Path(..., description="Task ID")
):
    request_id = base.get_task_id(request)
    task = sm.state.get_task(task_id)
    if not task:
        raise HttpException(
            task_id=task_id, status_code=404, message=f"{request_id}: task not found"
        )

    metadata = social_metadata.generate_social_metadata(
        video_subject=(task.get("trend_candidate") or {}).get("topic", ""),
        video_script=task.get("script", ""),
        video_terms=task.get("terms", []),
        trend_context=task.get("trend_candidate"),
    )
    current = dict(task)
    current.pop("task_id", None)
    sm.state.update_task(task_id, **{**current, "social_metadata": metadata.model_dump()})
    return utils.get_response(
        200, {"task_id": task_id, "social_metadata": metadata.model_dump()}
    )


@router.post("/tasks/{task_id}/publish", summary="Publish a completed task")
def publish_task(
    request: Request,
    body: PublishRequest,
    task_id: str = Path(..., description="Task ID"),
):
    request_id = base.get_task_id(request)
    task = sm.state.get_task(task_id)
    if not task:
        raise HttpException(
            task_id=task_id, status_code=404, message=f"{request_id}: task not found"
        )

    metadata = body.metadata
    if metadata is None:
        if task.get("social_metadata"):
            metadata = SocialMetadata(**task["social_metadata"])
        else:
            metadata = social_metadata.fallback_metadata(
                (task.get("trend_candidate") or {}).get("topic", ""), task.get("terms", [])
            )

    platforms = [platform.value for platform in body.platforms] if body.platforms else None
    results = social_publisher.publish_existing_task(
        task_id=task_id,
        metadata=metadata,
        platforms=platforms,
        privacy=body.privacy or None,
    )
    return utils.get_response(200, {"task_id": task_id, "publish_results": results})
