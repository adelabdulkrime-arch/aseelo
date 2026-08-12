/** Registration: local validation, then the API's field-level errors. */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AR, renderPage } from "./helpers";

const { routerMock, authMock, registerMock } = vi.hoisted(() => ({
  routerMock: { replace: vi.fn(), push: vi.fn(), refresh: vi.fn(), back: vi.fn() },
  authMock: { user: null as unknown, loading: false, signIn: vi.fn(), signOut: vi.fn() },
  registerMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => routerMock }));
vi.mock("@/lib/auth", () => ({ useAuth: () => authMock }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { ...actual.api, register: registerMock } };
});

import { ApiError } from "@/lib/api";
import RegisterPage from "@/app/register/page";

const SESSION = {
  access_token: "tok-new",
  token_type: "bearer",
  expires_in: 86400,
  user: { id: "u2", name: "Adel", email: "adel@example.com", role: "USER" },
};

beforeEach(() => {
  authMock.user = null;
  routerMock.replace.mockReset();
  authMock.signIn.mockReset();
  registerMock.mockReset();
});

async function fill({ password = "SuperSecret123", confirm = "SuperSecret123" } = {}) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(AR.name), "Adel");
  await user.type(screen.getByLabelText(AR.email), "adel@example.com");
  await user.type(screen.getByLabelText(AR.password), password);
  await user.type(screen.getByLabelText(AR.confirmPassword), confirm);
  await user.click(screen.getByRole("button", { name: AR.register }));
}

describe("register page", () => {
  it("creates the account and starts the user at the brand profile", async () => {
    registerMock.mockResolvedValue(SESSION);
    renderPage(<RegisterPage />);

    await fill();

    await waitFor(() => expect(authMock.signIn).toHaveBeenCalledWith("tok-new", SESSION.user));
    // /brand, not /dashboard: the brand identity drives every later render.
    expect(routerMock.replace).toHaveBeenCalledWith("/brand");
  });

  it("catches a password mismatch locally, without calling the API", async () => {
    renderPage(<RegisterPage />);

    await fill({ confirm: "DifferentSecret123" });

    expect(await screen.findByText(AR.passwordsDoNotMatch)).toBeInTheDocument();
    expect(registerMock).not.toHaveBeenCalled();
  });

  it("catches a short password locally, without calling the API", async () => {
    renderPage(<RegisterPage />);

    await fill({ password: "short", confirm: "short" });

    expect(await screen.findByText(AR.passwordTooShort)).toBeInTheDocument();
    expect(registerMock).not.toHaveBeenCalled();
  });

  it("maps the API's field errors onto the fields that caused them", async () => {
    registerMock.mockRejectedValue(
      new ApiError(409, "conflict", "An account with this email already exists", [
        { field: "email", message: "Already registered" },
      ]),
    );
    renderPage(<RegisterPage />);

    await fill();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "An account with this email already exists",
    );
    expect(screen.getByText("Already registered")).toBeInTheDocument();
    expect(routerMock.replace).not.toHaveBeenCalled();
  });
});
