# ---------------------------------------------------------------------------
# deps - install node_modules once, cached until package files change
# ---------------------------------------------------------------------------
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
# `vite` is pinned to 6.x in devDependencies rather than left to npm. Its only
# direct consumer is the test tooling, but @vitejs/plugin-react accepts vite
# 4-7, so npm resolves 7 - which demands @types/node >=22.12 and fails ERESOLVE
# against this app's 22.10.5. Bumping @types/node to satisfy a test dependency
# would change what the production build type-checks against, so the test tool
# gives way instead. vitest 2.x targets vite 6 regardless.
RUN npm install --no-audit --no-fund

# ---------------------------------------------------------------------------
# builder - compile the Next.js app
# ---------------------------------------------------------------------------
FROM node:22-alpine AS builder
WORKDIR /app

# Baked into the client bundle at build time, so it must be present here.
#
# The default is EMPTY on purpose — empty means "same origin", which is the only
# safe default for an image that may be deployed anywhere. A non-empty default
# (this used to be http://localhost:8000) is inlined by Next into the compiled
# server code, including the /runtime-config.js route handler, and becomes the
# fallback whenever API_PUBLIC_URL is not set at run time. The result is an
# image that silently tells every browser to call localhost — no test fails and
# nothing throws. The dev compose passes this arg explicitly, so local
# development is unaffected.
ARG NEXT_PUBLIC_API_URL=
ARG NEXT_PUBLIC_APP_NAME=ASEELO
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_APP_NAME=$NEXT_PUBLIC_APP_NAME \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ---------------------------------------------------------------------------
# test - vitest + Testing Library, run in CI and locally
#
# Separate from `builder` so the test run never becomes a prerequisite of the
# production image: `runner` copies only from `builder`, so nothing here ships.
# There is no Node on the development machine, so this is the only way the
# suite runs at all - see docker-compose.yml's `frontend-test` service.
# ---------------------------------------------------------------------------
FROM node:22-alpine AS test
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 CI=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
CMD ["npm", "test"]

# ---------------------------------------------------------------------------
# runner - minimal standalone server
# ---------------------------------------------------------------------------
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
