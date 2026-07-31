"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { AuthShell } from "@/components/auth-shell";
import { Alert, Field, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

export default function RegisterPage() {
  const { t } = useI18n();
  const { user, signIn } = useAuth();
  const router = useRouter();

  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    confirm_password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  // Set once we sign the new user in, so this page's "already signed in"
  // redirect does not race the post-registration one to /brand.
  const justRegistered = useRef(false);

  useEffect(() => {
    if (user && !justRegistered.current) router.replace("/dashboard");
  }, [user, router]);

  function update(key: keyof typeof form, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    // Check locally first so the user is not charged a round-trip for these.
    const local: Record<string, string> = {};
    if (form.password.length < 8) local.password = t("passwordTooShort");
    if (form.password !== form.confirm_password) {
      local.confirm_password = t("passwordsDoNotMatch");
    }
    setFieldErrors(local);
    if (Object.keys(local).length > 0) return;

    setSubmitting(true);
    try {
      const result = await api.register({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
        confirm_password: form.confirm_password,
      });
      justRegistered.current = true;
      signIn(result.access_token, result.user);
      // New accounts start at the brand profile: it drives every later render.
      router.replace("/brand");
    } catch (cause) {
      if (cause instanceof ApiError) {
        setError(cause.message);
        const mapped: Record<string, string> = {};
        for (const key of ["name", "email", "password", "confirm_password"] as const) {
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
    <AuthShell
      title={t("registerTitle")}
      subtitle={t("registerSubtitle")}
      footer={
        <>
          {t("haveAccount")}{" "}
          <Link href="/login" className="font-semibold text-accent hover:underline">
            {t("login")}
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {error && <Alert kind="error">{error}</Alert>}

        <Field label={t("name")} htmlFor="name" error={fieldErrors.name}>
          <input
            id="name"
            className="input"
            value={form.name}
            onChange={(e) => update("name", e.target.value)}
            autoComplete="name"
            required
            minLength={2}
          />
        </Field>

        <Field label={t("email")} htmlFor="email" error={fieldErrors.email}>
          <input
            id="email"
            type="email"
            className="input"
            value={form.email}
            onChange={(e) => update("email", e.target.value)}
            autoComplete="email"
            required
            dir="ltr"
          />
        </Field>

        <Field label={t("password")} htmlFor="password" error={fieldErrors.password}>
          <input
            id="password"
            type="password"
            className="input"
            value={form.password}
            onChange={(e) => update("password", e.target.value)}
            autoComplete="new-password"
            required
            minLength={8}
            dir="ltr"
          />
        </Field>

        <Field
          label={t("confirmPassword")}
          htmlFor="confirm_password"
          error={fieldErrors.confirm_password}
        >
          <input
            id="confirm_password"
            type="password"
            className="input"
            value={form.confirm_password}
            onChange={(e) => update("confirm_password", e.target.value)}
            autoComplete="new-password"
            required
            dir="ltr"
          />
        </Field>

        <button type="submit" className="btn-primary w-full" disabled={submitting}>
          {submitting && <Spinner className="h-4 w-4" />}
          {t("register")}
        </button>
      </form>
    </AuthShell>
  );
}
