# ASEELO Video

**From Idea to Content** — turn a raw clip and a line of text into a branded, ready-to-post
1080×1920 Reel/Short.

The user uploads a video, types Arabic or English text, picks a template, and gets back a single
flattened MP4 with their logo, colours and contact details permanently rendered into the frame.
No FFmpeg knowledge required.

## Status

| Area | State |
| --- | --- |
| Backend API (FastAPI) | implemented |
| Database + migrations (PostgreSQL/Alembic) | implemented |
| Auth (guest sessions only - no login) | implemented |
| Rendering engine (FFmpeg + Pillow) | implemented |
| Queue (Redis + Celery) | implemented |
| Frontend PWA (Next.js + TypeScript + Tailwind) | implemented |
| Backend tests + end-to-end smoke test | passing |

There is no login, register, or password reset. Every visitor gets an isolated guest account the
moment the app opens (`/dashboard`, `/brand`, `/videos`, `/videos/new`, `/videos/[id]`,
`/settings`), Arabic-first with a live RTL/LTR toggle, and installable as a PWA.

## Quick start

```bash
cp .env.example .env
```

Generate a real JWT secret and put it in `.env`:

```bash
python -c "import secrets;print(secrets.token_urlsafe(48))"
```

Start the whole stack:

```bash
docker compose up --build
```

- App: http://localhost:3000
- API: http://localhost:8000 (interactive docs at `/docs`, health at `/health`)

Migrations and template seeding run automatically on boot (see `backend/entrypoint.sh`).

## Try it end to end

```bash
curl -s -X POST http://localhost:8000/api/auth/guest
```

Save the returned `access_token`, then create a video (multipart):

```bash
curl -s -X POST http://localhost:8000/api/videos -H "Authorization: Bearer $TOKEN" -F "text_content=عروضنا الجديدة متوفرة الآن" -F "template_id=$TEMPLATE_ID" -F "video_file=@clip.mp4"
```

Poll `GET /api/jobs/{job_id}` until `status` is `COMPLETED`, then download from
`GET /api/videos/{video_id}/download`.

## Tests

Tests need PostgreSQL and the real ffmpeg/ffprobe binaries, so run them inside the backend image:

```bash
docker compose run --rm -e RATE_LIMIT_ENABLED=false backend pytest -q
```

They encode actual clips and assert the output is a valid 1080×1920 H.264/AAC MP4 — nothing in the
rendering path is mocked. (`RATE_LIMIT_ENABLED=false` stops the guest-session limiter from
rejecting the many sessions the suite creates.)

> **The suite truncates `users`, `videos`, `rendering_jobs` and `brand_profiles`** between tests.
> Run it against a development database only — it will wipe accounts you created by hand.

The end-to-end smoke test drives the *running* stack through the whole Definition of Done —
guest session, brand, upload, queue, worker, FFmpeg, quality check, download, ffprobe:

```bash
docker compose run --rm backend python -m scripts.smoke_test
```

Lint:

```bash
docker compose run --rm backend ruff check app tests scripts
```

## Documentation

- [Architecture](docs/architecture.md) — services, request flow, layer model
- [API reference](docs/api.md) — every endpoint, payload and error code
- [Video engine](docs/video-engine.md) — FFmpeg graph, Arabic text, templates, quality gates
- [Deployment](docs/deployment.md) — Coolify, Docker Compose, GitHub, S3, scaling, troubleshooting

## Environment

All configuration is environment-driven; see `.env.example` for development and
`.env.production.example` for production, plus `backend/app/config.py` for defaults. Never commit a
real `.env`.

## Production

Two compose files, for two different jobs:

| File | Use |
| --- | --- |
| `docker-compose.prod.yml` | builds from source — verifying the production stack locally |
| `docker-compose.coolify.yml` | pulls prebuilt images from GHCR — the actual deployment |

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The production stack keeps Postgres and Redis off the host network entirely, requires every secret
explicitly, and **refuses to boot** if `APP_ENV=production` is paired with a placeholder
`JWT_SECRET` or a localhost `CORS_ORIGINS` / `PUBLIC_MEDIA_BASE_URL`.

The API origin is resolved at **run time** via `/runtime-config.js`, not baked into the bundle, so
one image serves any domain — set `API_PUBLIC_URL` and restart. Leave it empty to run the API
reverse-proxied under the same domain, which removes CORS from the picture entirely.

The deployed target is Coolify Cloud on a 1-core VPS, with images built by
`.github/workflows/build-images.yml` and pushed to GHCR — the server builds nothing, because the
Next.js build alone would monopolise the only core for 10+ minutes. Full walkthrough, both
topologies, and sizing measurements are in [docs/deployment.md](docs/deployment.md).

