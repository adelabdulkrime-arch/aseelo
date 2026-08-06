import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
  // The API client and the locale provider both persist to localStorage, so a
  // token or locale left behind would leak into the next test's assertions.
  window.localStorage.clear();
  delete window.__ASEELO_CONFIG__;
  // I18nProvider writes these on mount; reset so direction assertions start clean.
  document.documentElement.removeAttribute("dir");
  document.documentElement.removeAttribute("lang");
});
