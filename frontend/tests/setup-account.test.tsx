/** Post-payment activation: the link from the receipt email, redeemed once. */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AR, renderPage } from "./helpers";

const { routerMock, authMock, setupMock, searchParams } = vi.hoisted(() => ({
  routerMock: { replace: vi.fn(), push: vi.fn(), refresh: vi.fn(), back: vi.fn() },
  authMock: { user: null as unknown, loading: false, signIn: vi.fn(), signOut: vi.fn() },
  setupMock: vi.fn(),
  searchParams: { current: new URLSearchParams() },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
  useSearchParams: () => searchParams.current,
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => authMock }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { ...actual.api, setupAccount: setupMock } };
});

import { ApiError } from "@/lib/api";
import SetupAccountPage from "@/app/setup-account/page";

const SESSION = {
  access_token: "tok-xyz",
  token_type: "bearer",
  expires_in: 86400,
  user: { id: "u9", name: "Buyer Ahmed", email: "buyer@example.com", role: "USER" },
};

function withLink(params: Record<string, string>) {
  searchParams.current = new URLSearchParams(params);
}

beforeEach(() => {
  authMock.user = null;
  routerMock.replace.mockReset();
  authMock.signIn.mockReset();
  setupMock.mockReset();
  withLink({ email: "buyer@example.com", charge: "ch_123456" });
});

describe("activation link guard", () => {
  it("refuses to show a form when the link has no charge reference", async () => {
    withLink({ email: "buyer@example.com" });
    renderPage(<SetupAccountPage />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: AR.saveAndProceed })).not.toBeInTheDocument();
  });

  it("refuses to show a form when the link has no email", async () => {
    withLink({ charge: "ch_123456" });
    renderPage(<SetupAccountPage />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: AR.saveAndProceed })).not.toBeInTheDocument();
  });
});

describe("activation form", () => {
  it("shows the paid address, locked", async () => {
    renderPage(<SetupAccountPage />);

    const email = (await screen.findByLabelText(AR.email)) as HTMLInputElement;
    expect(email.value).toBe("buyer@example.com");
    // readOnly, not disabled: a disabled input is skipped by screen-reader form
    // navigation, and this value is the thing the customer is confirming.
    expect(email).toHaveAttribute("readonly");
    expect(email).not.toBeDisabled();
  });

  it("redeems the charge and lands the customer on the dashboard signed in", async () => {
    setupMock.mockResolvedValue(SESSION);
    const user = userEvent.setup();
    renderPage(<SetupAccountPage />);

    await user.type(await screen.findByLabelText(AR.choosePassword), "ChosenAtCheckout123");
    await user.click(screen.getByRole("button", { name: AR.saveAndProceed }));

    await waitFor(() =>
      expect(setupMock).toHaveBeenCalledWith({
        email: "buyer@example.com",
        charge_id: "ch_123456",
        password: "ChosenAtCheckout123",
      }),
    );
    expect(authMock.signIn).toHaveBeenCalledWith("tok-xyz", SESSION.user);
    // replace, not push: Back must not return to a spent activation link.
    expect(routerMock.replace).toHaveBeenCalledWith("/dashboard");
  });

  it("rejects a short password without spending the charge on a round trip", async () => {
    const user = userEvent.setup();
    renderPage(<SetupAccountPage />);

    await user.type(await screen.findByLabelText(AR.choosePassword), "short");
    await user.click(screen.getByRole("button", { name: AR.saveAndProceed }));

    expect(await screen.findByRole("alert")).toHaveTextContent(AR.passwordTooShort);
    expect(setupMock).not.toHaveBeenCalled();
  });

  it("surfaces the backend's refusal for a spent or unknown charge", async () => {
    setupMock.mockRejectedValue(
      new ApiError(422, "validation_error", "This activation link is invalid or has already been used."),
    );
    const user = userEvent.setup();
    renderPage(<SetupAccountPage />);

    await user.type(await screen.findByLabelText(AR.choosePassword), "ChosenAtCheckout123");
    await user.click(screen.getByRole("button", { name: AR.saveAndProceed }));

    expect(await screen.findByRole("alert")).toHaveTextContent("already been used");
    expect(authMock.signIn).not.toHaveBeenCalled();
    expect(routerMock.replace).not.toHaveBeenCalled();
  });

  it("surfaces the conflict when an account already exists for that address", async () => {
    setupMock.mockRejectedValue(
      new ApiError(409, "conflict", "An account already exists for this email. Sign in instead."),
    );
    const user = userEvent.setup();
    renderPage(<SetupAccountPage />);

    await user.type(await screen.findByLabelText(AR.choosePassword), "ChosenAtCheckout123");
    await user.click(screen.getByRole("button", { name: AR.saveAndProceed }));

    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
  });

  it("trims whitespace out of link parameters", async () => {
    withLink({ email: "  buyer@example.com  ", charge: "  ch_123456  " });
    setupMock.mockResolvedValue(SESSION);
    const user = userEvent.setup();
    renderPage(<SetupAccountPage />);

    await user.type(await screen.findByLabelText(AR.choosePassword), "ChosenAtCheckout123");
    await user.click(screen.getByRole("button", { name: AR.saveAndProceed }));

    await waitFor(() =>
      expect(setupMock).toHaveBeenCalledWith(
        expect.objectContaining({ email: "buyer@example.com", charge_id: "ch_123456" }),
      ),
    );
  });
});
