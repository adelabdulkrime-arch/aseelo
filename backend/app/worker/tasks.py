"""Celery task: the real, deterministic FFmpeg rendering pipeline.

One task renders exactly one job. Progress is persisted through
:class:`~app.services.pipeline.JobProgress` so the frontend can poll a real
state machine - nothing here is a decorative timer.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from celery import Task
from celery.utils.log import get_task_logger

from app.database import session_scope
from app.models import JobStatus, RenderingJob, Video, VideoStatus
from app.services.pipeline import JobProgress
from app.storage import Storage, build_key, get_storage
from app.video import compose
from app.video import render as render_mod
from app.video.probe import MediaInfo, ProbeError, probe
from app.video.quality import validate_output
from app.worker.celery_app import RENDER_TASK, celery_app

logger = get_task_logger(__name__)


class RenderTaskError(Exception):
    """A pipeline failure with a message safe to show to the end user."""


@celery_app.task(name=RENDER_TASK, bind=True)
def render_video(self: Task, video_id: str, job_id: str) -> None:
    with session_scope() as db:
        job = db.get(RenderingJob, uuid.UUID(job_id))
        video = db.get(Video, uuid.UUID(video_id))
        if job is None or video is None:
            logger.error(
                "render_task_missing_row", extra={"video_id": video_id, "job_id": job_id}
            )
            return
        if job.status == JobStatus.CANCELLED:
            return

        job.celery_task_id = self.request.id
        progress = JobProgress(db, job)
        progress.begin()
        video.status = VideoStatus.PROCESSING
        db.commit()

        storage = get_storage()
        workdir = Path(tempfile.mkdtemp(prefix="aseelo-render-"))
        try:
            _run_pipeline(video, job, progress, storage, workdir)
        except Exception as exc:  # noqa: BLE001 - every failure must be recorded, never silent
            message = (
                str(exc)
                if isinstance(exc, RenderTaskError | ProbeError)
                else f"Rendering failed unexpectedly: {exc}"
            )
            logger.exception(
                "render_pipeline_failed", extra={"video_id": video_id, "job_id": job_id}
            )
            progress.fail(message[:2000])
            video.status = VideoStatus.FAILED
            video.error_message = message[:2000]
            db.commit()
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


def _run_pipeline(
    video: Video,
    job: RenderingJob,
    progress: JobProgress,
    storage: Storage,
    workdir: Path,
) -> None:
    db = progress.db
    input_path = workdir / f"input{Path(video.input_file_url).suffix or '.mp4'}"
    output_path = workdir / "output.mp4"
    thumbnail_path = workdir / "thumbnail.jpg"
    overlay_path = workdir / "overlay.png"

    # ---------------- validation / probe ----------------
    progress.start_step("validation")
    storage.download_to(video.input_file_url, input_path)
    try:
        media: MediaInfo = probe(input_path)
    except ProbeError as exc:
        raise RenderTaskError(f"The uploaded video could not be re-validated: {exc}") from exc
    progress.complete_step("validation")

    # ---------------- video processing ----------------
    progress.start_step("video_processing")
    template = video.template
    if template is None or not template.configuration:
        raise RenderTaskError("The selected template is no longer available")
    config = template.configuration
    background_cfg = config.get("background") or {}
    progress.complete_step("video_processing")

    # ---------------- brand ----------------
    progress.start_step("brand")
    brand = video.user.brand_profile
    logo_local: Path | None = None
    if brand and brand.logo_url:
        logo_local = workdir / "logo.png"
        try:
            storage.download_to(brand.logo_url, logo_local)
        except Exception:  # noqa: BLE001 - a missing/broken logo must not fail the render
            logger.warning("brand_logo_download_failed", extra={"video_id": str(video.id)})
            logo_local = None
    brand_context = (
        compose.BrandContext.from_model(brand, logo_path=logo_local)
        if brand
        else compose.BrandContext(logo_path=logo_local)
    )
    video.brand_snapshot = brand_context.to_snapshot()
    db.commit()
    progress.complete_step("brand")

    # ---------------- text + logo (one flattened overlay) ----------------
    progress.start_step("text")
    result = compose.build_overlay(config, brand_context, video.text_content, video.title)
    result.image.save(overlay_path)
    progress.complete_step("text")
    progress.start_step("logo")
    progress.complete_step("logo")

    # ---------------- rendering ----------------
    progress.start_step("rendering")
    canvas_w, canvas_h = compose.canvas_size(config)
    request = render_mod.RenderRequest(
        input_path=input_path,
        overlay_path=overlay_path,
        output_path=output_path,
        duration=media.duration,
        has_audio=media.has_audio,
        background_mode=background_cfg.get("mode", "cover"),
        blur_sigma=float(background_cfg.get("blur_sigma", 25.0)),
        width=canvas_w,
        height=canvas_h,
    )
    try:
        render_result = render_mod.render(
            request, progress=lambda fraction: progress.step_fraction("rendering", fraction)
        )
    except render_mod.RenderError as exc:
        raise RenderTaskError(str(exc)) from exc
    progress.complete_step("rendering")

    # ---------------- quality check ----------------
    progress.start_step("quality_check")
    report = validate_output(
        output_path,
        expected_width=request.width,
        expected_height=request.height,
        expected_duration=media.duration,
        source_had_audio=media.has_audio,
    )
    if not report.ok:
        raise RenderTaskError(f"The rendered video failed quality validation: {report.summary}")

    generated_thumbnail = True
    try:
        render_mod.generate_thumbnail(output_path, thumbnail_path)
    except render_mod.RenderError as exc:
        logger.warning("thumbnail_generation_failed", extra={"error": str(exc)})
        generated_thumbnail = False
    progress.complete_step("quality_check")

    # ---------------- persist output ----------------
    output_key = build_key("users", str(video.user_id), "outputs", extension="mp4")
    storage.save_file(output_key, output_path, content_type="video/mp4")
    video.output_file_url = output_key
    video.output_file_size = render_result.size_bytes
    video.duration = report.info.duration if report.info else media.duration
    video.width = request.width
    video.height = request.height
    video.has_audio = report.info.has_audio if report.info else media.has_audio

    if generated_thumbnail and thumbnail_path.exists():
        thumb_key = build_key("users", str(video.user_id), "thumbnails", extension="jpg")
        storage.save_file(thumb_key, thumbnail_path, content_type="image/jpeg")
        video.thumbnail_url = thumb_key

    video.status = VideoStatus.COMPLETED
    video.completed_at = datetime.now(UTC)
    progress.finish()
