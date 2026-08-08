/** Locale state, and the `dir`/`lang` it drives on <html>.
 *
 * This matters more than a normal i18n test: the whole layout uses Tailwind
 * logical properties (ps-*, me-*, text-start), which only flip because `dir`
 * changes. If `dir` stops being written the app still renders - just mirrored
 * wrongly for Arabic, which is the default locale.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { I18nProvider, useI18n } from "@/lib/i18n";

function Probe() {
  const { locale, dir, setLocale, t } = useI18n();
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="dir">{dir}</span>
      <span data-testid="login-label">{t("startOver")}</span>
      <button onClick={() => setLocale("en")}>to-en</button>
      <button onClick={() => setLocale("ar")}>to-ar</button>
    </div>
  );
}

function renderProbe() {
  return render(
    <I18nProvider>
      <Probe />
    </I18nProvider>,
  );
}

describe("I18nProvider", () => {
  it("defaults to Arabic, right-to-left - the product is Arabic-first", () => {
    renderProbe();
    expect(screen.getByTestId("locale")).toHaveTextContent("ar");
    expect(screen.getByTestId("dir")).toHaveTextContent("rtl");
    expect(document.documentElement.dir).toBe("rtl");
    expect(document.documentElement.lang).toBe("ar");
  });

  it("flips document direction and language when the locale changes", async () => {
    const user = userEvent.setup();
    renderProbe();

    await user.click(screen.getByRole("button", { name: "to-en" }));

    expect(screen.getByTestId("dir")).toHaveTextContent("ltr");
    expect(document.documentElement.dir).toBe("ltr");
    expect(document.documentElement.lang).toBe("en");
  });

  it("translates the same key differently per locale", async () => {
    const user = userEvent.setup();
    renderProbe();

    const arabic = screen.getByTestId("login-label").textContent;
    await user.click(screen.getByRole("button", { name: "to-en" }));
    const english = screen.getByTestId("login-label").textContent;

    expect(arabic).toBe("بدء جلسة جديدة");
    expect(english).toBe("Start a new session");
  });

  it("persists the choice and restores it on the next mount", async () => {
    const user = userEvent.setup();
    const first = renderProbe();

    await user.click(screen.getByRole("button", { name: "to-en" }));
    expect(window.localStorage.getItem("aseelo.locale")).toBe("en");
    first.unmount();

    renderProbe();
    expect(screen.getByTestId("locale")).toHaveTextContent("en");
    expect(document.documentElement.dir).toBe("ltr");
  });

  it("ignores a corrupt stored locale rather than rendering an unknown direction", () => {
    window.localStorage.setItem("aseelo.locale", "klingon");
    renderProbe();
    expect(screen.getByTestId("locale")).toHaveTextContent("ar");
    expect(document.documentElement.dir).toBe("rtl");
  });
});
