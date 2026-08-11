"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { AuthShell } from "@/components/auth-shell";
import { Alert, Field, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

function ResetPasswordForm() {
  const { t } = useI18n();
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    // Checked here purely to save a round trip; the API validates both again.
    if (password.length < 8) {
      setError(t("passwordTooShort"));
      return;
    }
    if (password !== confirmPassword) {
      setError(t("passwordsDoNotMatch"));
      return;
    }

    setSubmitting(true);
    try {
      await api.resetPassword({ token, password, confirm_password: confirmPassword });
      setDone(true);
      setTimeout(() => router.replace("/login"), 2500);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : t("somethingWrong"));
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title={t("resetPasswordTitle")}
      subtitle={t("resetPasswordSubtitle")}
      footer={
        <Link href="/login" className="font-semibold text-accent hover:underline">
          {t("backToLogin")}
        </Link>
      }
    >
      {done ? (
        <Alert kind="success">{t("resetPasswordDone")}</Alert>
      ) : !token ? (
        // Nothing to submit without a token, so do not show a form that can only fail.
        <Alert kind="error">{t("resetTokenMissing")}</Alert>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          {error && <Alert kind="error">{error}</Alert>}

          <Field label={t("newPassword")} htmlFor="password">
            <input
              id="password"
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              required
              dir="ltr"
            />
          </Field>

          <Field label={t("confirmPassword")} htmlFor="confirm-password">
            <input
              id="confirm-password"
              type="password"
              className="input"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              required
              dir="ltr"
            />
          </Field>

          <button type="submit" className="btn-primary w-full" disabled={submitting}>
            {submitting && <Spinner className="h-4 w-4" />}
            {t("resetPasswordSubmit")}
          </button>
        </form>
      )}
    </AuthShell>
  );
}

export default function ResetPasswordPage() {
  // useSearchParams() opts the tree into client-side rendering; without this
  // boundary the production build fails rather than degrading.
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}
