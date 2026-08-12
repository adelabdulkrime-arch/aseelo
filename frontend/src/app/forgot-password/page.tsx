"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { AuthShell } from "@/components/auth-shell";
import { Alert, Field, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function ForgotPasswordPage() {
  const { t } = useI18n();

  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.forgotPassword({ email: email.trim() });
      // Shown whatever the outcome: the API answers identically for unknown
      // addresses, and the UI must not undo that.
      setSent(true);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : t("somethingWrong"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title={t("forgotPasswordTitle")}
      subtitle={t("forgotPasswordSubtitle")}
      footer={
        <Link href="/login" className="font-semibold text-accent hover:underline">
          {t("backToLogin")}
        </Link>
      }
    >
      {sent ? (
        <Alert kind="success">{t("resetLinkSent")}</Alert>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          {error && <Alert kind="error">{error}</Alert>}

          <Field label={t("email")} htmlFor="email">
            <input
              id="email"
              type="email"
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
              dir="ltr"
            />
          </Field>

          <button type="submit" className="btn-primary w-full" disabled={submitting}>
            {submitting && <Spinner className="h-4 w-4" />}
            {t("sendResetLink")}
          </button>
        </form>
      )}
    </AuthShell>
  );
}
