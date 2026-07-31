"""Video API: creation, validation, ownership isolation, job lifecycle.

Celery dispatch is stubbed so these tests exercise the HTTP layer without a
broker; the rendering pipeline itself is covered by test_render.py and the
end-to-end smoke test.
"""

from __future__ import annotations

import io
import subprocess
import uuid

import pytest

from app.config import settings
from app.models import JobStatus, VideoStatus

ARABIC = "عروضنا الجديدة متوفرة الآن"


@pytest.fixture(autouse=True)
def _no_broker(monkeypatch):
    """Record enqueued renders instead of talking to Redis."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.routers.videos._enqueue_render",
        lambda video_id, job_id: sent.append((str(video_id), str(job_id))),
    )
    return sent


@pytest.fixture(scope="module")
def clip(tmp_path_factory) -> bytes:
    path = tmp_path_factory.mktemp("media") / "clip.mp4"
    subprocess.run(
        [
            settings.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=640x480:rate=30:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True, capture_output=True, timeout=180,
    )
    return path.read_bytes()


def _create(client, user, template, clip, **overrides):
    data = {
        "title": "Test video",
        "text_content": ARABIC,
        "template_id": str(template.id),
        **overrides,
    }
    return client.post(
        "/api/videos",
        headers=user["headers"],
        data=data,
        files={"video_file": ("clip.mp4", clip, "video/mp4")},
    )


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------
def test_create_video_queues_a_job(client, user, template, clip, _no_broker):
    response = _create(client, user, template, clip)
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["status"] == VideoStatus.QUEUED.value
    assert body["text_content"] == ARABIC
    assert body["template"]["id"] == str(template.id)
    assert body["job"]["status"] == JobStatus.QUEUED.value
    assert len(body["job"]["steps"]) == 8
    assert _no_broker == [(body["id"], body["job"]["id"])]


def test_create_video_without_auto_render_stays_draft(client, user, template, clip, _no_broker):
    response = _create(client, user, template, clip, auto_render="false")
    assert response.status_code == 201
    assert response.json()["status"] == VideoStatus.DRAFT.value
    assert _no_broker == []


def test_create_video_requires_auth(client, template, clip):
    response = client.post(
        "/api/videos",
        data={"text_content": ARABIC, "template_id": str(template.id)},
        files={"video_file": ("clip.mp4", clip, "video/mp4")},
    )
    assert response.status_code == 401


def test_create_video_rejects_unknown_template(client, user, clip):
    response = client.post(
        "/api/videos",
        headers=user["headers"],
        data={"text_content": ARABIC, "template_id": str(uuid.uuid4())},
        files={"video_file": ("clip.mp4", clip, "video/mp4")},
    )
    assert response.status_code == 404


def test_create_video_rejects_empty_text(client, user, template, clip):
    assert _create(client, user, template, clip, text_content="   ").status_code == 422


def test_create_video_rejects_a_non_video_file(client, user, template):
    response = client.post(
        "/api/videos",
        headers=user["headers"],
        data={"text_content": ARABIC, "template_id": str(template.id)},
        files={"video_file": ("clip.mp4", b"not a video at all", "video/mp4")},
    )
    assert response.status_code == 422


def test_create_video_rejects_a_disguised_extension(client, user, template, clip):
    response = client.post(
        "/api/videos",
        headers=user["headers"],
        data={"text_content": ARABIC, "template_id": str(template.id)},
        files={"video_file": ("clip.exe", clip, "video/mp4")},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Listing / detail / ownership
# ---------------------------------------------------------------------------
def test_list_returns_only_own_videos(client, user, other_user, template, clip):
    _create(client, user, template, clip)

    mine = client.get("/api/videos", headers=user["headers"]).json()
    theirs = client.get("/api/videos", headers=other_user["headers"]).json()
    assert mine["total"] == 1
    assert theirs["total"] == 0


def test_list_filters_by_status(client, user, template, clip):
    _create(client, user, template, clip)
    processing = client.get("/api/videos?status=processing", headers=user["headers"]).json()
    completed = client.get("/api/videos?status=completed", headers=user["headers"]).json()
    assert processing["total"] == 1
    assert completed["total"] == 0


def test_other_users_video_is_404_not_403(client, user, other_user, template, clip):
    video_id = _create(client, user, template, clip).json()["id"]
    response = client.get(f"/api/videos/{video_id}", headers=other_user["headers"])
    assert response.status_code == 404


def test_other_user_cannot_delete(client, user, other_user, template, clip):
    video_id = _create(client, user, template, clip).json()["id"]
    assert client.delete(f"/api/videos/{video_id}", headers=other_user["headers"]).status_code == 404
    assert client.get(f"/api/videos/{video_id}", headers=user["headers"]).status_code == 200


def test_delete_removes_the_video(client, user, template, clip):
    video_id = _create(client, user, template, clip).json()["id"]
    assert client.delete(f"/api/videos/{video_id}", headers=user["headers"]).status_code == 200
    assert client.get(f"/api/videos/{video_id}", headers=user["headers"]).status_code == 404


# ---------------------------------------------------------------------------
# Render / download / jobs
# ---------------------------------------------------------------------------
def test_rerender_is_rejected_while_a_job_is_active(client, user, template, clip):
    video_id = _create(client, user, template, clip).json()["id"]
    response = client.post(f"/api/videos/{video_id}/render", headers=user["headers"])
    assert response.status_code == 409


def test_download_is_rejected_before_completion(client, user, template, clip):
    video_id = _create(client, user, template, clip).json()["id"]
    assert client.get(f"/api/videos/{video_id}/download", headers=user["headers"]).status_code == 409


@pytest.mark.parametrize(
    "title",
    ["اختبار الواجهة", 'weird "quoted" name', "عرض خاص - 50% OFF", None],
)
def test_download_header_is_latin1_encodable(client, user, template, clip, db, title):
    """HTTP headers are latin-1: an Arabic title must not break the response.

    Putting a non-ASCII title straight into Content-Disposition raises
    UnicodeEncodeError and aborts the download mid-flight.
    """
    from app.routers.videos import _content_disposition

    header = _content_disposition(title)
    header.encode("latin-1")  # must not raise
    assert header.startswith("attachment; filename=")
    assert "filename*=UTF-8''" in header


def test_download_of_a_completed_video_streams_mp4(client, user, template, clip, db):
    from app.models import Video, VideoStatus
    from app.storage import build_key, get_storage

    video_id = _create(client, user, template, clip, title="اختبار الواجهة").json()["id"]

    # Stand in for a finished render: store real bytes and mark the row COMPLETED.
    key = build_key("users", str(user["user"]["id"]), "outputs", extension="mp4")
    get_storage().save_stream(key, io.BytesIO(clip), content_type="video/mp4")
    video = db.get(Video, uuid.UUID(video_id))
    video.status = VideoStatus.COMPLETED
    video.output_file_url = key
    db.commit()

    response = client.get(f"/api/videos/{video_id}/download", headers=user["headers"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.content == clip
    response.headers["content-disposition"].encode("latin-1")


def test_job_polling_is_scoped_to_the_owner(client, user, other_user, template, clip):
    job_id = _create(client, user, template, clip).json()["job"]["id"]

    mine = client.get(f"/api/jobs/{job_id}", headers=user["headers"])
    assert mine.status_code == 200
    assert mine.json()["status"] == JobStatus.QUEUED.value

    assert client.get(f"/api/jobs/{job_id}", headers=other_user["headers"]).status_code == 404


# ---------------------------------------------------------------------------
# Templates / dashboard
# ---------------------------------------------------------------------------
def test_templates_are_listed(client, template):
    response = client.get("/api/templates")
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 1
    assert all(t["configuration"]["canvas"] == {"width": 1080, "height": 1920} for t in body)


def test_dashboard_counts_reflect_created_videos(client, user, template, clip):
    _create(client, user, template, clip)
    stats = client.get("/api/dashboard", headers=user["headers"]).json()
    assert stats["total_videos"] == 1
    assert stats["videos_today"] == 1
    assert stats["processing_jobs"] == 1
    assert stats["storage_used_bytes"] > 0
    assert len(stats["recent_videos"]) == 1


def test_dashboard_requires_auth(client):
    assert client.get("/api/dashboard").status_code == 401
