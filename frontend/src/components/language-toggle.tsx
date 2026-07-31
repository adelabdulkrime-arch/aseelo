"use client";

import { useI18n } from "@/lib/i18n";

export function LanguageToggle({ tone = "light" }: { tone?: "light" | "dark" }) {
  const { locale, setLocale } = useI18n();
  const base =
    tone === "dark"
      ? "border-white/25 text-white hover:bg-white/10"
      : "border-slate-300 text-ink-soft hover:bg-slate-50";

  return (
    <button
      type="button"
      onClick={() => setLocale(locale === "ar" ? "en" : "ar")}
      className={`rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition ${base}`}
      // The label names the language you switch *to*, so it stays in that language.
      aria-label={locale === "ar" ? "Switch to English" : "التبديل إلى العربية"}
    >
      {locale === "ar" ? "English" : "العربية"}
    </button>
  );
}
