"""Video lifecycle endpoints: create, list, detail, delete, render, download."""

# No `from __future__ import annotations` here: slowapi's @limiter.limit wrapper makes
# FastAPI resolve string annotations against slowapi's module globals, where this
# module's dependency aliases do not exist, so they degrade into required body fields.

import json
import uuid
from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.deps import CurrentUser, DbSession, OwnedVideo
from app.errors import ConflictError, NotFoundError, ValidationError
from app.logging_config import get_logger
from app.models import JobStatus, RenderingJob, Template, Video, VideoStatus
from app.rate_limit import limiter
from app.schemas import (
    Caption,
    JobOut,
    MessageResponse,
    TemplateOut,
    VideoCreateForm,
    VideoListOut,
    VideoOut,
    validate_caption_track,
)
from app.services.file_validation import validate_video_upload
from app.services.pipeline import initial_steps_payload
from app.storage import build_key, get_storage
from app.worker.celery_app import RENDER_QUEUE, RENDER_TASK, celery_app

logger = get_logger(__name__)
router = APIRouter(prefix="/api/videos", tags=["videos"])

_STATUS_FILTERS: dict[str, tuple[VideoStatus, ...]] = {
    "processing": (VideoStatus.QUEUED, VideoStatus.PROCESSING),
    "completed": (VideoStatus.COMPLETED,),
    "failed": (VideoStatus.FAILED,),
}


def serialize_video(video: Video) -> VideoOut:
    storage = get_storage()
    out = VideoOut(
        id=video.id,
        title=video.title,
        text_content=video.text_content,
        # Built field by field rather than from_attributes, so anything added to
        # the model has to be listed here too or it silently serialises as its
        # default - which is exactly how captions first came back empty.
        captions=video.captions or [],
        quality=video.quality,
        template_id=video.template_id,
        status=video.status,
        output_file_url=storage.public_url(video.output_file_url) if video.output_file_url else None,
        thumbnail_url=storage.public_url(video.thumbnail_url) if video.thumbnail_url else None,
        duration=float(video.duration) if video.duration is not None else None,
        width=video.width,
        height=video.height,
        has_audio=video.has_audio,
        output_file_size=video.output_file_size,
        error_message=video.error_message,
        created_at=video.created_at,
        completed_at=video.completed_at,
        template=TemplateOut.model_validate(video.template) if video.template else None,
        job=JobOut.model_validate(video.latest_job) if video.latest_job else None,
    )
    return out


def _enqueue_render(video_id: uuid.UUID, job_id: uuid.UUID) -> None:
    celery_app.send_task(RENDER_TASK, args=[str(video_id), str(job_id)], queue=RENDER_QUEUE)


