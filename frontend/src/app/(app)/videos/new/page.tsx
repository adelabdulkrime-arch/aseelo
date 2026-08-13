"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { CaptionTimeline } from "@/components/caption-timeline";
import { Alert, ErrorState, Field, LoadingState, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatBytes } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { Caption, Template, VideoQuality } from "@/lib/types";

const MAX_TEXT = 600;

/** Read a local file's duration without uploading it. */
function readDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const probe = document.createElement("video");
    probe.preload = "metadata";
    const done = (value: number | null) => {
      URL.revokeObjectURL(url);
      resolve(value);
    };
    probe.onloadedmetadata = () =>
      done(Number.isFinite(probe.duration) ? probe.duration : null);
    // A codec the browser cannot read is not a rejection - the server still
    // validates, so fall through rather than blocking a valid upload.
    probe.onerror = () => done(null);
    probe.src = url;
  });
}

export default function CreateVideoPage() {
  const { t, locale } = useI18n();
  const { user } = useAuth();
  const router = useRouter();

  const [templates, setTemplates] = useState<Template[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const [captions, setCaptions] = useState<Caption[]>([]);
  const [clipDuration, setClipDuration] = useState<number | null>(null);
  const [quality, setQuality] = useState<VideoQuality>("balanced");

  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const selectedTemplate = templates?.find((item) => item.id === templateId) ?? null;
  const usesCaptions = selectedTemplate?.supports_captions ?? false;

  // The server sends the ceiling that applies to THIS account: a guest gets a
  // shorter one than a registered user.
  const maxDuration = user?.max_video_duration_seconds ?? null;

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
    if (!file) local.video_file = t("fileRequired");
    if (!templateId) local.template_id = t("templateRequired");
    if (usesCaptions) {
      // The words live in the caption track for this template, so text_content
      // is not what the user filled in - require at least one real caption.
      if (!captions.some((caption) => caption.content.trim())) {
        local.captions = t("captionsRequired");
      }
    } else if (!text.trim()) {
      local.text_content = t("textRequired");
    }
    setFieldErrors(local);
    if (Object.keys(local).length > 0) return;

    setSubmitting(true);
    try {
      const track = captions.filter((caption) => caption.content.trim());
      const video = await api.createVideo({
        // The backend still requires text_content; for a caption video the
        // first line doubles as the title/summary rather than being painted.
        text_content: usesCaptions ? track[0].content.trim() : text.trim(),
        template_id: templateId,
        title: title.trim() || undefined,
        file: file!,
        captions: usesCaptions ? track : undefined,
        quality,
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

          {/* The caption template carries its words on the timeline instead. */}
          {!usesCaptions && (
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
          )}
        </section>

        {usesCaptions && (
          <section className="card p-5">
            <h2 className="mb-1 font-bold">{t("timeline")}</h2>
            <p className="mb-3 text-xs text-ink-muted">{t("captionsHint")}</p>
            {!file ? (
              // Timings are meaningless without knowing how long the clip is.
              <p className="rounded-lg bg-slate-50 p-4 text-center text-sm text-ink-muted">
                {t("fileRequired")}
              </p>
            ) : (
              <CaptionTimeline
                captions={captions}
                duration={clipDuration ?? maxDuration ?? 15}
                onChange={setCaptions}
                disabled={submitting}
              />
            )}
            {fieldErrors.captions && (
              <p className="mt-2 text-sm text-red-600">{fieldErrors.captions}</p>
            )}
          </section>
        )}

        <section className="card p-5">
          <h2 className="mb-3 font-bold">{t("quality")}</h2>
          <div className="grid gap-2 sm:grid-cols-3">
            {(
              [
                ["fast", "qualityFast", "qualityFastHint"],
                ["balanced", "qualityBalanced", "qualityBalancedHint"],
                ["high", "qualityHigh", "qualityHighHint"],
              ] as const
            ).map(([value, labelKey, hintKey]) => (
              <button
                key={value}
                type="button"
                disabled={submitting}
                onClick={() => setQuality(value)}
                aria-pressed={quality === value}
                className={`rounded-xl border-2 p-3 text-start transition ${
                  quality === value
                    ? "border-brand bg-brand/5"
                    : "border-slate-200 hover:border-slate-300"
                }`}
              >
                <span className="block text-sm font-semibold">{t(labelKey)}</span>
                <span className="block text-xs text-ink-muted">{t(hintKey)}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="card p-5">
          <h2 className="mb-3 font-bold">{t("sourceVideo")}</h2>
          <input
            id="video_file"
            type="file"
            accept="video/mp4,video/quicktime,video/x-matroska,video/webm,video/x-msvideo"
            className="sr-only"
            onChange={async (e) => {
              const chosen = e.target.files?.[0] ?? null;
              setFile(chosen);
              setFieldErrors((prev) => ({ ...prev, video_file: "" }));
              // Catch an over-long clip here rather than after the upload: the
              // server rejects it either way, but only this is instant.
              // One read serves both the length check and the caption
              // timeline, which needs the real duration to place bars against.
              const seconds = chosen ? await readDuration(chosen) : null;
              setClipDuration(seconds);
              if (seconds !== null && maxDuration && seconds > maxDuration + 0.5) {
                setFieldErrors((prev) => ({
                  ...prev,
                  video_file: t("videoTooLong")
                    .replace("{actual}", String(Math.round(seconds)))
                    .replace("{max}", String(maxDuration)),
                }));
              }
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
                {maxDuration !== null && (
                  <span className="text-xs font-medium text-ink-muted">
                    {t("maxDurationHint").replace("{max}", String(maxDuration))}
                    {user?.is_guest ? ` — ${t("guestDurationNote")}` : ""}
                  </span>
                )}
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
                  {/* The gradient stays as the container background, so it also
                      covers the gap while the image loads or if it 404s. */}
                  <div className="mb-2 aspect-[9/16] w-full overflow-hidden rounded-lg bg-gradient-to-br from-ink to-brand/70">
                    {template.preview_url && (
                      // eslint-disable-next-line @next/next/no-img-element -- media comes from the API/S3 host
                      <img
                        src={template.preview_url}
                        alt=""
                        className="h-full w-full object-cover"
                        loading="lazy"
                      />
                    )}
                  </div>
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
