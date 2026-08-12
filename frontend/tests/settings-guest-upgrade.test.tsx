/** Converting a guest session into a permanent account from Settings.
 *
 * The point of this flow: it calls convertGuest (same user_id), not register
 * (a fresh one) - so a guest's videos and brand must not be orphaned by it.
 */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AR, renderPage } from "./helpers";

const { authMock, convertGuestMock } = vi.hoisted(() => ({
  authMock: { user: null as unknown, signIn: vi.fn(), signOut: vi.fn() },
  convertGuestMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => authMock }));
vi.mock("@/lib/pwa", () => ({
  usePwa: () => ({ isStandalone: true, canInstall: false, isIos: false, promptInstall: vi.fn() }),
}));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  // Real ApiError - the form branches on `instanceof`, so a stubbed class
  // would make the error path pass for the wrong reason.
  return { ...actual, api: { ...actual.api, convertGuest: convertGuestMock } };
});

import { ApiError } from "@/lib/api";
import SettingsPage from "@/app/(app)/settings/page";

const GUEST_USER = {
  id: "g1",
  name: "Guest",
  email: "guest-abc@guest.aseelo.example",
  role: "USER",
  is_active: true,
  is_guest: true,
  created_at: "2026-01-01T00:00:00Z",
};

const REAL_USER = {
  id: "u1",
  name: "Adel",
  email: "adel@example.com",
  role: "USER",
  is_active: true,
  is_guest: false,
  created_at: "2026-01-01T00:00:00Z",
};

const UPGRADED_SESSION = {
  access_token: "tok-real",
  token_type: "bearer",
  expires_in: 86400,
  user: { ...GUEST_USER, email: "new-owner@example.com", is_guest: false },
};

beforeEach(() => {
  authMock.user = GUEST_USER;
  authMock.signIn.mockReset();
  authMock.signOut.mockReset();
  convertGuestMock.mockReset();
});

describe("guest upgrade form in Settings", () => {
  it("is shown for a guest and hidden for a registered user", () => {
    renderPage(<SettingsPage />);
    expect(screen.getByLabelText(AR.email)).toBeInTheDocument();

    authMock.user = REAL_USER;
    renderPage(<SettingsPage />);
    expect(screen.queryAllByLabelText(AR.email)).toHaveLength(1); // only the first render's
  });

  it("converts the session in place and signs the caller in with the new account", async () => {
    convertGuestMock.mockResolvedValue(UPGRADED_SESSION);
    renderPage(<SettingsPage />);

    await userEvent.type(screen.getByLabelText(AR.email), "new-owner@example.com");
    await userEvent.type(screen.getByLabelText(AR.password), "SuperSecret123");
    await userEvent.click(screen.getByRole("button", { name: /إنشاء حساب دائم/ }));

    await waitFor(() => expect(convertGuestMock).toHaveBeenCalledWith({
      email: "new-owner@example.com",
      password: "SuperSecret123",
    }));
    expect(authMock.signIn).toHaveBeenCalledWith("tok-real", UPGRADED_SESSION.user);
  });

  it("shows the backend's error and leaves the guest session untouched on conflict", async () => {
    convertGuestMock.mockRejectedValue(
      new ApiError(409, "conflict", "An account with this email already exists"),
    );
    renderPage(<SettingsPage />);

    await userEvent.type(screen.getByLabelText(AR.email), "taken@example.com");
    await userEvent.type(screen.getByLabelText(AR.password), "SuperSecret123");
    await userEvent.click(screen.getByRole("button", { name: /إنشاء حساب دائم/ }));

    expect(await screen.findByText("An account with this email already exists")).toBeInTheDocument();
    expect(authMock.signIn).not.toHaveBeenCalled();
  });

  it("validates password length locally before calling the API", async () => {
    renderPage(<SettingsPage />);

    await userEvent.type(screen.getByLabelText(AR.email), "new-owner@example.com");
    await userEvent.type(screen.getByLabelText(AR.password), "short");
    await userEvent.click(screen.getByRole("button", { name: /إنشاء حساب دائم/ }));

    expect(await screen.findByText(AR.passwordTooShort)).toBeInTheDocument();
    expect(convertGuestMock).not.toHaveBeenCalled();
  });
});
