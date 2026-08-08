# API reference

Base URL: `http://localhost:8000`. Interactive docs (OpenAPI) at `/docs`.

All endpoints below except `/health`, `/api/auth/guest` and `/api/templates` require
`Authorization: Bearer <access_token>`.

## Errors

Every error uses one envelope:

```json
{
  "error": { "code": "not_found", "message": "Video not found" },
  "request_id": "8f1c…"
}
```

Validation errors add `error.details` as a list of `{field, message}`.

| Code | HTTP | Meaning |
| --- | --- | --- |
| `validation_error` | 422 | Bad payload, unsupported file, failed media checks |
| `unauthorized` | 401 | Missing, malformed or expired token; bad credentials |
| `forbidden` | 403 | Account disabled, or admin-only route |
| `not_found` | 404 | Missing — **or owned by another user** |
| `conflict` | 409 | Render already running; download before completion |
| `payload_too_large` | 413 | Upload exceeded `MAX_UPLOAD_SIZE` / `MAX_LOGO_SIZE` |
| `rate_limited` | 429 | Auth or upload rate limit tripped |
| `internal_error` | 500 | Unhandled; the message is generic in production |

## Auth

There is no login. `/api/auth/guest` is the only way to get a session.

### `POST /api/auth/guest` → 201

No body. Mints a throwaway account and a default brand profile, and returns a `TokenResponse`:

```json
{
  "access_token": "eyJ…",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": { "id": "…", "name": "Guest", "email": "guest-…@guest.aseelo.example", "role": "USER", "is_active": true, "is_guest": true, "created_at": "…" }
}
```

Returns 403 `forbidden` when `GUEST_SESSIONS_ENABLED` is off (an emergency brake for a host that
cannot keep up with render load, not a normal state). Rate limited by `GUEST_RATE_LIMIT` (default
`2/hour`) — each call is a real row and a real render slot.

Guest accounts older than `GUEST_RETENTION_DAYS` (default 7) are reclaimed by
`scripts.prune_guests`, which deletes the account, its videos, and their stored files.

### `GET /api/auth/me` → 200

Returns the authenticated `UserOut`.

## Brand

### `GET /api/brand` → 200

Returns the caller's `BrandOut`, creating a default profile if none exists. `logo_url` is
returned as a browser-reachable URL, not a storage key.

### `PUT /api/brand` → 200

Partial update. Any subset of: `brand_name`, `primary_color`, `secondary_color`, `accent_color`,
`font`, `phone`, `whatsapp`, `website`, `social_media`, `address`, `tagline`.

- Colours must be `#RGB`, `#RRGGBB` or `#RRGGBBAA`; they're normalised to uppercase.
- A bare domain in `website` gets an `https://` prefix.
- `social_media` accepts at most 12 entries; keys are lowercased and blanks dropped.

### `POST /api/brand/logo` → 200

Multipart `file`. PNG/JPEG/WEBP, ≤ `MAX_LOGO_SIZE` (5 MB), ≤ 8000 px per side. Validated by
extension, declared MIME, magic bytes and a Pillow decode. Replacing a logo deletes the old
object. Returns the updated `BrandOut`.

## Templates

### `GET /api/templates` → 200

List of active `TemplateOut`, ordered by `sort_order`. `configuration` is the full JSONB template
document (canvas, safe area, background, layers) — see [video-engine.md](video-engine.md).

## Videos

### `POST /api/videos` → 201

Multipart form:

| Field | Required | Notes |
| --- | --- | --- |
| `video_file` | yes | mp4/mov/avi/mkv/webm/mpeg/m4v, ≤ `MAX_UPLOAD_SIZE` (512 MB), 1–180 s, ≥144 px short edge |
| `text_content` | yes | 1–600 chars, ≤10 lines. Arabic, English or mixed |
| `template_id` | yes | UUID from `GET /api/templates` |
| `title` | no | ≤160 chars |
| `auto_render` | no | default `true`; `false` leaves the video in `DRAFT` |

Creates the video and a `QUEUED` rendering job, enqueues the Celery task, and returns
immediately. Returns `VideoOut` with an embedded `job`. Rate limited (`UPLOAD_RATE_LIMIT`,
default 30/hour).

### `GET /api/videos` → 200

Query: `status` (`all` | `processing` | `completed` | `failed`), `page` (≥1), `page_size`
(1–50, default 20). Returns `{items, total, page, page_size}`, newest first, scoped to the caller.

### `GET /api/videos/{id}` → 200

Single `VideoOut` including `template` and the latest `job`.

```json
{
  "id": "…", "title": "Ramadan promo", "text_content": "عروضنا الجديدة متوفرة الآن",
  "status": "COMPLETED", "output_file_url": "http://…/media/users/…/outputs/….mp4",
  "thumbnail_url": "http://…", "duration": 12.4, "width": 1080, "height": 1920,
  "has_audio": true, "output_file_size": 4180221, "error_message": null,
  "created_at": "…", "completed_at": "…",
  "template": { "…": "…" },
  "job": { "id": "…", "status": "COMPLETED", "progress": 100, "current_step": "quality_check", "steps": [ … ] }
}
```

### `DELETE /api/videos/{id}` → 200

Deletes the record and its input, output and thumbnail objects. A storage failure is logged but
does not block record removal.

### `POST /api/videos/{id}/render` → 200

Queues a fresh attempt (`attempt` increments). Returns 409 if a job is already `QUEUED` or
`PROCESSING`, 422 if there is no source file. Use this to retry a `FAILED` video.

### `GET /api/videos/{id}/download` → 200

Streams the flattened MP4 as an attachment. Returns 409 unless the video is `COMPLETED`.

## Jobs

### `GET /api/jobs/{id}` → 200

Poll this for progress. Scoped to the owner (404 otherwise).

```json
{
  "id": "…", "video_id": "…", "status": "PROCESSING", "progress": 63,
  "current_step": "rendering", "error_message": null, "attempt": 1,
  "created_at": "…", "started_at": "…", "completed_at": null,
  "steps": [
    {"key": "upload", "label": "Upload", "label_ar": "الرفع", "status": "done", "progress": 100},
    {"key": "rendering", "label": "Rendering", "label_ar": "المعالجة النهائية", "status": "active", "progress": 28},
    {"key": "quality_check", "label": "Quality check", "label_ar": "فحص الجودة", "status": "pending", "progress": 0}
  ]
}
```

Statuses: `QUEUED`, `PROCESSING`, `COMPLETED`, `FAILED`, `CANCELLED`. Stages, in order:
`upload`, `validation`, `video_processing`, `brand`, `text`, `logo`, `rendering`,
`quality_check`. On failure the stage is marked `failed` and `error_message` carries a
user-readable reason.

## Dashboard

### `GET /api/dashboard` → 200

```json
{
  "total_videos": 12, "videos_today": 3, "processing_jobs": 1,
  "completed_videos": 10, "failed_videos": 1,
  "storage_used_bytes": 284736512,
  "recent_videos": [ /* 5 most recent VideoOut */ ]
}
```

## Health

### `GET /health` → 200

`{"status": "ok"}`. Used by the compose healthcheck; requires no auth.
