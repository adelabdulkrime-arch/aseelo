"""Pipeline stage definitions and job progress tracking.

Progress is derived from *real* work: each stage owns a slice of the 0-100 range
and the rendering stage is driven by FFmpeg's own ``-progress`` output. Nothing
here is a decorative timer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.logging_config import get_logger, job_id_var
from app.models import JobStatus, RenderingJob

logger = get_logger(__name__)


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    label_ar: str
    start: int
    end: int


STEPS: tuple[Step, ...] = (
    Step("upload", "Upload", "الرفع", 0, 5),
    Step("validation", "Validation", "التحقق", 5, 14),
    Step("video_processing", "Video processing", "معالجة الفيديو", 14, 26),
    Step("brand", "Brand application", "تطبيق الهوية", 26, 36),
    Step("text", "Text", "النص", 36, 46),
    Step("logo", "Logo", "الشعار", 46, 52),
    Step("rendering", "Rendering", "المعالجة النهائية", 52, 92),
    Step("quality_check", "Quality check", "فحص الجودة", 92, 100),
)

STEP_BY_KEY = {step.key: step for step in STEPS}


def initial_steps_payload(first_done: str | None = "upload") -> dict[str, Any]:
    """Build the JSONB payload stored on ``rendering_jobs.steps``."""
    items = []
    for step in STEPS:
        status = "done" if first_done and step.key == first_done else "pending"
        items.append(
            {
                "key": step.key,
                "label": step.label,
                "label_ar": step.label_ar,
                "status": status,
                "progress": 100 if status == "done" else 0,
            }
        )
    return {"items": items}


class JobProgress:
    """Persists stage transitions and progress for one rendering job."""

    def __init__(self, db: Session, job: RenderingJob, *, commit_threshold: int = 1):
        self.db = db
        self.job = job
        self._commit_threshold = commit_threshold
        self._last_committed = job.progress
        job_id_var.set(str(job.id))
        if not job.steps or "items" not in job.steps:
            job.steps = initial_steps_payload()

    # ---------------- internals ----------------
    def _items(self) -> list[dict[str, Any]]:
        return list(self.job.steps.get("items", []))

    def _write_items(self, items: list[dict[str, Any]]) -> None:
        # Reassign so SQLAlchemy detects the JSONB mutation.
        self.job.steps = {"items": items}

    def _set_item(self, key: str, **updates: Any) -> None:
        items = self._items()
        for item in items:
            if item["key"] == key:
                item.update(updates)
                break
        self._write_items(items)

    def _persist(self, *, force: bool = False) -> None:
        if force or abs(self.job.progress - self._last_committed) >= self._commit_threshold:
            self._last_committed = self.job.progress
            self.db.commit()

    # ---------------- API ----------------
    def begin(self) -> None:
        self.job.status = JobStatus.PROCESSING
        self.job.started_at = self.job.started_at or datetime.now(UTC)
        self.job.error_message = None
        self._persist(force=True)

    def start_step(self, key: str) -> None:
        step = STEP_BY_KEY[key]
        self.job.current_step = key
        self.job.progress = max(self.job.progress, step.start)
        self._set_item(key, status="active", progress=0)
        logger.info("job_step_start", extra={"step": key, "progress": self.job.progress})
        self._persist(force=True)

    def step_fraction(self, key: str, fraction: float) -> None:
        """Report intra-stage progress (0.0-1.0), e.g. FFmpeg encode position."""
        step = STEP_BY_KEY[key]
        fraction = max(0.0, min(1.0, fraction))
        span = step.end - step.start
        self.job.progress = min(step.end, int(step.start + span * fraction))
        self._set_item(key, status="active", progress=int(fraction * 100))
        self._persist()

    def complete_step(self, key: str) -> None:
        step = STEP_BY_KEY[key]
        self.job.progress = max(self.job.progress, step.end)
        self._set_item(key, status="done", progress=100)
        self._persist(force=True)

    def fail(self, message: str, *, key: str | None = None) -> None:
        key = key or self.job.current_step
        if key in STEP_BY_KEY:
            self._set_item(key, status="failed")
        self.job.status = JobStatus.FAILED
        self.job.error_message = message[:2000]
        self.job.completed_at = datetime.now(UTC)
        logger.error("job_failed", extra={"step": key, "reason": message[:500]})
        self._persist(force=True)

    def cancel(self, message: str = "Cancelled by user") -> None:
        self.job.status = JobStatus.CANCELLED
        self.job.error_message = message
        self.job.completed_at = datetime.now(UTC)
        self._persist(force=True)

    def finish(self) -> None:
        items = self._items()
        for item in items:
            item["status"] = "done"
            item["progress"] = 100
        self._write_items(items)
        self.job.status = JobStatus.COMPLETED
        self.job.progress = 100
        self.job.current_step = STEPS[-1].key
        self.job.completed_at = datetime.now(UTC)
        logger.info("job_completed")
        self._persist(force=True)
