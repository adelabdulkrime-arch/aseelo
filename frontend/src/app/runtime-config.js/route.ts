import { NextResponse } from "next/server";

/** Runtime configuration handed to the browser before hydration.
 *
 * `NEXT_PUBLIC_*` variables are inlined into the client bundle at *build* time,
 * which would hard-code one domain into the image. Coolify (and any other
 * platform where env vars are set per-deployment) needs the API origin to be
 * decided at *run* time instead, so it is served from here and read by
 * `src/lib/api.ts`.
 *
 * `API_PUBLIC_URL` is deliberately not prefixed with NEXT_PUBLIC_ so that Next
 * leaves it alone and we read the live process environment.
 */
export const dynamic = "force-dynamic";
export const revalidate = 0;

export function GET() {
  // An empty value means "same origin" — the zero-CORS reverse-proxy setup.
  const apiUrl = (process.env.API_PUBLIC_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "").replace(
    /\/+$/,
    "",
  );
  const appName = process.env.APP_NAME ?? process.env.NEXT_PUBLIC_APP_NAME ?? "ASEELO";

  const body = `window.__ASEELO_CONFIG__=${JSON.stringify({ apiUrl, appName })};`;

  return new NextResponse(body, {
    headers: {
      "Content-Type": "application/javascript; charset=utf-8",
      // Must never be cached: it is the one thing that changes per deployment.
      "Cache-Control": "no-store, no-cache, must-revalidate",
    },
  });
}
