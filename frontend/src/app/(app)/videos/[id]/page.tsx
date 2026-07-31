"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { JobProgress } from "@/components/job-progress";
import { Alert, ErrorState, LoadingState, Spinner, StatusBadge } from "@/components/ui";
import { ApiError, api, downloadVideo } from "@/lib/api";
import { formatBytes, formatDate, formatDuration } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { Video } from "@/lib/types";

const ACTIVE_POLL_MS = 2000;

export default function VideoDetailPage() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [video, setVideo] = useState<Video | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const notFound = useRef(false);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const result = await api.getVideo(id, signal);
        setVideo(result);
        setError(null);
        return result;
      } catch (cause) {
        if ((cause as Error)?.name === "AbortError") return null;
        if (cause instanceof ApiError && cause.status === 404) notFound.current = true;
        setError(cause instanceof ApiError ? cause.message : t("somethingWrong"));
        return null;
      }
    },
    [id, t],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  // Poll only while work is actually in flight, then stop.
  useEffect(() => {
    if (!video) return;
    const active = video.status === "QUEUED" || video.status === "PROCESSING";
    if (!active) return;
    const timer = setInterval(() => void load(), ACTIVE_POLL_MS);
    return () => clearInterval(timer);
  }, [video, load]);

  async function handleDownload() {
    if (!video) return;
    setActionError(null);
    setBusy(true);
    try {
      const name = `${(video.title || "aseelo-video").trim()}.mp4`;
      await downloadVideo(video.id, name);
    } catch (cause) {
      setActionError(cause instanceof ApiError ? cause.message : t("somethingWrong"));
    } finally {
      setBusy(false);
    }
  }

  async function handleRetry() {
    if (!video) return;
    setActionError(null);
    setBusy(true);
    try {
      setVideo(await api.renderVideo(video.id));
    } catch (cause) {
      setActionError(cause instanceof ApiError ? cause.message : t("somethingWrong"));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!video || !window.confirm(t("confirmDelete"))) return;
    setActionError(null);
    setBusy(true);
    try {
      await api.deleteVideo(video.id);
      router.replace("/videos");
    } catch (cause) {
      setActionError(cause instanceof ApiError ? cause.message : t("somethingWrong"));
      setBusy(false);
    }
  }

  if (error && notFound.current) {
    return (
      <div className="space-y-4">
        <ErrorState message={t("notFound")} />
        <Link href="/videos" className="btn-secondary">
          {t("backToVideos")}
        </Link>
      </div>
    );
  }
  if (error && !video) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!video) return <LoadingState />;

  const isActive = video.status === "QUEUED" || video.status === "PROCESSING";
  const isDone = video.status === "COMPLETED";
  const isFailed = video.status === "FAILED";

  const heading = isDone
    ? t("completedTitle")
    : isFailed
      ? t("failedTitle")
      : t("processingTitle");

  return (
    <div className="animate-fade-in space-y-5">
      <Link href="/videos" className="inline-flex items-center gap-1 text-sm text-ink-muted hover:text-brand">
        <span aria-hidden="true" className="rtl:rotate-180">
          ‹
        </span>
        {t("backToVideos")}
      </Link>

      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{heading}</h1>
          <p className="mt-1 text-sm text-ink-muted">
            {video.title?.trim() || video.text_content.slice(0, 80)}
          </p>
        </div>
        <StatusBadge status={video.status} />
      </header>

      {actionError && <Alert kind="error">{actionError}</Alert>}

      {isActive && video.job && (
        <section className="card p-5">
          <JobProgress job={video.job} />
          <p className="mt-4 text-xs text-ink-muted">{t("processingHelp")}</p>
        </section>
      )}

      {isFailed && (
        <section className="card space-y-3 p-5">
          <Alert kind="error">
            {video.error_message || video.job?.error_message || t("somethingWrong")}
          </Alert>
          <button type="button" onClick={handleRetry} className="btn-primary" disabled={busy}>
            {busy && <Spinner className="h-4 w-4" />}
            {t("retry")}
          </button>
        </section>
      )}

      {isDone && video.output_file_url && (
        <section className="card overflow-hidden p-5">
          <div className="mx-auto w-full max-w-[280px]">
            <video
              key={video.output_file_url}
              src={video.output_file_url}
              poster={video.thumbnail_url ?? undefined}
              controls
              playsInline
              className="aspect-[9/16] w-full rounded-xl bg-black"
            />
          </div>

          <div className="mt-5 flex flex-wrap justify-center gap-2">
            <button type="button" onClick={handleDownload} className="btn-primary" disabled={busy}>
              {busy && <Spinner className="h-4 w-4" />}
              {t("download")}
            </button>
            <Link href="/videos/new" className="btn-secondary">
              {t("createAnother")}
            </Link>
          </div>
        </section>
      )}

      <section className="card p-5">
        <dl className="divide-y divide-slate-100 text-sm">
          {[
            { label: t("template"), value: video.template?.name ?? "—" },
            { label: t("duration"), value: formatDuration(video.duration) },
            {
              label: t("resolution"),
              value: video.width && video.height ? `${video.width}×${video.height}` : "—",
            },
            { label: t("fileSize"), value: formatBytes(video.output_file_size, locale) },
            { label: t("createdAt"), value: formatDate(video.created_at, locale) },
          ].map((row) => (
            <div key={row.label} className="flex items-center justify-between gap-4 py-2.5">
              <dt className="text-ink-muted">{row.label}</dt>
              <dd className="text-end font-medium">{row.value}</dd>
            </div>
          ))}
        </dl>

        <div className="mt-4 border-t border-slate-100 pt-4">
          <p className="mb-1 text-xs font-medium text-ink-muted">{t("videoText")}</p>
          <p className="whitespace-pre-wrap text-sm">{video.text_content}</p>
        </div>
      </section>

      <button type="button" onClick={handleDelete} className="btn-danger" disabled={busy}>
        {t("delete")}
      </button>
    </div>
  );
}