## Frontend

Next.js 15 (App Router) + TypeScript + Tailwind, in `frontend/`. Arabic is the default locale
with a live RTL/LTR toggle; layout uses logical properties so direction flips cleanly.

- `src/lib/api.ts` — typed client; every backend error surfaces as one `ApiError`
- `src/lib/auth.tsx` — JWT session, replayed through `/api/auth/me` on load
- `src/lib/i18n.tsx` — ar/en strings, drives `dir`/`lang` on `<html>`
- `src/app/(app)/` — the authenticated shell and its screens

The processing view polls `GET /api/jobs/{id}` and renders the backend's real stage checklist,
so progress reflects actual pipeline state rather than an animation.

```bash
docker compose build frontend
```

### PWA

Installable with a web app manifest (`id`, `display_override`, maskable icon, two shortcuts) and
a service worker (`public/sw.js`) registered in production builds only.

- **Install** — `src/lib/pwa.tsx` captures `beforeinstallprompt` and surfaces its own banner plus
  a button in Settings. iOS never fires that event, so it gets Add-to-Home-Screen instructions
  instead. Dismissal persists, and everything hides once running standalone.
- **Updates** — the worker deliberately does **not** `skipWaiting()` on install; reloading mid-upload
  would lose work. A waiting worker raises a "new version available" banner, and only when the user
  accepts does the app post `SKIP_WAITING` and reload on `controllerchange`.
- **Offline** — the shell (`offline.html`, manifest, icons, `/_next/static`) is precached;
  navigations are network-first falling back to the offline page. API responses and rendered media
  are **never** cached, because a stale job status or video would mislead the user. A banner shows
  when the browser goes offline.
- **Standalone** — `env(safe-area-inset-*)` padding keeps content clear of the notch and home
  indicator, and overscroll bounce is disabled where there is no browser chrome to absorb it.

## Template previews

`seed_template_previews()` renders each template's picker thumbnail at seed time via
`render_preview()` and stores it at `templates/previews/<slug>.png`. The key is stable, so
re-rendering overwrites in place; the URL carries a `?v=<digest>` of the template configuration,
which busts caches and lets the next boot detect whether anything actually changed — only the
templates whose configuration moved are re-rendered. A render failure is logged and swallowed: the
picker falls back to its gradient rather than blocking startup.

## Guest sessions

There is no login, register, or password reset. `AuthProvider` calls `POST /api/auth/guest` the
moment the app opens, which creates an isolated throwaway account with its own brand profile and
returns a real JWT. **On by default** — `GUEST_SESSIONS_ENABLED=false` is an emergency brake for a
host that cannot keep up with render load, not a normal setting; with it off there is nothing for a
visitor to reach.

The session has to come from the server. A user object invented in the client would render a
dashboard whose every request 401s: signed in to look at, loading nothing.

Guests are cheaper on purpose, because duration drives render cost:

| | Guest ceiling |
| --- | --- |
| Max video duration | `GUEST_MAX_VIDEO_DURATION_SECONDS` (20 s), clamped to `MAX_VIDEO_DURATION_SECONDS` |
| Sessions per hour | `GUEST_RATE_LIMIT` (2) |

The ceiling is clamped by `min()` against the global one, so misconfiguring it can never *raise*
the limit for anybody.

Guest rows accumulate for as long as the endpoint is enabled — which, with no other account type,
is the entire lifetime of the deployment. Reclaim them — accounts, videos, jobs, brand profiles
**and the media on disk**:

```bash
docker compose run --rm backend python -m scripts.prune_guests --dry-run
docker compose run --rm backend python -m scripts.prune_guests
```

Files are deleted before the database rows on purpose: the rows are the only
record of which storage keys belong to whom, so dropping them first and failing
half way leaves media nobody can attribute or ever collect. Retention is
`GUEST_RETENTION_DAYS` (7).

### Sizing

Measured with the worker pinned to one core, rendering a 6-second clip:
**105 s wall time (~17.6× realtime), 105% CPU, 877 MiB peak RSS**. The worker
therefore carries `mem_limit: 1g` in both production compose files — above the
measured peak, but low enough that a runaway render is killed alone rather than
pushing the host into OOM. Do not tighten it below ~900 MiB.

## Next phase

1. Frontend component tests — the UI has been verified by hand against the live API, but has no
   automated coverage yet.
2. Revoking existing sessions on password reset (needs a token version on the user row).
