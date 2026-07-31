"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/ui";
import { VideoCard } from "@/components/video-card";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatBytes } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { DashboardStats } from "@/lib/types";

export default function DashboardPage() {
  const { t, locale } = useI18n();
  const { user } = useAuth();

  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setStats(await api.dashboard());
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : t("somethingWrong"));
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!stats) return <LoadingState />;

  const tiles = [
    { label: t("totalVideos"), value: String(stats.total_videos) },
    { label: t("videosToday"), value: String(stats.videos_today) },
    { label: t("processingJobs"), value: String(stats.processing_jobs) },
    { label: t("storageUsed"), value: formatBytes(stats.storage_used_bytes, locale) },
  ];

  return (
    <div className="animate-fade-in space-y-6">
      <section className="card overflow-hidden">
        <div className="bg-gradient-to-br from-ink to-ink-soft p-6 text-white">
          <p className="text-sm text-slate-300">
            {t("welcome")}, {user?.name}
          </p>
          <h1 className="mt-1 text-2xl font-bold">{t("dashboard")}</h1>
          <p className="mt-2 max-w-md text-sm text-slate-300">{t("dashboardSubtitle")}</p>
          <Link
            href="/videos/new"
            className="btn mt-5 bg-accent font-bold text-ink hover:brightness-95"
          >
            {t("createVideo")}
          </Link>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tiles.map((tile) => (
          <div key={tile.label} className="card p-4">
            <p className="text-xs font-medium text-ink-muted">{tile.label}</p>
            <p className="mt-1 text-2xl font-bold tabular-nums">{tile.value}</p>
          </div>
        ))}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-bold">{t("recentVideos")}</h2>
          <Link href="/videos" className="text-sm font-semibold text-brand hover:underline">
            {t("viewAll")}
          </Link>
        </div>

        {stats.recent_videos.length === 0 ? (
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
            {stats.recent_videos.map((video) => (
              <VideoCard key={video.id} video={video} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
