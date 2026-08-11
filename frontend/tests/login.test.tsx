/** The sign-in flow: credentials in, session established, dashboard. */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AR, renderPage } from "./helpers";

const { routerMock, authMock, loginMock } = vi.hoisted(() => ({
  routerMock: { replace: vi.fn(), push: vi.fn(), refresh: vi.fn(), back: vi.fn() },
  authMock: { user: null as unknown, loading: false, signIn: vi.fn(), signOut: vi.fn() },
  loginMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => routerMock }));
vi.mock("@/lib/auth", () => ({ useAuth: () => authMock }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  // Real ApiError - the page branches on `instanceof`, so a stubbed class would
  // make the error path pass for the wrong reason.
  return { ...actual, api: { ...actual.api, login: loginMock } };
});

import { ApiError } from "@/lib/api";
import LoginPage from "@/app/login/page";

const SESSION = {
  access_token: "tok-abc",
  token_type: "bearer",
  expires_in: 86400,
  user: { id: "u1", name: "Adel", email: "adel@example.com", role: "USER" },
};

beforeEach(() => {
  authMock.user = null;
  routerMock.replace.mockReset();
  authMock.signIn.mockReset();
  loginMock.mockReset();
});

async function fillAndSubmit(email = "  adel@example.com  ", password = "SuperSecret123") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(AR.email), email);
  await user.type(screen.getByLabelText(AR.password), password);
  await user.click(screen.getByRole("button", { name: AR.login }));
}

describe("login page", () => {
  it("signs the user in and sends them to the dashboard", async () => {
    loginMock.mockResolvedValue(SESSION);
    renderPage(<LoginPage />);

    await fillAndSubmit();

    await waitFor(() => expect(authMock.signIn).toHaveBeenCalledWith("tok-abc", SESSION.user));
    // Trimmed: a trailing space pasted from an email client must not 401.
    expect(loginMock).toHaveBeenCalledWith({
      email: "adel@example.com",
      password: "SuperSecret123",
    });
    expect(routerMock.replace).toHaveBeenCalledWith("/dashboard");
  });

  it("shows the backend's own message when credentials are rejected", async () => {
    loginMock.mockRejectedValue(new ApiError(401, "unauthorized", "Invalid email or password"));
    renderPage(<LoginPage />);

    await fillAndSubmit();

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    expect(authMock.signIn).not.toHaveBeenCalled();
    expect(routerMock.replace).not.toHaveBeenCalled();
  });

  it("falls back to a generic message for a non-API failure", async () => {
    loginMock.mockRejectedValue(new TypeError("boom"));
    renderPage(<LoginPage />);

    await fillAndSubmit();

    // A raw TypeError message would leak an implementation detail to the user.
    expect(await screen.findByRole("alert")).toHaveTextContent(AR.somethingWrong);
  });

  it("re-enables the submit button after a failure so the user can retry", async () => {
    loginMock.mockRejectedValue(new ApiError(401, "unauthorized", "nope"));
    renderPage(<LoginPage />);

    await fillAndSubmit();

    await screen.findByRole("alert");
    expect(screen.getByRole("button", { name: AR.login })).toBeEnabled();
  });

  it("redirects an already-signed-in visitor away from the form", async () => {
    authMock.user = SESSION.user;
    renderPage(<LoginPage />);

    await waitFor(() => expect(routerMock.replace).toHaveBeenCalledWith("/dashboard"));
  });
});
