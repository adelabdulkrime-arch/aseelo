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
| Auth (JWT, bcrypt) | implemented |
| Rendering engine (FFmpeg + Pillow) | implemented |
| Queue (Redis + Celery) | implemented |
| Frontend PWA (Next.js + TypeScript + Tailwind) | implemented |
| Backend tests (95) + end-to-end smoke test | passing |

All eight screens from the spec are built (`/login`, `/register`, `/dashboard`, `/brand`,
`/videos`, `/videos/new`, `/videos/[id]`, `/settings`), Arabic-first with a live RTL/LTR toggle,
and installable as a PWA.

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
curl -s -X POST http://localhost:8000/api/auth/register -H 'Content-Type: application/json' -d '{"name":"Test","email":"you@example.com","password":"SuperSecret123","confirm_password":"SuperSecret123"}'
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

95 tests, all passing. They encode actual clips and assert the output is a valid 1080×1920
H.264/AAC MP4 — nothing in the rendering path is mocked. (`RATE_LIMIT_ENABLED=false` stops the
auth limiter from rejecting the many logins the suite performs.)

> **The suite truncates `users`, `videos`, `rendering_jobs` and `brand_profiles`** between tests.
> Run it against a development database only — it will wipe accounts you created by hand.

The end-to-end smoke test drives the *running* stack through the whole Definition of Done —
register, brand, upload, queue, worker, FFmpeg, quality check, download, ffprobe:

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

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The production stack keeps Postgres and Redis off the host network entirely, requires every secret
explicitly, and **refuses to boot** if `APP_ENV=production` is paired with a placeholder
`JWT_SECRET` or a localhost `CORS_ORIGINS` / `PUBLIC_MEDIA_BASE_URL`.

The API origin is resolved at **run time** via `/runtime-config.js`, not baked into the bundle, so
one image serves any domain — set `API_PUBLIC_URL` and restart. Leave it empty to run the API
reverse-proxied under the same domain, which removes CORS from the picture entirely.

Full Coolify walkthrough, both topologies, and the GitHub push commands are in
[docs/deployment.md](docs/deployment.md).

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

## Next phase

1. Template preview thumbnails (`render_preview()` in `app/video/compose.py` already produces
   them; they just need generating at seed time and storing on `templates.preview_url`) — the
   picker currently shows a gradient placeholder.
2. Password reset delivery (the endpoint contract exists; no mail transport is wired up).
3. Frontend component tests — the UI has been verified by hand against the live API, but has no
   automated coverage yet.
