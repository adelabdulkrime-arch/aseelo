"use client";

import type { ReactNode } from "react";

import { useI18n } from "@/lib/i18n";
import type { VideoStatus } from "@/lib/types";

export function Spinner({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}

export function LoadingState({ label }: { label?: string }) {
  const { t } = useI18n();
  return (
    <div
      className="flex items-center justify-center gap-3 py-16 text-ink-muted"
      role="status"
      aria-live="polite"
    >
      <Spinner />
      <span>{label ?? t("loading")}</span>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <div className="card p-6 text-center" role="alert">
      <p className="font-semibold text-red-600">{t("somethingWrong")}</p>
      <p className="mt-1 text-sm text-ink-muted">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-secondary mt-4">
          {t("retry")}
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="card flex flex-col items-center gap-3 p-10 text-center">
      <div className="grid h-12 w-12 place-items-center rounded-full bg-slate-100 text-2xl">🎬</div>
      <p className="font-semibold">{title}</p>
      {description && <p className="max-w-sm text-sm text-ink-muted">{description}</p>}
      {action}
    </div>
  );
}

export function Alert({ kind, children }: { kind: "error" | "success"; children: ReactNode }) {
  const styles =
    kind === "error"
      ? "border-red-200 bg-red-50 text-red-700"
      : "border-emerald-200 bg-emerald-50 text-emerald-700";
  return (
    <div
      className={`rounded-xl border px-3.5 py-2.5 text-sm ${styles}`}
      role={kind === "error" ? "alert" : "status"}
    >
      {children}
    </div>
  );
}

const STATUS_STYLES: Record<VideoStatus, string> = {
  DRAFT: "bg-slate-100 text-slate-600",
  QUEUED: "bg-amber-100 text-amber-700",
  PROCESSING: "bg-blue-100 text-blue-700",
  COMPLETED: "bg-emerald-100 text-emerald-700",
  FAILED: "bg-red-100 text-red-700",
  CANCELLED: "bg-slate-100 text-slate-600",
};

const STATUS_LABELS: Record<VideoStatus, { ar: string; en: string }> = {
  DRAFT: { ar: "مسودة", en: "Draft" },
  QUEUED: { ar: "في الانتظار", en: "Queued" },
  PROCESSING: { ar: "قيد المعالجة", en: "Processing" },
  COMPLETED: { ar: "مكتمل", en: "Completed" },
  FAILED: { ar: "فشل", en: "Failed" },
  CANCELLED: { ar: "ملغى", en: "Cancelled" },
};

export function StatusBadge({ status }: { status: VideoStatus }) {
  const { locale } = useI18n();
  const active = status === "PROCESSING" || status === "QUEUED";
  return (
    <span className={`chip ${STATUS_STYLES[status]}`}>
      {active && <Spinner className="h-3 w-3" />}
      {STATUS_LABELS[status][locale]}
    </span>
  );
}

export function ProgressBar({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-slate-200"
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full rounded-full bg-brand transition-[width] duration-500 ease-out"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

export function Field({
  label,
  htmlFor,
  hint,
  error,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label className="label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {error ? (
        <p className="mt-1 text-xs text-red-600">{error}</p>
      ) : (
        hint && <p className="mt-1 text-xs text-ink-muted">{hint}</p>
      )}
    </div>
  );
}

export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 font-extrabold tracking-tight ${className}`}>
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-ink text-sm text-accent">
        A
      </span>
      <span>ASEELO</span>
    </span>
  );
}
