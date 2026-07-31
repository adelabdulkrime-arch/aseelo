"""Job polling and dashboard summary endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.deps import CurrentUser, DbSession
from app.errors import NotFoundError
from app.models import RenderingJob, Video, VideoStatus
from app.routers.videos import serialize_video
from app.schemas import DashboardStats, JobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
dashboard_router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> JobOut:
    job = db.scalar(
        select(RenderingJob)
        .join(Video, Video.id == RenderingJob.video_id)
        .where(RenderingJob.id == job_id, Video.user_id == user.id)
    )
    if job is None:
        raise NotFoundError("Job not found")
    return JobOut.model_validate(job)


@dashboard_router.get("", response_model=DashboardStats)
def get_dashboard(user: CurrentUser, db: DbSession) -> DashboardStats:
    owned = select(Video).where(Video.user_id == user.id)

    def count_where(*conditions: object) -> int:
        return db.scalar(select(func.count()).select_from(owned.where(*conditions).subquery())) or 0

    total_videos = count_where()
    videos_today = count_where(func.date(Video.created_at) == func.current_date())
    processing_jobs = count_where(Video.status.in_((VideoStatus.QUEUED, VideoStatus.PROCESSING)))
    completed_videos = count_where(Video.status == VideoStatus.COMPLETED)
    failed_videos = count_where(Video.status == VideoStatus.FAILED)

    storage_used_bytes = db.scalar(
        select(
            func.coalesce(func.sum(func.coalesce(Video.input_file_size, 0)), 0)
            + func.coalesce(func.sum(func.coalesce(Video.output_file_size, 0)), 0)
        ).where(Video.user_id == user.id)
    ) or 0

    recent = db.scalars(
        owned.options(selectinload(Video.template), selectinload(Video.jobs))
        .order_by(Video.created_at.desc())
        .limit(5)
    )

    return DashboardStats(
        total_videos=total_videos,
        videos_today=videos_today,
        processing_jobs=processing_jobs,
        completed_videos=completed_videos,
        failed_videos=failed_videos,
        storage_used_bytes=int(storage_used_bytes),
        recent_videos=[serialize_video(v) for v in recent],
    )
