"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/ui";
import { VideoCard } from "@/components/video-card";
import { ApiError, api } from "@/lib/api";
import { useI18n, type StringKey } from "@/lib/i18n";
import type { VideoFilter, VideoList } from "@/lib/types";

const FILTERS: { value: VideoFilter; key: StringKey }[] = [
  { value: "all", key: "filterAll" },
  { value: "processing", key: "filterProcessing" },
  { value: "completed", key: "filterCompleted" },
  { value: "failed", key: "filterFailed" },
];

export default function VideosPage() {
  const { t } = useI18n();

  const [filter, setFilter] = useState<VideoFilter>("all");
  const [data, setData] = useState<VideoList | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await api.listVideos(filter));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : t("somethingWrong"));
    }
  }, [filter, t]);

  useEffect(() => {
    setData(null);
    void load();
  }, [load]);

  // Anything still rendering will change state without user action, so refresh.
  useEffect(() => {
    const hasActive = data?.items.some(
      (video) => video.status === "PROCESSING" || video.status === "QUEUED",
    );
    if (!hasActive) return;
    const timer = setInterval(() => void load(), 4000);
    return () => clearInterval(timer);
  }, [data, load]);

  return (
    <div className="animate-fade-in space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">{t("videos")}</h1>
        <Link href="/videos/new" className="btn-primary">
          {t("createVideo")}
        </Link>
      </header>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label={t("videos")}>
        {FILTERS.map((option) => (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={filter === option.value}
            onClick={() => setFilter(option.value)}
            className={`rounded-full border px-3.5 py-1.5 text-sm font-semibold transition ${
              filter === option.value
                ? "border-brand bg-brand text-white"
                : "border-slate-300 bg-white text-ink-soft hover:bg-slate-50"
            }`}
          >
            {t(option.key)}
          </button>
        ))}
      </div>

      {error ? (
        <ErrorState message={error} onRetry={load} />
      ) : !data ? (
        <LoadingState />
      ) : data.items.length === 0 ? (
        <EmptyState
          title={t("noVideosYet")}
          description={t("noVideosYetHelp")}
          action={
            <Link href="/videos/new" className="btn-primary mt-2">
              {t("createVideo")}
            </Link>
          }
        />
      ) : (
        <div className="space-y-2">
          {data.items.map((video) => (
            <VideoCard key={video.id} video={video} />
          ))}
        </div>
      )}
    </div>
  );
}
