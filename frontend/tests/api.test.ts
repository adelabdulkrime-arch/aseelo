/** The typed API client: origin resolution, the error envelope, token handling. */

import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, apiOrigin, downloadVideo, getToken, setToken } from "@/lib/api";

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response;
}

function mockFetch(response: Response | Promise<Response>) {
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// Origin resolution
// ---------------------------------------------------------------------------
describe("apiOrigin", () => {
  it("prefers the runtime value over the build-time one", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://build-time.example");
    window.__ASEELO_CONFIG__ = { apiUrl: "https://runtime.example" };
    expect(apiOrigin()).toBe("https://runtime.example");
  });

  it("treats an explicitly empty RUNTIME value as same-origin", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://build-time.example");
    window.__ASEELO_CONFIG__ = { apiUrl: "" };
    // Not the build-time fallback: empty is a deliberate "call my own origin",
    // which is how the app runs behind the single-domain proxy.
    expect(apiOrigin()).toBe("");
  });

  it("treats an explicitly empty BUILD-TIME value as same-origin, not localhost", () => {
    // Regression guard. `||` here instead of `??` sends every browser to
    // localhost:8000 whenever the image was built without the arg - which is
    // exactly what the production Dockerfile default now relies on. Nothing
    // throws; the app just silently cannot reach its own API.
    delete window.__ASEELO_CONFIG__;
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    expect(apiOrigin()).toBe("");
  });

  it("falls back to localhost only when the value is genuinely absent", () => {
    delete window.__ASEELO_CONFIG__;
    vi.stubEnv("NEXT_PUBLIC_API_URL", undefined);
    expect(apiOrigin()).toBe("http://localhost:8000");
  });

  it("strips trailing slashes so paths do not double up", () => {
    window.__ASEELO_CONFIG__ = { apiUrl: "https://example.com///" };
    expect(apiOrigin()).toBe("https://example.com");
  });
});

// ---------------------------------------------------------------------------
// Error envelope
// ---------------------------------------------------------------------------
describe("error handling", () => {
  it("turns the backend envelope into an ApiError", async () => {
    mockFetch(
      jsonResponse(403, {
        error: { code: "forbidden", message: "Guest sessions are disabled" },
      }),
    );

    const err = await api.guest().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(403);
    expect(err.code).toBe("forbidden");
    expect(err.message).toBe("Guest sessions are disabled");
  });

  it("exposes per-field messages by name and by dotted suffix", async () => {
    mockFetch(
      jsonResponse(422, {
        error: {
          code: "validation_error",
          message: "Invalid request payload",
          details: [{ field: "body.template_id", message: "required" }],
        },
      }),
    );

    setToken("tok");
    const err: ApiError = await api.renderVideo("v1").catch((e) => e);
    expect(err.fieldError("template_id")).toBe("required");
    expect(err.fieldError("body.template_id")).toBe("required");
    expect(err.fieldError("email")).toBeUndefined();
  });

  it("reports an unreachable server as a network error rather than throwing raw", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const err = await api.listTemplates().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("network_error");
    expect(err.status).toBe(0);
  });

  it("lets an AbortError through untouched, so polling can cancel cleanly", async () => {
    const abort = Object.assign(new Error("aborted"), { name: "AbortError" });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(abort));

    const err = await api.getJob("job-1").catch((e) => e);
    expect(err).toBe(abort);
    expect(err).not.toBeInstanceOf(ApiError);
  });

  it("falls back to a readable message when the body is not the envelope", async () => {
    mockFetch({
      ok: false,
      status: 502,
      headers: { get: () => "text/html" },
      json: async () => null,
    } as unknown as Response);

    const err: ApiError = await api.listTemplates().catch((e) => e);
    expect(err.message).toContain("502");
    expect(err.code).toBe("http_error");
  });
});

// ---------------------------------------------------------------------------
// Requests
// ---------------------------------------------------------------------------
describe("requests", () => {
  it("attaches the bearer token to authenticated calls", async () => {
    setToken("tok-123");
    const fetchMock = mockFetch(jsonResponse(200, { id: "u1" }));

    await api.me();

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBe("Bearer tok-123");
  });

  it("omits the token on public endpoints even when one is stored", async () => {
    setToken("tok-123");
    const fetchMock = mockFetch(jsonResponse(200, []));

    await api.listTemplates();

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBeUndefined();
  });

  it("sends JSON bodies with the right content type", async () => {
    setToken("tok");
    const fetchMock = mockFetch(jsonResponse(200, {}));

    await api.updateBrand({ brand_name: "My Brand" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/brand");
    expect(init.method).toBe("PUT");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ brand_name: "My Brand" });
  });

  it("does not set a JSON content type on multipart uploads", async () => {
    setToken("tok");
    const fetchMock = mockFetch(jsonResponse(200, {}));

    await api.uploadLogo(new File(["x"], "logo.png", { type: "image/png" }));

    const [, init] = fetchMock.mock.calls[0];
    // Setting it by hand would clobber the boundary the browser generates.
    expect(init.headers["Content-Type"]).toBeUndefined();
    expect(init.body).toBeInstanceOf(FormData);
  });

  it("returns undefined for 204 rather than trying to parse a body", async () => {
    setToken("tok");
    mockFetch({ status: 204 } as unknown as Response);
    await expect(api.deleteVideo("v1")).resolves.toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Token storage
// ---------------------------------------------------------------------------
describe("token storage", () => {
  it("round-trips and clears", () => {
    expect(getToken()).toBeNull();
    setToken("abc");
    expect(getToken()).toBe("abc");
    setToken(null);
    expect(getToken()).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Download
// ---------------------------------------------------------------------------
describe("downloadVideo", () => {
  it("raises an ApiError instead of writing an error page to disk", async () => {
    setToken("tok");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 409 } as Response));

    await expect(downloadVideo("v1", "out.mp4")).rejects.toBeInstanceOf(ApiError);
  });
});
