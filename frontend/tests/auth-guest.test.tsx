/** Opening the app without a login.
 *
 * The point of these tests is that the session comes from the SERVER. A user
 * object invented in the client would render a dashboard whose every request
 * 401s - signed in to look at, loading nothing.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { meMock, guestMock } = vi.hoisted(() => ({
  meMock: vi.fn(),
  guestMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { ...actual.api, me: meMock, guest: guestMock } };
});

import { ApiError, getToken, setToken } from "@/lib/api";
import { AuthProvider, useAuth } from "@/lib/auth";

const GUEST = {
  id: "g1",
  name: "Guest",
  email: "guest-abc@guest.invalid",
  role: "USER",
  is_active: true,
  is_guest: true,
  created_at: "2026-01-01T00:00:00Z",
};

const SESSION = { access_token: "guest-tok", token_type: "bearer", expires_in: 86400, user: GUEST };

function Probe() {
  const { user, loading, error } = useAuth();
  if (loading) return <span>loading</span>;
  return (
    <span data-testid="who">
      {user ? `${user.name}:${user.is_guest}` : `anonymous:${error ?? "none"}`}
    </span>
  );
}

function renderAuth() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
}

beforeEach(() => {
  meMock.mockReset();
  guestMock.mockReset();
});

describe("automatic guest session", () => {
  it("mints a server session when the browser has no token", async () => {
    guestMock.mockResolvedValue(SESSION);
    renderAuth();

    expect(await screen.findByTestId("who")).toHaveTextContent("Guest:true");
    // The token is what makes every later API call work.
    expect(getToken()).toBe("guest-tok");
    expect(meMock).not.toHaveBeenCalled();
  });

  it("reuses an existing token instead of minting another guest row", async () => {
    setToken("existing-tok");
    meMock.mockResolvedValue({ ...GUEST, name: "Adel", is_guest: false });
    renderAuth();

    expect(await screen.findByTestId("who")).toHaveTextContent("Adel:false");
    expect(guestMock).not.toHaveBeenCalled();
  });

  it("classifies a disabled deployment (403) so the UI can say so", async () => {
    guestMock.mockRejectedValue(new ApiError(403, "forbidden", "Guest sessions are disabled"));
    renderAuth();

    expect(await screen.findByTestId("who")).toHaveTextContent("anonymous:disabled");
    expect(getToken()).toBeNull();
  });

  it("classifies a rate limit (429) rather than hanging on loading", async () => {
    guestMock.mockRejectedValue(new ApiError(429, "rate_limited", "Too many requests"));
    renderAuth();

    // Loading must resolve either way, or the route guards never run and the
    // user sits on a spinner forever - this is the bug being guarded against:
    // a rate-limited visitor used to see no error and no way out.
    await waitFor(() =>
      expect(screen.getByTestId("who")).toHaveTextContent("anonymous:rate_limited"),
    );
  });

  it("falls back to a generic error for anything else", async () => {
    guestMock.mockRejectedValue(new Error("network down"));
    renderAuth();

    expect(await screen.findByTestId("who")).toHaveTextContent("anonymous:unknown");
  });

  it("drops a token the server no longer accepts", async () => {
    setToken("stale-tok");
    meMock.mockRejectedValue(new ApiError(401, "unauthorized", "Invalid token"));
    renderAuth();

    expect(await screen.findByTestId("who")).toHaveTextContent("anonymous:unknown");
    expect(getToken()).toBeNull();
  });
});
