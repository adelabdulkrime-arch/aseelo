"use client";

import { useState, type FormEvent } from "react";

import { Alert, Field, LoadingState, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { useI18n, type Locale } from "@/lib/i18n";
import { usePwa } from "@/lib/pwa";

const LOCALES: { value: Locale; label: string }[] = [
  { value: "ar", label: "العربية" },
  { value: "en", label: "English" },
];

function GuestUpgradeForm() {
  const { t } = useI18n();
  const { signIn } = useAuth();

  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  if (done) return <Alert kind="success">{t("guestConvertSuccess")}</Alert>;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (form.password.length < 8) {
      setFieldErrors({ password: t("passwordTooShort") });
      return;
    }
    setFieldErrors({});
    setSubmitting(true);
    try {
      const result = await api.convertGuest(form);
      signIn(result.access_token, result.user);
      setDone(true);
    } catch (cause) {
      if (cause instanceof ApiError) {
        setError(cause.message);
        const mapped: Record<string, string> = {};
        for (const key of ["email", "password"] as const) {
          const message = cause.fieldError(key);
          if (message) mapped[key] = message;
        }
        setFieldErrors(mapped);
      } else {
        setError(t("somethingWrong"));
      }
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3" noValidate>
      {error && <Alert kind="error">{error}</Alert>}

      <Field label={t("email")} htmlFor="guest-email" error={fieldErrors.email}>
        <input
          id="guest-email"
          type="email"
          className="input"
          value={form.email}
          onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))}
          autoComplete="email"
          required
          dir="ltr"
        />
      </Field>

      <Field label={t("password")} htmlFor="guest-password" error={fieldErrors.password}>
        <input
          id="guest-password"
          type="password"
          className="input"
          value={form.password}
          onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))}
          autoComplete="new-password"
          required
          minLength={8}
          dir="ltr"
        />
      </Field>

      <button type="submit" className="btn-primary w-full" disabled={submitting}>
        {submitting && <Spinner className="h-4 w-4" />}
        {t("guestCreateAccount")}
      </button>
    </form>
  );
}

export default function SettingsPage() {
  const { t, locale, setLocale } = useI18n();
  const { user, signOut } = useAuth();
  const { isStandalone, canInstall, isIos, promptInstall } = usePwa();

  if (!user) return <LoadingState />;

  return (
    <div className="animate-fade-in space-y-5">
      <h1 className="text-2xl font-bold">{t("settings")}</h1>

      {/* A guest never chose their address, so showing the synthetic
          `@guest.invalid` one would be confusing. Offer the way out instead:
          their work lives on this browser's token alone and is lost with it.
          Converts the same account in place (same user_id) so their videos
          and brand carry over - /register would start a blank one instead. */}
      {user.is_guest && (
        <section className="card border-accent/40 bg-accent/5 p-5">
          <h2 className="mb-1 font-bold">{t("guestTitle")}</h2>
          <p className="mb-3 text-sm text-ink-muted">{t("guestBody")}</p>
          <GuestUpgradeForm />
        </section>
      )}

      <section className="card p-5">
        <h2 className="mb-3 font-bold">{t("account")}</h2>
        <dl className="divide-y divide-slate-100 text-sm">
          {[
            { label: t("name"), value: user.name },
            ...(user.is_guest ? [] : [{ label: t("email"), value: user.email }]),
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
