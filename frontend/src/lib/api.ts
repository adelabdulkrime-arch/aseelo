/** Typed client for the ASEELO API.
 *
 * Every backend error uses one envelope ({error: {code, message, details}}),
 * so all failures surface as a single ApiError the UI can render directly.
 */

import type {
  Brand,
  BrandUpdate,
  DashboardStats,
  Job,
  Template,
  TokenResponse,
  User,
  Video,
  VideoFilter,
  VideoList,
  ApiErrorDetail,
} from "./types";

declare global {
  interface Window {
    __ASEELO_CONFIG__?: { apiUrl?: string; appName?: string };
  }
}

/** Origin of the API.
 *
 * Resolved per call, not at module load: `/runtime-config.js` supplies the real
 * value at run time so one image can serve any domain (see that route). An
 * empty string means same-origin, i.e. the API is reverse-proxied under the
 * frontend's domain and no CORS is involved at all.
 */
export function apiOrigin(): string {
  if (typeof window !== "undefined") {
    const runtime = window.__ASEELO_CONFIG__?.apiUrl;
    if (typeof runtime === "string") return runtime.replace(/\/+$/, "");
  }
  // `??`, not `||`: an explicitly empty build value means "same origin" and must
  // not fall through to localhost. Only a genuinely absent value does.
  return (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
}

export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME || "ASEELO";

const TOKEN_KEY = "aseelo.token";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ApiErrorDetail[];

  constructor(status: number, code: string, message: string, details: ApiErrorDetail[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Message for a specific form field, when the backend named one. */
  fieldError(field: string): string | undefined {
    return this.details.find((d) => d.field === field || d.field.endsWith(`.${field}`))?.message;
  }
}

// ---------------------------------------------------------------------------
// Token storage
// ---------------------------------------------------------------------------
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

// ---------------------------------------------------------------------------
// Core request
// ---------------------------------------------------------------------------
interface RequestOptions {
  method?: string;
  body?: unknown;
  /** Sent as-is (multipart); `body` is ignored when this is present. */
  formData?: FormData;
  signal?: AbortSignal;
  auth?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, formData, signal, auth = true } = options;

  const headers: Record<string, string> = {};
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  if (body !== undefined && !formData) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(`${apiOrigin()}${path}`, {
      method,
      headers,
      body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
      signal,
    });
  } catch (cause) {
    if ((cause as Error)?.name === "AbortError") throw cause;
    throw new ApiError(0, "network_error", "Could not reach the server. Check your connection.");
  }

  if (response.status === 204) return undefined as T;

  const isJson = (response.headers.get("content-type") || "").includes("application/json");
  const payload = isJson ? await response.json().catch(() => null) : null;

  if (!response.ok) {
    const envelope = payload?.error;
    throw new ApiError(
      response.status,
      envelope?.code ?? "http_error",
      envelope?.message ?? `Request failed with status ${response.status}`,
      envelope?.details ?? [],
    );
  }

  return payload as T;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------
export const api = {
  /** Mint a throwaway session so the app opens without a login.
   *
   * 429 when the rate limit is hit is an ordinary outcome the caller is
   * expected to handle, not a bug. There is no other way into the app.
   */
  guest: () => request<TokenResponse>("/api/auth/guest", { method: "POST", auth: false }),

  me: () => request<User>("/api/auth/me"),

  getBrand: () => request<Brand>("/api/brand"),

  updateBrand: (input: BrandUpdate) => request<Brand>("/api/brand", { method: "PUT", body: input }),

  uploadLogo: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<Brand>("/api/brand/logo", { method: "POST", formData });
  },

  listTemplates: () => request<Template[]>("/api/templates", { auth: false }),

  dashboard: () => request<DashboardStats>("/api/dashboard"),

  createVideo: (input: {
    text_content: string;
    template_id: string;
    title?: string;
    file: File;
  }) => {
    const formData = new FormData();
    formData.append("text_content", input.text_content);
    formData.append("template_id", input.template_id);
    if (input.title) formData.append("title", input.title);
    formData.append("video_file", input.file);
    return request<Video>("/api/videos", { method: "POST", formData });
  },

  listVideos: (filter: VideoFilter = "all", page = 1, pageSize = 20) =>
    request<VideoList>(`/api/videos?status=${filter}&page=${page}&page_size=${pageSize}`),

  getVideo: (id: string, signal?: AbortSignal) => request<Video>(`/api/videos/${id}`, { signal }),

  deleteVideo: (id: string) =>
    request<{ message: string }>(`/api/videos/${id}`, { method: "DELETE" }),

  renderVideo: (id: string) => request<Video>(`/api/videos/${id}/render`, { method: "POST" }),

  getJob: (id: string, signal?: AbortSignal) => request<Job>(`/api/jobs/${id}`, { signal }),

  downloadUrl: (id: string) => `${apiOrigin()}/api/videos/${id}/download`,
};

/** Download through fetch so the Authorization header is sent. */
export async function downloadVideo(id: string, filename: string): Promise<void> {
  const token = getToken();
  const response = await fetch(api.downloadUrl(id), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new ApiError(response.status, "download_failed", "The download could not be started.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
