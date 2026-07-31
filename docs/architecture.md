# Architecture

## Services

| Service | Role |
| --- | --- |
| `backend` | FastAPI HTTP API. Validates uploads, owns the database, enqueues render jobs. Never renders. |
| `worker` | Celery worker. Runs the FFmpeg pipeline, one render at a time per process. |
| `postgres` | System of record: users, brands, templates, videos, jobs. |
| `redis` | Celery broker + result backend, and rate-limit storage. |
| `frontend` | Next.js PWA (not yet implemented). |
| `nginx` | Optional reverse proxy, enabled with the `proxy` compose profile. |

The API and the worker are the *same image* with different entrypoint arguments
(`entrypoint.sh api` vs `entrypoint.sh worker`), so the rendering code and the request-handling
code can never drift apart.

## Request flow

```
POST /api/videos  (multipart: text + template_id + video file)
  │
  ├─ stream upload to a temp file in bounded 1 MB chunks   (services/file_validation.py)
  ├─ check extension, declared MIME, magic bytes, ffprobe duration/resolution
  ├─ persist to storage under an opaque key                (storage/)
  ├─ INSERT videos + rendering_jobs
  ├─ celery.send_task("aseelo.render_video")               → redis
  └─ 201 Created  ← returns immediately; the HTTP request never waits on FFmpeg

Celery worker picks up the task                            (worker/tasks.py)
  ├─ download input to a scratch dir
  ├─ ffprobe re-validation
  ├─ compose the overlay PNG from template + brand         (video/compose.py)
  ├─ ffmpeg: normalise to 9:16, overlay, encode H.264/AAC  (video/render.py)
  ├─ ffprobe the output against the promised contract      (video/quality.py)
  ├─ upload MP4 + thumbnail, UPDATE videos/rendering_jobs
  └─ scratch dir removed in a finally block

GET /api/jobs/{id} ← the frontend polls this for real stage/progress state
```

Progress is not a timer. Each of the eight pipeline stages owns a slice of the 0–100 range
(`services/pipeline.py`), and the rendering slice is driven by parsing FFmpeg's own `-progress`
output stream.

## Layer model

The product spec defines a conceptual stack: video → background/FX → text → logo → contact →
brand elements → final overlay. Everything *above* the video is flattened by Pillow into a single
full-canvas RGBA PNG, so FFmpeg needs exactly one `overlay` filter.

Two consequences, both deliberate:

- The downloaded MP4 is genuinely flat. There are no editable layers to extract.
- Arabic text is rasterised by Pillow (HarfBuzz shaping via libraqm), not by FFmpeg's `drawtext`,
  which has no shaping or bidi support and would render Arabic as disconnected reversed letters.

## Data model

```
users ─┬─< brand_profiles   (1:1, cascade delete)
       └─< videos ──< rendering_jobs   (cascade delete)
                └─> templates (SET NULL on delete)
```

- `templates.configuration` is JSONB. Templates are *data*, not code — adding one is an INSERT,
  and the renderer never changes. See [video-engine.md](video-engine.md).
- `videos.brand_snapshot` is JSONB, written at render time. Editing your brand later does not
  retroactively change what an already-rendered video claims to contain.
- `rendering_jobs.steps` is JSONB holding the per-stage UI state (label, Arabic label, status,
  progress) so the frontend renders the checklist without duplicating pipeline knowledge.

Indexes cover the real access patterns: `(user_id, created_at)` for the library, `(user_id,
status)` for the filter tabs, `(video_id, created_at)` for a video's job history.

## Storage abstraction

Business logic only ever handles opaque keys like `users/<uuid>/outputs/<uuid>.mp4`. The
`Storage` ABC (`storage/base.py`) has two implementations — local disk and S3-compatible
(AWS/R2/MinIO). Original filenames are never used as paths; `sanitize_key()` rejects absolute
paths, `..`, backslashes and anything outside `[A-Za-z0-9._-]`, and `LocalStorage` re-verifies
containment after resolution.

## Security

- bcrypt with a SHA-256 pre-hash, so long multi-byte (e.g. Arabic) passwords aren't silently
  truncated at bcrypt's 72-byte limit.
- JWT bearer tokens, verified with a required `exp` and a `type` claim check.
- Ownership is enforced in a dependency (`deps.get_owned_video`), which returns **404, not 403**,
  for another user's resource so IDs aren't enumerable.
- Uploads are validated on extension, declared MIME, file signature, size, duration and
  resolution — and streamed, never buffered whole.
- Rate limits on auth and upload endpoints, keyed by user when authenticated, IP otherwise.
- Structured JSON logs carry request/user/video/job IDs and redact anything password- or
  token-shaped.

## Scaling

The worker is stateless and horizontally scalable (`docker compose up --scale worker=4`). The
API is too, once storage is S3 rather than a local volume. `worker_prefetch_multiplier=1` plus
`task_acks_late` means a crashed worker's job is redelivered rather than lost, and a long render
never blocks a queued one behind it.