def _validated_form(**fields: object) -> VideoCreateForm:
    """Run the multipart fields through the schema, surfacing a 422 envelope."""
    try:
        return VideoCreateForm.model_validate(fields)
    except PydanticValidationError as exc:
        details = [
            {"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        raise ValidationError("Invalid request payload", details=details) from exc


def _validated_captions(raw: str | None) -> list[dict[str, Any]]:
    """Parse the `captions` multipart field, which carries JSON as a string.

    Multipart has no native array type, so the timeline editor sends the track
    as one JSON blob. Absent or empty means "no captions" - the classic
    templates never send it.
    """
    if not raw or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "Captions must be valid JSON",
            details=[{"field": "captions", "message": str(exc)}],
        ) from exc

    if not isinstance(parsed, list):
        raise ValidationError(
            "Captions must be a list",
            details=[{"field": "captions", "message": "expected a list of captions"}],
        )

    try:
        track = [Caption.model_validate(item) for item in parsed]
        validate_caption_track(track)
    except PydanticValidationError as exc:
        details = [
            {"field": "captions." + ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        raise ValidationError("Invalid captions", details=details) from exc
    except ValueError as exc:
        raise ValidationError(
            str(exc), details=[{"field": "captions", "message": str(exc)}]
        ) from exc

    return [caption.model_dump() for caption in track]


@router.post("", response_model=VideoOut, status_code=201)
@limiter.limit(settings.upload_rate_limit)
def create_video(
    request: Request,
    user: CurrentUser,
    db: DbSession,
    video_file: Annotated[UploadFile, File()],
    text_content: Annotated[str, Form()],
    template_id: Annotated[str, Form()],
    title: Annotated[str | None, Form()] = None,
    auto_render: Annotated[bool, Form()] = True,
    captions: Annotated[str | None, Form()] = None,
    quality: Annotated[str, Form()] = "balanced",
) -> VideoOut:
    payload = _validated_form(
        title=title,
        text_content=text_content,
        template_id=template_id,
        auto_render=auto_render,
        quality=quality,
    )
    caption_track = _validated_captions(captions)

    template = db.get(Template, payload.template_id)
    if template is None or not template.is_active:
        raise NotFoundError("Selected template was not found")

    validated = validate_video_upload(
        video_file,
        # Duration drives render cost, and a guest is an anonymous caller who
        # can be one of many. Registered users keep the full ceiling.
        max_duration_seconds=(
            settings.guest_max_video_duration_seconds if user.is_guest else None
        ),
    )
    try:
        storage = get_storage()
        input_key = build_key("users", str(user.id), "inputs", extension=validated.extension)
        storage.save_file(input_key, validated.temp_path, content_type=validated.content_type)
    finally:
        validated.cleanup()

    video = Video(
        user_id=user.id,
        template_id=template.id,
        title=payload.title,
        text_content=payload.text_content,
        captions=caption_track or None,
        quality=payload.quality,
        input_file_url=input_key,
        input_file_size=validated.size,
        width=validated.media.width if validated.media else None,
        height=validated.media.height if validated.media else None,
        duration=validated.media.duration if validated.media else None,
        has_audio=validated.media.has_audio if validated.media else False,
        status=VideoStatus.QUEUED if payload.auto_render else VideoStatus.DRAFT,
    )
    db.add(video)
    db.flush()

    job = RenderingJob(video_id=video.id, steps=initial_steps_payload())
    db.add(job)
    db.commit()
    db.refresh(video)

    if payload.auto_render:
        _enqueue_render(video.id, job.id)

    logger.info("video_created", extra={"user_id": str(user.id), "video_id": str(video.id)})
    return serialize_video(video)


@router.get("", response_model=VideoListOut)
def list_videos(
    user: CurrentUser,
    db: DbSession,
    status: Literal["all", "processing", "completed", "failed"] = "all",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
) -> VideoListOut:
    base = select(Video).where(Video.user_id == user.id)
    if status != "all":
        base = base.where(Video.status.in_(_STATUS_FILTERS[status]))

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.options(selectinload(Video.template), selectinload(Video.jobs))
        .order_by(Video.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return VideoListOut(
        items=[serialize_video(v) for v in rows], total=total, page=page, page_size=page_size
    )


@router.get("/{video_id}", response_model=VideoOut)
def get_video(video: OwnedVideo) -> VideoOut:
    return serialize_video(video)


@router.delete("/{video_id}", response_model=MessageResponse)
def delete_video(video: OwnedVideo, db: DbSession) -> MessageResponse:
    storage = get_storage()
    for key in (video.input_file_url, video.output_file_url, video.thumbnail_url):
        if key:
            try:
                storage.delete(key)
            except Exception:  # noqa: BLE001 - deletion must not block removing the record
                logger.warning("video_asset_delete_failed", extra={"key": key})
    db.delete(video)
    db.commit()
    return MessageResponse(message="Video deleted")


@router.post("/{video_id}/render", response_model=VideoOut)
def render_video_endpoint(video: OwnedVideo, db: DbSession) -> VideoOut:
    active_job = next(
        (j for j in video.jobs if j.status in (JobStatus.QUEUED, JobStatus.PROCESSING)), None
    )
    if active_job is not None:
        raise ConflictError("A render is already in progress for this video")
    if not video.input_file_url:
        raise ValidationError("This video has no uploaded source file")

    previous_attempt = video.jobs[0].attempt if video.jobs else 0
    job = RenderingJob(
        video_id=video.id, steps=initial_steps_payload(), attempt=previous_attempt + 1
    )
    video.status = VideoStatus.QUEUED
    video.error_message = None
    db.add(job)
    db.commit()
    db.refresh(video)

    _enqueue_render(video.id, job.id)
    logger.info("video_render_requeued", extra={"video_id": str(video.id)})
    return serialize_video(video)


@router.get("/{video_id}/download")
def download_video(video: OwnedVideo) -> StreamingResponse:
    if video.status != VideoStatus.COMPLETED or not video.output_file_url:
        raise ConflictError("This video has not finished rendering yet")

    storage = get_storage()
    stream = storage.open_stream(video.output_file_url)
    return StreamingResponse(
        stream,
        media_type="video/mp4",
        headers={"Content-Disposition": _content_disposition(video.title)},
    )


def _content_disposition(title: str | None) -> str:
    """Build an RFC 6266 Content-Disposition for a possibly non-ASCII title.

    HTTP headers are latin-1 only, so an Arabic title placed directly in
    ``filename=`` raises UnicodeEncodeError and kills the response mid-flight.
    We therefore send an ASCII-safe ``filename`` plus a UTF-8 ``filename*``,
    which every current browser prefers.
    """
    stem = (title or "").strip() or "aseelo-video"
    # Drop quotes, backslashes and control characters that would break the header.
    stem = "".join(ch for ch in stem if ch.isprintable() and ch not in '"\\')[:80].strip()
    stem = stem or "aseelo-video"

    ascii_stem = stem.encode("ascii", "ignore").decode("ascii").strip() or "aseelo-video"
    quoted = quote(f"{stem}.mp4", safe="")
    return f"attachment; filename=\"{ascii_stem}.mp4\"; filename*=UTF-8''{quoted}"
