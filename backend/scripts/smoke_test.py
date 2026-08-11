"""End-to-end smoke test against a running ASEELO stack.

Exercises the full Definition of Done: register -> login -> brand + logo ->
upload a real clip with Arabic text -> job queued -> Celery worker renders with
FFmpeg -> quality check -> COMPLETED -> download and verify the MP4.

    docker compose run --rm backend python -m scripts.smoke_test

Set ASEELO_API_URL to point somewhere other than http://backend:8000.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx
from PIL import Image

API = os.environ.get("ASEELO_API_URL", "http://backend:8000")
ARABIC_TEXT = "عروضنا الجديدة متوفرة الآن"
TIMEOUT_SECONDS = 300


def step(message: str) -> None:
    print(f"\n=== {message}", flush=True)


def fail(message: str) -> None:
    print(f"\nFAILED: {message}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def make_clip(path: Path) -> Path:
    """A real 6 s landscape clip with audio - the worker must convert it to 9:16."""
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=30:duration=6",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", "6",
            str(path),
        ],
        check=True, capture_output=True, timeout=180,
    )
    return path


def main() -> None:
    workdir = Path(tempfile.mkdtemp(prefix="aseelo-smoke-"))
    client = httpx.Client(base_url=API, timeout=120.0)

    step("Health check")
    health = client.get("/health")
    if health.status_code != 200:
        fail(f"/health returned {health.status_code}")
    print(f"  {health.json()}")

    step("Register")
    email = f"smoke-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Smoke Test",
            "email": email,
            "password": "SuperSecret123",
            "confirm_password": "SuperSecret123",
        },
    )
    if response.status_code != 201:
        fail(f"register returned {response.status_code}: {response.text}")
    print(f"  user {response.json()['user']['id']}")

    step("Login")
    response = client.post(
        "/api/auth/login", json={"email": email, "password": "SuperSecret123"}
    )
    if response.status_code != 200:
        fail(f"login returned {response.status_code}: {response.text}")
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    step("Configure brand")
    response = client.put(
        "/api/brand",
        headers=headers,
        json={
            "brand_name": "أصيلو",
            "primary_color": "#0F172A",
            "secondary_color": "#1E88E5",
            "accent_color": "#F5B700",
            "phone": "+964 770 000 0000",
            "whatsapp": "+964 771 111 1111",
            "website": "aseelo.example",
            "tagline": "From Idea to Content",
        },
    )
    if response.status_code != 200:
        fail(f"brand update returned {response.status_code}: {response.text}")
    print(f"  brand '{response.json()['brand_name']}'")

    step("Upload logo")
    logo = io.BytesIO()
    Image.new("RGBA", (512, 512), (245, 183, 0, 255)).save(logo, format="PNG")
    response = client.post(
        "/api/brand/logo",
        headers=headers,
        files={"file": ("logo.png", logo.getvalue(), "image/png")},
    )
    if response.status_code != 200:
        fail(f"logo upload returned {response.status_code}: {response.text}")
    print(f"  logo {response.json()['logo_url']}")

    step("List templates")
    response = client.get("/api/templates")
    templates = response.json()
    if response.status_code != 200 or not templates:
        fail(f"templates returned {response.status_code}: {response.text}")
    template = templates[0]
    print(f"  {len(templates)} templates; using '{template['name']}'")

    step("Create video (real 1920x1080 source, Arabic text)")
    clip = make_clip(workdir / "source.mp4")
    with clip.open("rb") as fh:
        response = client.post(
            "/api/videos",
            headers=headers,
            data={
                # Deliberately non-ASCII: it must survive the Content-Disposition
                # header on download, which latin-1 encoding would otherwise break.
                "title": "اختبار الدخان",
                "text_content": ARABIC_TEXT,
                "template_id": template["id"],
            },
            files={"video_file": ("source.mp4", fh, "video/mp4")},
        )
    if response.status_code != 201:
        fail(f"video create returned {response.status_code}: {response.text}")
    video = response.json()
    video_id, job_id = video["id"], video["job"]["id"]
    print(f"  video {video_id} status={video['status']} job={job_id}")

    step("Poll the job (worker + FFmpeg doing real work)")
    deadline = time.monotonic() + TIMEOUT_SECONDS
    last = None
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}", headers=headers).json()
        marker = (job["status"], job["current_step"], job["progress"])
        if marker != last:
            print(f"  {job['status']:<11} {job['current_step']:<17} {job['progress']:>3}%")
            last = marker
        if job["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            break
        time.sleep(1.5)
    else:
        fail(f"job did not finish within {TIMEOUT_SECONDS}s")

    if job["status"] != "COMPLETED":
        fail(f"job ended as {job['status']}: {job.get('error_message')}")

    step("Verify the completed video record")
    video = client.get(f"/api/videos/{video_id}", headers=headers).json()
    print(f"  status={video['status']} {video['width']}x{video['height']} "
          f"duration={video['duration']}s size={video['output_file_size']} bytes")
    if (video["width"], video["height"]) != (1080, 1920):
        fail(f"expected 1080x1920, got {video['width']}x{video['height']}")
    if not video["thumbnail_url"]:
        fail("no thumbnail was generated")

    step("Download and probe the flattened MP4")
    output = workdir / "downloaded.mp4"
    with client.stream("GET", f"/api/videos/{video_id}/download", headers=headers) as stream:
        if stream.status_code != 200:
            fail(f"download returned {stream.status_code}")
        with output.open("wb") as fh:
            for chunk in stream.iter_bytes():
                fh.write(chunk)
    print(f"  downloaded {output.stat().st_size} bytes")

    probed = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "stream=codec_type,codec_name,width,height", "-of", "json", str(output),
        ],
        capture_output=True, text=True, timeout=60, check=True,
    ).stdout
    streams = json.loads(probed)["streams"]
    video_stream = next((s for s in streams if s["codec_type"] == "video"), None)
    audio_stream = next((s for s in streams if s["codec_type"] == "audio"), None)
    print(f"  ffprobe: {video_stream} | {audio_stream}")

    if video_stream is None:
        fail("the downloaded file has no video stream")
    if video_stream["codec_name"] != "h264":
        fail(f"expected h264, got {video_stream['codec_name']}")
    if (video_stream["width"], video_stream["height"]) != (1080, 1920):
        fail(f"expected 1080x1920, got {video_stream['width']}x{video_stream['height']}")
    if audio_stream is None or audio_stream["codec_name"] != "aac":
        fail("source had audio but the download has no AAC track")

    step("Dashboard reflects the render")
    stats = client.get("/api/dashboard", headers=headers).json()
    print(f"  total={stats['total_videos']} completed={stats['completed_videos']} "
          f"storage={stats['storage_used_bytes']} bytes")
    if stats["completed_videos"] != 1:
        fail(f"dashboard shows {stats['completed_videos']} completed videos, expected 1")

    print("\nSMOKE TEST PASSED\n", flush=True)


if __name__ == "__main__":
    main()
