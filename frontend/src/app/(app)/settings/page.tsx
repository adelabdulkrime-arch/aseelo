"use client";

import { LoadingState } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { useI18n, type Locale } from "@/lib/i18n";
import { usePwa } from "@/lib/pwa";

const LOCALES: { value: Locale; label: string }[] = [
  { value: "ar", label: "العربية" },
  { value: "en", label: "English" },
];

export default function SettingsPage() {
  const { t, locale, setLocale } = useI18n();
  const { user, signOut } = useAuth();
  const { isStandalone, canInstall, isIos, promptInstall } = usePwa();

  if (!user) return <LoadingState />;

  return (
    <div className="animate-fade-in space-y-5">
      <h1 className="text-2xl font-bold">{t("settings")}</h1>

      <section className="card p-5">
        <h2 className="mb-3 font-bold">{t("account")}</h2>
        <dl className="divide-y divide-slate-100 text-sm">
          {[
            { label: t("name"), value: user.name },
            { label: t("email"), value: user.email },
            { label: t("role"), value: user.role },
            { label: t("memberSince"), value: formatDate(user.created_at, locale) },
          ].map((row) => (
            <div key={row.label} className="flex items-center justify-between gap-4 py-2.5">
              <dt className="text-ink-muted">{row.label}</dt>
              <dd className="font-medium">{row.value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="card p-5">
        <h2 className="mb-3 font-bold">{t("language")}</h2>
        <div className="flex gap-2">
          {LOCALES.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setLocale(option.value)}
              aria-pressed={locale === option.value}
              className={`btn flex-1 border ${
                locale === option.value
                  ? "border-brand bg-brand/10 text-brand"
                  : "border-slate-300 bg-white text-ink-soft hover:bg-slate-50"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </section>

      <section className="card p-5">
        <h2 className="mb-3 font-bold">{t("appSection")}</h2>
        <div className="flex items-center justify-between gap-4 text-sm">
          <span className="text-ink-muted">{t("installState")}</span>
          <span className="font-medium">
            {isStandalone ? t("runningStandalone") : t("runningInBrowser")}
          </span>
        </div>
        {!isStandalone && (canInstall || isIos) && (
          <div className="mt-3">
            {canInstall ? (
              <button
                type="button"
                onClick={() => void promptInstall()}
                className="btn-primary w-full"
              >
                {t("install")}
              </button>
            ) : (
              <p className="text-xs text-ink-muted">{t("installIosBody")}</p>
            )}
          </div>
        )}
      </section>

      <section className="card p-5">
        <button type="button" onClick={signOut} className="btn-danger w-full">
          {t("logout")}
        </button>
      </section>
    </div>
  );
}
