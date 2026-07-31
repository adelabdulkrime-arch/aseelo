"use client";

import Link from "next/link";

import { StatusBadge } from "@/components/ui";
import { formatDate, formatDuration } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { Video } from "@/lib/types";

export function VideoCard({ video }: { video: Video }) {
  const { locale } = useI18n();
  const title = video.title?.trim() || video.text_content.slice(0, 60);

  return (
    <Link
      href={`/videos/${video.id}`}
      className="card group flex gap-3 overflow-hidden p-3 transition hover:shadow-md"
    >
      <div className="relative aspect-[9/16] w-16 shrink-0 overflow-hidden rounded-lg bg-slate-900">
        {video.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- media comes from the API/S3 host
          <img
            src={video.thumbnail_url}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="grid h-full place-items-center text-slate-500" aria-hidden="true">
            🎬
          </div>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold group-hover:text-brand">{title}</p>
        <p className="mt-0.5 truncate text-xs text-ink-muted">{formatDate(video.created_at, locale)}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <StatusBadge status={video.status} />
          {video.status === "COMPLETED" && video.duration && (
            <span className="text-xs text-ink-muted">
              {formatDuration(video.duration)} · 1080×1920
            </span>
          )}
          {video.status === "PROCESSING" && video.job && (
            <span className="text-xs text-ink-muted">{video.job.progress}%</span>
          )}
        </div>
      </div>

      <span
        className="self-center text-ink-muted transition group-hover:text-brand rtl:rotate-180"
        aria-hidden="true"
      >
        ›
      </span>
    </Link>
  );
}
