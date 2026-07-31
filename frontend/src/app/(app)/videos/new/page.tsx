"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Alert, ErrorState, Field, LoadingState, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { Template } from "@/lib/types";

const MAX_TEXT = 600;

export default function CreateVideoPage() {
  const { t, locale } = useI18n();
  const router = useRouter();

  const [templates, setTemplates] = useState<Template[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  async function loadTemplates() {
    setLoadError(null);
    try {
      const result = await api.listTemplates();
      setTemplates(result);
      if (result.length > 0) setTemplateId((current) => current || result[0].id);
    } catch (cause) {
      setLoadError(cause instanceof ApiError ? cause.message : t("somethingWrong"));
    }
  }

  useEffect(() => {
    void loadTemplates();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    const local: Record<string, string> = {};
    if (!text.trim()) local.text_content = t("textRequired");
    if (!file) local.video_file = t("fileRequired");
    if (!templateId) local.template_id = t("templateRequired");
    setFieldErrors(local);
    if (Object.keys(local).length > 0) return;

    setSubmitting(true);
    try {
      const video = await api.createVideo({
        text_content: text.trim(),
        template_id: templateId,
        title: title.trim() || undefined,
        file: file!,
      });
      router.replace(`/videos/${video.id}`);
    } catch (cause) {
      if (cause instanceof ApiError) {
        setError(cause.message);
        const mapped: Record<string, string> = {};
        for (const key of ["text_content", "template_id", "video_file", "title"] as const) {
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

  if (loadError) return <ErrorState message={loadError} onRetry={loadTemplates} />;
  if (!templates) return <LoadingState />;

  return (
    <div className="animate-fade-in space-y-5">
      <header>
        <h1 className="text-2xl font-bold">{t("createVideo")}</h1>
        <p className="mt-1 text-sm text-ink-muted">{t("createSubtitle")}</p>
      </header>

      <form onSubmit={handleSubmit} className="space-y-5" noValidate>
        {error && <Alert kind="error">{error}</Alert>}

        <section className="card space-y-4 p-5">
          <Field label={`${t("videoTitle")} (${t("optional")})`} htmlFor="title">
            <input
              id="title"
              className="input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={160}
              disabled={submitting}
            />
          </Field>

          <Field
            label={t("videoText")}
            htmlFor="text_content"
            hint={t("videoTextHint")}
            error={fieldErrors.text_content}
          >
            <textarea
              id="text_content"
              className="input min-h-28 resize-y"
              value={text}
              onChange={(e) => setText(e.target.value.slice(0, MAX_TEXT))}
              maxLength={MAX_TEXT}
              required
              disabled={submitting}
            />
            <p className="mt-1 text-end text-xs tabular-nums text-ink-muted">
              {text.length}/{MAX_TEXT}
            </p>
          </Field>
        </section>

        <section className="card p-5">
          <h2 className="mb-3 font-bold">{t("sourceVideo")}</h2>
          <input
            id="video_file"
            type="file"
            accept="video/mp4,video/quicktime,video/x-matroska,video/webm,video/x-msvideo"
            className="sr-only"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setFieldErrors((prev) => ({ ...prev, video_file: "" }));
            }}
            disabled={submitting}
          />
          <label
            htmlFor="video_file"
            className={`flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed p-6 text-center transition ${
              fieldErrors.video_file
                ? "border-red-300 bg-red-50"
                : "border-slate-300 hover:border-brand hover:bg-brand/5"
            }`}
          >
            <span className="text-2xl" aria-hidden="true">
              ⬆
            </span>
            {file ? (
              <>
                <span className="font-semibold text-brand">{file.name}</span>
                <span className="text-xs text-ink-muted">{formatBytes(file.size, locale)}</span>
              </>
            ) : (
              <>
                <span className="font-semibold">{t("chooseFile")}</span>
                <span className="text-xs text-ink-muted">{t("dropHint")}</span>
              </>
            )}
          </label>
          {fieldErrors.video_file && (
            <p className="mt-1 text-xs text-red-600">{fieldErrors.video_file}</p>
          )}
        </section>

        <section className="card p-5">
          <h2 className="mb-3 font-bold">{t("template")}</h2>
          <div className="grid gap-3 sm:grid-cols-3" role="radiogroup" aria-label={t("template")}>
            {templates.map((template) => {
              const selected = templateId === template.id;
              return (
                <button
                  key={template.id}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => setTemplateId(template.id)}
                  disabled={submitting}
                  className={`rounded-xl border-2 p-3 text-start transition ${
                    selected
                      ? "border-brand bg-brand/5"
                      : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  <div className="mb-2 aspect-[9/16] w-full overflow-hidden rounded-lg bg-gradient-to-br from-ink to-brand/70" />
                  <p className="text-sm font-semibold">{template.name}</p>
                  {template.description && (
                    <p className="mt-0.5 line-clamp-3 text-xs text-ink-muted">
                      {template.description}
                    </p>
                  )}
                </button>
              );
            })}
          </div>
          {fieldErrors.template_id && (
            <p className="mt-1 text-xs text-red-600">{fieldErrors.template_id}</p>
          )}
        </section>

        <button type="submit" className="btn-primary w-full sm:w-auto" disabled={submitting}>
          {submitting && <Spinner className="h-4 w-4" />}
          {submitting ? t("uploading") : t("submitCreate")}
        </button>
      </form>
    </div>
  );
}
