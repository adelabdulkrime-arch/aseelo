"use client";

/** Post-payment account activation.
 *
 * Reached from a receipt email as /setup-account?email=…&charge=…. The customer
 * has already paid, so this screen asks for exactly one thing - a password -
 * and drops them on the dashboard signed in. Anything else here is friction on
 * the first minute of a paid relationship.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { AuthShell } from "@/components/auth-shell";
import { Alert, Field, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

function SetupAccountForm() {
  const { t } = useI18n();
  const router = useRouter();
  const { signIn } = useAuth();
  const params = useSearchParams();

  const email = params.get("email")?.trim() ?? "";
  const chargeId = params.get("charge")?.trim() ?? "";

  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Guard: without both halves the request can only ever fail, so show the
  // reason instead of a form. Whether the charge is *valid* is deliberately not
  // checked up front - that answer only comes back on submit, so this page
  // cannot be used to probe which charge references exist.
  const linkComplete = email !== "" && chargeId !== "";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    // Checked here only to save a round trip; the API validates it again.
    if (password.length < 8) {
      setError(t("passwordTooShort"));
      return;
    }

    setSubmitting(true);
    try {
      const session = await api.setupAccount({ email, charge_id: chargeId, password });
      signIn(session.access_token, session.user);
      // replace, not push: Back must not return to a spent activation link.
      router.replace("/dashboard");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : t("somethingWrong"));
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title={t("setupAccountTitle")}
      subtitle={t("setupAccountSubtitle")}
      footer={
        <Link href="/login" className="font-semibold text-accent hover:underline">
          {t("backToLogin")}
        </Link>
      }
    >
      {!linkComplete ? (
        <Alert kind="error">{t("setupLinkInvalid")}</Alert>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          {error && <Alert kind="error">{error}</Alert>}

          <Field label={t("email")} htmlFor="email" hint={t("setupEmailLocked")}>
            <input
              id="email"
              type="email"
              className="input"
              value={email}
              // readOnly rather than disabled: disabled inputs are skipped by
              // screen readers' form navigation, and the value still needs to
              // be announced - it is what the customer is confirming.
              readOnly
              autoComplete="email"
              dir="ltr"
            />
          </Field>

          <Field label={t("choosePassword")} htmlFor="password">
            <input
              id="password"
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              autoFocus
              required
              dir="ltr"
            />
          </Field>

          <button type="submit" className="btn-primary w-full" disabled={submitting}>
            {submitting && <Spinner className="h-4 w-4" />}
            {t("setupAccountSubmit")}
          </button>
        </form>
      )}
    </AuthShell>
  );
}

export default function SetupAccountPage() {
  // useSearchParams() opts the tree into client-side rendering; without this
  // boundary the production build fails rather than degrading.
  return (
    <Suspense fallback={null}>
      <SetupAccountForm />
    </Suspense>
  );
}
