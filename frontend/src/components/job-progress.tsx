"use client";

import { ProgressBar, Spinner } from "@/components/ui";
import { useI18n } from "@/lib/i18n";
import type { Job } from "@/lib/types";

/** The real pipeline checklist, driven by rendering_jobs.steps from the API. */
export function JobProgress({ job }: { job: Job }) {
  const { locale } = useI18n();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <ProgressBar value={job.progress} />
        <span className="shrink-0 text-sm font-bold tabular-nums text-brand">{job.progress}%</span>
      </div>

      <ol className="space-y-1.5">
        {job.steps.map((step) => {
          const label = locale === "ar" ? step.label_ar : step.label;
          const isActive = step.status === "active";
          const isDone = step.status === "done";
          const isFailed = step.status === "failed";

          return (
            <li
              key={step.key}
              className={`flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm transition ${
                isActive ? "bg-brand/5 font-semibold text-brand" : ""
              } ${isFailed ? "bg-red-50 font-semibold text-red-600" : ""} ${
                !isActive && !isFailed && !isDone ? "text-slate-400" : ""
              } ${isDone ? "text-ink-soft" : ""}`}
            >
              <span className="grid h-5 w-5 shrink-0 place-items-center" aria-hidden="true">
                {isDone && <span className="text-emerald-600">✓</span>}
                {isActive && <Spinner className="h-4 w-4" />}
                {isFailed && <span>✕</span>}
                {step.status === "pending" && <span className="text-xs">○</span>}
              </span>
              <span className="flex-1">{label}</span>
              {isActive && step.progress > 0 && (
                <span className="text-xs tabular-nums">{step.progress}%</span>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
