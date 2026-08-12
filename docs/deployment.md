# Deployment

- [Local development](#local-development)
- [Choosing a topology](#choosing-a-topology) ← read this first
- [Environment variables](#environment-variables)
- [Deploying to Coolify](#deploying-to-coolify)
- [Deploying with plain Docker Compose](#deploying-with-plain-docker-compose)
- [Pushing to GitHub](#pushing-to-github)
- [Production checklist](#production-checklist)
- [Scaling](#scaling)
- [Troubleshooting](#troubleshooting)

## Local development

```bash
cp .env.example .env
```

```bash
python -c "import secrets;print(secrets.token_urlsafe(48))"
```

```bash
docker compose up --build
```

App on :3000, API on :8000, Postgres on :5433, Redis on :6379. Migrations and template seeding run
automatically via `backend/entrypoint.sh`.

Useful commands:

```bash
docker compose logs -f worker
```

```bash
docker compose run --rm -e RATE_LIMIT_ENABLED=false backend pytest -q
```

```bash
docker compose down -v
```

(`down -v` deletes the database and all uploaded media — not a routine restart.)

## Choosing a topology

The browser has to know where the API lives. There are two supported shapes, and the choice
decides your whole environment configuration.

### A — two domains (typical Coolify setup)

```
app.example.com  → frontend
api.example.com  → backend  (also serves /media)
```

Cross-origin, so `CORS_ORIGINS` must name the frontend domain exactly.

```bash
API_PUBLIC_URL=https://api.example.com
CORS_ORIGINS=https://app.example.com
PUBLIC_MEDIA_BASE_URL=https://api.example.com/media
```

### B — one domain, API reverse-proxied (no CORS at all)

```
example.com/        → frontend
example.com/api/    → backend
example.com/media/  → backend
```

Same-origin, so **there is no CORS and nothing to misconfigure**. Leave `API_PUBLIC_URL` empty and
the frontend issues relative requests. `infra/nginx/nginx.conf` already implements this routing.

```bash
API_PUBLIC_URL=
CORS_ORIGINS=https://example.com
PUBLIC_MEDIA_BASE_URL=https://example.com/media
```

Prefer B when you can: fewer moving parts, no preflight requests, no certificate for a second host.

### Why the API URL is not baked into the image

`NEXT_PUBLIC_*` variables are inlined into the client bundle at **build** time. If the API origin
were only a build argument, one image would be locked to one domain, and a missing argument would
ship an app whose users' browsers call `http://localhost:8000`.

Instead the frontend serves `/runtime-config.js` (see `frontend/src/app/runtime-config.js/route.ts`),
which reads `API_PUBLIC_URL` from the live process environment on every request and is loaded
before hydration. **Changing the domain needs a restart, not a rebuild.** Verify any deployment
with:

```bash
curl -s https://app.example.com/runtime-config.js
```

## Environment variables

Start from `.env.production.example`. Required in production — the backend **refuses to boot**
without them (see `_production_safety` in `backend/app/config.py`):

| Variable | Notes |
| --- | --- |
| `APP_ENV` | `production` — hides internal error detail and enables the safety checks |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | no defaults in the prod compose |
| `JWT_SECRET` | 32+ chars; the placeholder is rejected |
| `CORS_ORIGINS` | exact browser origins, comma separated; localhost is rejected |
| `PUBLIC_MEDIA_BASE_URL` | publicly reachable https origin; localhost is rejected |
| `API_PUBLIC_URL` | API origin as the browser sees it; empty = same origin |

Optional: `STORAGE_PROVIDER` (`local`/`s3`) plus the `S3_*` group, `WORKER_CONCURRENCY`,
`MAX_UPLOAD_SIZE`, `MAX_VIDEO_DURATION_SECONDS`, `OUTPUT_CRF`, `OUTPUT_PRESET`,
`RATE_LIMIT_ENABLED`, `LOG_LEVEL`.

### Password reset mail

Password reset is **off by default**: `MAIL_BACKEND=console` logs the message instead of sending
it, so nothing is delivered to users. To turn it on:

| Variable | Notes |
| --- | --- |
| `APP_PUBLIC_URL` | public origin of the frontend; reset links are built from it. Empty = nothing is sent. Production rejects a localhost value |
| `MAIL_BACKEND` | `console` or `smtp` |
| `MAIL_FROM` | e.g. `ASEELO <no-reply@example.com>` — must be an address the provider lets you send as |
| `SMTP_HOST` / `SMTP_PORT` | 587 with `SMTP_STARTTLS=true`, or 465 with `SMTP_SSL=true` |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | provider credentials |

With `APP_ENV=production`, `MAIL_BACKEND=smtp` requires both `SMTP_HOST` and `APP_PUBLIC_URL` — the
backend refuses to boot otherwise rather than accept reset requests it can never fulfil. There is
no vendor SDK: any provider that speaks SMTP (SES, Resend, Postmark, Mailgun, Zoho) works by
changing these variables alone.

Generate the secret with:

```bash
python -c "import secrets;print(secrets.token_urlsafe(48))"
```

## Deploying to Coolify

This is the configured path: **Coolify Cloud**, a **1-core** VPS, a single domain behind the
`proxy` service, and images **prebuilt by GitHub Actions**. Two files implement it:

| File | Role |
| --- | --- |
| `.github/workflows/build-images.yml` | builds both images, pushes to GHCR |
| `docker-compose.coolify.yml` | pulls those images; builds nothing on the server |
| `.env.coolify.example` | the variables to paste into Coolify |

### Why images are not built on the server

The Next.js build wants ~2 GB and saturates a core for 10+ minutes. On a 1-core box that means
every deploy takes the live app down, and it competes with the only core FFmpeg has. CI builds
instead; the VPS only pulls. `docker-compose.prod.yml` stays build-based so the production stack
can still be verified locally — keep the two files in sync when you change either.

### 1. Publish the images

Push to `main` (or run the workflow manually). It publishes:

```
ghcr.io/<owner>/aseelo-backend:latest   + :sha-<commit>
ghcr.io/<owner>/aseelo-frontend:latest  + :sha-<commit>
```

The `sha-` tags are immutable — pin `IMAGE_TAG` to one to roll back.

**The repository is private, so the packages are private too.** Give Coolify a registry credential:
a GitHub PAT with `read:packages`, added under Coolify's *Private Registry* / Docker credentials
and applied to the resource. Without it the deploy fails with `denied` or `manifest unknown` on
`docker pull`.

### 2. Create the resource

**+ New → Resource → Docker Compose**, connect the GitHub repo, set the compose file to
`docker-compose.coolify.yml`.

### 3. Set the environment variables

Paste from `.env.coolify.example` into Coolify's Environment tab. Do not commit a filled-in copy.
Three of them must match the domain you attach in the next step.

### 4. Attach ONE domain, to `proxy` only

Give the domain to the **`proxy`** service on port **80**, and to nothing else. `proxy` is the only
public entry point: it serves `/` from the frontend and `/api` + `/media` from the backend, so the
browser only ever sees one origin and CORS never applies. Coolify's Traefik terminates TLS in
front of it.

No domain yet? Coolify generates an `sslip.io` hostname that resolves to your VPS IP and gets a
real Let's Encrypt certificate — good enough to go live and swap later. Copy it from the Domains
field, then set, with **no trailing slash**:

```bash
CORS_ORIGINS=https://<generated-domain>
PUBLIC_MEDIA_BASE_URL=https://<generated-domain>/media
API_PUBLIC_URL=
```

`API_PUBLIC_URL` must be **present and empty** — empty means same-origin. Leave the line in place
rather than deleting it.

### 5. Declare the volumes as persistent

`pgdata`, `redisdata` and `mediadata` — otherwise a redeploy discards the database and every
rendered video.

### 6. Raise the proxy body limit

Coolify's Traefik defaults are far below a 512 MB upload. Raise it or lower `MAX_UPLOAD_SIZE` to
match. A 413 on upload is almost always this, not the app — `infra/nginx/nginx.conf` already
allows 512 MB, but Traefik sits in front of it.

### 7. Deploy and verify

The backend runs migrations and seeds the three templates on first boot. Then:

```bash
curl -s https://<your-domain>/health
```

```bash
curl -s https://<your-domain>/runtime-config.js
```

The second must print `{"apiUrl":"", ...}`. **If it prints `http://localhost:8000`, stop** — the
frontend is telling every browser to call itself and nothing will work. That means
`API_PUBLIC_URL` reached the container genuinely absent rather than empty.

Then confirm the API and the app answer on the same origin:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://<your-domain>/api/templates
```

Note that `postgres` and `redis` publish **no** host ports — they are reachable only on the
internal network. `backend` and `frontend` publish none either; only `proxy` is routed. Do not add
ports for any of them.

### Persistence

`pgdata`, `redisdata` and `mediadata` are named volumes. In Coolify make sure they are declared as
persistent storage, or a redeploy will discard the database and every rendered video. With
`STORAGE_PROVIDER=s3` only `pgdata` is critical.

## Deploying with plain Docker Compose

```bash
git clone https://github.com/<you>/aseelo.git && cd aseelo
```

```bash
cp .env.production.example .env
```

Fill in `.env`, then:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Put a TLS-terminating proxy in front. `infra/nginx/nginx.conf` implements topology B; point your
certificates at it and redirect :80 to :443.

Update an existing deployment:

```bash
git pull && docker compose -f docker-compose.prod.yml up -d --build
```

## Pushing to GitHub

From `aseelo/` (the repo root — it already has a `.git` directory and `.env` is gitignored):

```bash
git status --short
```

Confirm no `.env` appears, then:

```bash
git add -A
```

```bash
git commit -m "ASEELO Video MVP: FastAPI backend, FFmpeg render pipeline, Next.js PWA"
```

Create the remote repository (with the `gh` CLI):

```bash
gh repo create aseelo --private --source=. --remote=origin --push
```

Or, if you created it in the GitHub web UI:

```bash
git remote add origin https://github.com/<you>/aseelo.git
```

```bash
git branch -M main && git push -u origin main
```

Then point Coolify at the repository and enable automatic deploys on push if you want them.

> Never commit a real `.env`. `.gitignore` already excludes it — verify with `git status --short`
> before every push, and if a secret is ever committed, rotate it rather than only deleting it.

## Production checklist

1. **Secrets** — real `JWT_SECRET` and Postgres password, injected via Coolify's environment store,
   never committed.
2. **`APP_ENV=production`** — stops internal exception text leaking into API responses and turns on
   the boot-time safety checks.
3. **HTTPS everywhere** — an https page cannot load media from an http origin, so
   `PUBLIC_MEDIA_BASE_URL` must be https too.
4. **`CORS_ORIGINS`** — the real frontend origin only (or the same origin under topology B).
5. **Storage** — switch to `s3` for anything serious. The local volume does not survive volume
   recreation and prevents running more than one backend replica.
6. **Proxy body limit** — must exceed `MAX_UPLOAD_SIZE`.
7. **Backups** — scheduled `pg_dump`, plus bucket versioning for media.
8. **Resources** — FFmpeg is CPU-bound; budget ~1 core per worker process and keep
   `WORKER_CONCURRENCY` at or below the core count.

## Sizing the server

Rendering is the whole product, and it is CPU-bound. These numbers were measured on this codebase
with the worker container limited to **one core** (`docker update --cpus=1`), rendering the smoke
test's 6-second 1080×1920 clip:

| `OUTPUT_PRESET` | render time | ratio |
| --- | --- | --- |
| `medium` (default) | 85–98 s | ~14–16× realtime |
| `veryfast` | 81 s | ~13.5× realtime |

Two things follow, and both are counter-intuitive:

1. **Preset tuning barely helps.** `veryfast` bought ~6%, not the 2–3× you would expect. The
   bottleneck is the filter graph — scaling to 1080×1920, the blur/pad background and the
   full-canvas overlay composite — not the H.264 encode. Do not expect to tune your way out of an
   undersized host.
2. **One core is not enough.** At ~14× realtime, a 60-second clip takes ~14 minutes and the
   180-second maximum takes ~40 minutes, during which that core is saturated and the API, database
   and frontend all contend for it. The app feels broken while anything is rendering.

Practical guidance:

| Host | `WORKER_CONCURRENCY` | Realistic `MAX_VIDEO_DURATION_SECONDS` |
| --- | --- | --- |
| 1 core | `1` | 30–60 (and warn users renders take minutes) |
| 2 cores | `1` | 90 |
| 4 cores | `2` | 180 |
| 8 cores | `3`–`4` | 180 |

Budget roughly **one core per concurrent render**, plus one for everything else. RAM is not the
constraint — 4 GB is comfortable — but building the images is: the Next.js build wants ~2 GB and is
CPU-heavy, so on a 1–2 core box prefer building elsewhere (Coolify's *Use it as a build server*
option, or a CI job pushing to a registry) rather than on the box that serves traffic.

## Scaling

```bash
docker compose -f docker-compose.prod.yml up -d --scale worker=4
```

Workers are stateless and pull from the shared `renders` queue. `task_acks_late` plus
`task_reject_on_worker_lost` means a crashed worker's job is redelivered rather than lost, and
`worker_prefetch_multiplier=1` stops one worker hoarding queued jobs.

Scaling the **API** horizontally additionally requires `STORAGE_PROVIDER=s3` — with local storage,
replicas would not see each other's uploads.

## Troubleshooting

**The deployed app calls `localhost:8000` from the browser.** `API_PUBLIC_URL` is unset. Check
`curl https://app.example.com/runtime-config.js` and restart the frontend service after setting it.

**CORS errors in the browser console.** `CORS_ORIGINS` must contain the frontend origin exactly:
scheme included, no trailing slash, no path. `https://app.example.com` — not `app.example.com`
and not `https://app.example.com/`.

**Backend exits immediately with "Refusing to start in production".** Intentional. The message
lists each offending variable; fix them and redeploy.

**Videos render but do not play, or the page shows mixed-content warnings.**
`PUBLIC_MEDIA_BASE_URL` is http (or localhost) while the page is https.

**413 on upload.** The reverse proxy's body limit, not the app. Traefik/nginx default well below
512 MB.

**Worker starts, jobs stay `QUEUED`.** The API enqueued to a queue nobody consumes. Confirm both
containers share one `REDIS_URL`: `docker compose exec redis redis-cli llen renders`.

**Arabic renders as disconnected or reversed letters.** libraqm is missing, so Pillow fell back to
the reshaper path:

```bash
docker compose run --rm backend python -c "from app.video.text import text_engine_info; print(text_engine_info())"
```

`raqm` should be `True`; if not, rebuild without cache.

**Latin text renders as empty boxes.** The chosen font has no Latin glyphs — see
[video-engine.md](video-engine.md#font-coverage).

**Jobs fail at `quality_check` with "bitrate too low".** Usually a genuinely black or broken
source. Confirm with `ffprobe` on the input; if the source is fine, lower `OUTPUT_CRF`.

**Migrations fail on a fresh volume.** The initial migration needs the `pgcrypto` extension, which
requires a superuser. The bundled Postgres has it; a managed database may need it enabled first.

**Renders are slow.** Almost certainly not enough cores — see [Sizing the server](#sizing-the-server).
`OUTPUT_PRESET=veryfast` is worth setting but buys only ~6%: the bottleneck is the filter graph
(scale, blur/pad background, full-canvas overlay), not the H.264 encode. There is no setting that
makes a 1-core host fast; add cores.
