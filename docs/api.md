# API reference

Base URL: `http://localhost:8000`. Interactive docs (OpenAPI) at `/docs`.

All endpoints below except `/health`, `/api/auth/register`, `/api/auth/login`,
`/api/auth/setup-account`, `/api/auth/forgot-password`, `/api/auth/reset-password` and
`/api/templates` require `Authorization: Bearer <access_token>`.

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
| `conflict` | 409 | Email taken; render already running; download before completion |
| `payload_too_large` | 413 | Upload exceeded `MAX_UPLOAD_SIZE` / `MAX_LOGO_SIZE` |
| `rate_limited` | 429 | Auth or upload rate limit tripped |
| `internal_error` | 500 | Unhandled; the message is generic in production |

## Auth

### `POST /api/auth/register` → 201

Body: `name`, `email`, `password` (≥8 chars), `confirm_password`.
Creates the user *and* a default brand profile. Returns a `TokenResponse`.

```json
{
  "access_token": "eyJ…",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": { "id": "…", "name": "…", "email": "…", "role": "USER", "is_active": true, "created_at": "…" }
}
```

Returns 403 `forbidden` when `GUEST_SESSIONS_ENABLED` is off — the visitor is expected to sign in
instead. Rate limited by `GUEST_RATE_LIMIT` (default `30/hour`) — this caps session creation, not
rendering: a session on its own queues nothing. It exists so one IP cannot fill `users` with spam
rows, not to protect the render queue, which `UPLOAD_RATE_LIMIT` on `POST /api/videos` covers
separately. A normal visitor calls this once per browser; `AuthProvider` only calls it again when
the stored token is gone.

### `POST /api/auth/login` → 200

Body: `email`, `password`. Same `TokenResponse`. Returns 401 for both an unknown email and a
wrong password — the responses are indistinguishable on purpose.

### `POST /api/auth/setup-account` → 201

Body: `charge_id`, `email`, `password` (≥8 chars). Redeems a paid charge into an account:
creates the user and a default brand profile, marks the charge used, and returns the same
`TokenResponse` as login — so the customer lands on the dashboard already signed in.

No `confirm_password`: the setup page shows one password field, and a mistyped password is
recoverable through the ordinary reset flow.

`payment_charges` rows are written outside the app (payment happens elsewhere; a provider
webhook is not part of the MVP). To record one:

```bash
docker compose run --rm backend python -m scripts.create_charge ch_3PabcXYZ customer@example.com
```

It prints the activation URL: `APP_PUBLIC_URL/setup-account?email=…&charge=…`.

| Situation | Response |
| --- | --- |
| Unknown `charge_id` | 422 `validation_error` |
| Charge already redeemed | 422 `validation_error` (identical message) |
| `email` does not match the charge | 422 `validation_error` (identical message) |
| An account already exists for that email | 409 `conflict`, charge left **unused** |

The first three are deliberately indistinguishable: the pair `(email, charge_id)` is what
authorises account creation, so naming which half was wrong would confirm which charge
references exist. The 409 exists because paying with someone else's address must not let the
payer set that account's password.

Email is matched case-insensitively, and the account is created from the address stored on the
charge, lowercased — the customer never types this address, so an account whose stored casing
differs from what they type at login is an account they can never reach.

Rate limited (`SETUP_ACCOUNT_RATE_LIMIT`, default 10/hour) — tighter than `AUTH_RATE_LIMIT`
because a guessed pair yields an account.

### `GET /api/auth/me` → 200

Returns the authenticated `UserOut`.

### `POST /api/auth/forgot-password` → 200

Body: `email`. Always returns the same `{"message": ...}`, whether or not an account exists —
otherwise the endpoint would be a way to enumerate registered addresses. For the same reason the
mail is sent *after* the response (so delivery time cannot be measured) and a transport failure is
logged rather than returned.

Issuing a link retires any earlier one for that user. Rate limited by `PASSWORD_RESET_RATE_LIMIT`
(default `5/hour`), tighter than the other auth endpoints because this one sends mail to an
address the caller chooses.

Nothing is sent when `APP_PUBLIC_URL` is empty — there would be no valid link to include.

### `POST /api/auth/reset-password` → 200

Body: `token`, `password`, `confirm_password`. Returns 422 with `validation_error` for a token that
is unknown, already used, expired, or belongs to a disabled account — all four are the same
message, so a caller learns nothing about which.

Tokens are single-use, expire after `PASSWORD_RESET_TOKEN_TTL_MINUTES` (default 60), and are stored
only as a SHA-256 digest, so a database leak cannot be replayed.

> Access tokens are stateless JWTs: sessions issued before a reset remain valid until they expire.

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
