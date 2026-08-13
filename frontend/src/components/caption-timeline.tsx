"use client";

/** Timeline editor for timed captions.
 *
 * Timings are set by dragging on a track rather than typed, because the useful
 * question is "does this line sit where the beat is", which a number cannot
 * answer. Each caption is a bar: drag the middle to move it, drag either edge
 * to trim it. The numbers are still shown, so nothing is hidden - they are just
 * not the input method.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { useI18n } from "@/lib/i18n";
import type { Caption, CaptionPosition } from "@/lib/types";

const POSITIONS: CaptionPosition[] = ["top", "center", "bottom"];

/** Matches the server's MIN_CAPTION_SECONDS. */
const MIN_SECONDS = 0.3;
const MAX_CAPTIONS = 12;

/** Band colours, kept distinct so a glance at the track shows the layout. */
const BAND_STYLE: Record<CaptionPosition, string> = {
  top: "bg-sky-500/85 border-sky-600",
  center: "bg-violet-500/85 border-violet-600",
  bottom: "bg-emerald-500/85 border-emerald-600",
};

type DragMode = "move" | "start" | "end";

interface Props {
  captions: Caption[];
  duration: number;
  onChange: (captions: Caption[]) => void;
  disabled?: boolean;
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

/** One decimal is the finest control a drag can meaningfully express. */
function round(value: number): number {
  return Math.round(value * 10) / 10;
}

export function CaptionTimeline({ captions, duration, onChange, disabled = false }: Props) {
  const { t } = useI18n();
  const trackRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<string | null>(null);
  // Mirrors `drag.current` in state so the bar can show a live readout; the ref
  // stays the source of truth for the pointer maths.
  const [dragging, setDragging] = useState<string | null>(null);
  const drag = useRef<{ id: string; mode: DragMode; grabOffset: number } | null>(null);

  const span = Math.max(duration, 1);
  const toPercent = (seconds: number) => (seconds / span) * 100;

  const secondsAt = useCallback(
    (clientX: number) => {
      const track = trackRef.current;
      if (!track) return 0;
      const rect = track.getBoundingClientRect();
      // The app runs RTL for Arabic; the track itself stays left-to-right in
      // time, so measure from the visual left edge either way.
      const ratio = clamp((clientX - rect.left) / rect.width, 0, 1);
      return round(ratio * span);
    },
    [span],
  );

  const update = useCallback(
    (id: string, patch: Partial<Caption>) => {
      onChange(captions.map((c) => (c.id === id ? { ...c, ...patch } : c)));
    },
    [captions, onChange],
  );

  useEffect(() => {
    if (disabled) return;

    function onMove(event: PointerEvent) {
      const active = drag.current;
      if (!active) return;
      const caption = captions.find((c) => c.id === active.id);
      if (!caption) return;

      const at = secondsAt(event.clientX);
      const length = caption.end_time - caption.start_time;

      // The server rejects captions that overlap inside one band, so the drag
      // is fenced by its neighbours in that band - the bar simply stops rather
      // than letting the user build something that will be refused on submit.
      const neighbours = captions.filter(
        (c) => c.id !== caption.id && c.position === caption.position,
      );
      const floor = Math.max(
        0,
        ...neighbours.filter((c) => c.end_time <= caption.start_time).map((c) => c.end_time),
      );
      const ceiling = Math.min(
        span,
        ...neighbours.filter((c) => c.start_time >= caption.end_time).map((c) => c.start_time),
      );

      if (active.mode === "move") {
        const start = clamp(round(at - active.grabOffset), floor, round(ceiling - length));
        update(active.id, { start_time: start, end_time: round(start + length) });
      } else if (active.mode === "start") {
        update(active.id, {
          start_time: clamp(at, floor, round(caption.end_time - MIN_SECONDS)),
        });
      } else {
        update(active.id, {
          end_time: clamp(at, round(caption.start_time + MIN_SECONDS), ceiling),
        });
      }
    }

    function onUp() {
      drag.current = null;
      setDragging(null);
    }

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [captions, disabled, secondsAt, span, update]);

  function startDrag(event: React.PointerEvent, caption: Caption, mode: DragMode) {
    if (disabled) return;
    event.preventDefault();
    event.stopPropagation();
    setSelected(caption.id);
    setDragging(caption.id);
    drag.current = {
      id: caption.id,
      mode,
      grabOffset: mode === "move" ? secondsAt(event.clientX) - caption.start_time : 0,
    };
  }

  function addCaption() {
    if (captions.length >= MAX_CAPTIONS) return;
    // Drop the new bar after the last one in the same band, so it never lands
    // on top of an existing caption and trips the overlap rule.
    const band: CaptionPosition =
      POSITIONS[Math.min(captions.length, POSITIONS.length - 1)] ?? "center";
    const inBand = captions.filter((c) => c.position === band);
    const start = inBand.length ? Math.max(...inBand.map((c) => c.end_time)) : 0;
    if (start >= span - MIN_SECONDS) return;

    const caption: Caption = {
      id: `txt_${Date.now().toString(36)}`,
      content: "",
      start_time: round(start),
      end_time: round(Math.min(start + 3, span)),
      position: band,
      animation: "fade",
    };
    onChange([...captions, caption]);
    setSelected(caption.id);
  }

  const active = captions.find((c) => c.id === selected) ?? null;

  return (
    <div className="space-y-3">
      {/* ---- the track ---- */}
      <div>
        <div className="mb-1 flex items-center justify-between text-xs text-ink-muted">
          <span>{t("timeline")}</span>
          <span className="tabular-nums">
            {span.toFixed(1)}
            {t("secondsShort")}
          </span>
        </div>

        <div
          ref={trackRef}
          dir="ltr"
          className="relative h-28 w-full select-none overflow-hidden rounded-xl border border-slate-200 bg-slate-50"
        >
          {/* one lane per band */}
          {POSITIONS.map((position, lane) => (
            <div
              key={position}
              className="absolute inset-x-0 border-b border-dashed border-slate-200 last:border-b-0"
              style={{ top: `${(lane * 100) / 3}%`, height: `${100 / 3}%` }}
            >
              <span className="pointer-events-none absolute left-1 top-1 text-[10px] uppercase tracking-wide text-slate-400">
                {t(`band_${position}` as never)}
              </span>
            </div>
          ))}

          {/* second markers */}
          {Array.from({ length: Math.floor(span) + 1 }, (_, second) => (
            <div
              key={second}
              className="pointer-events-none absolute top-0 h-full border-l border-slate-200/70"
              style={{ left: `${toPercent(second)}%` }}
            />
          ))}

          {/* caption bars */}
          {captions.map((caption) => {
            const lane = POSITIONS.indexOf(caption.position);
            const isSelected = caption.id === selected;
            return (
              <div
                key={caption.id}
                role="button"
                tabIndex={0}
                aria-label={caption.content || t("untitledCaption")}
                onPointerDown={(e) => startDrag(e, caption, "move")}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") setSelected(caption.id);
                }}
                className={`absolute flex items-center rounded-lg border-2 text-white shadow-sm transition-shadow ${
                  BAND_STYLE[caption.position]
                } ${isSelected ? "ring-2 ring-offset-1 ring-brand" : ""} ${
                  disabled ? "" : "cursor-grab active:cursor-grabbing"
                }`}
                style={{
                  left: `${toPercent(caption.start_time)}%`,
                  width: `${Math.max(toPercent(caption.end_time - caption.start_time), 3)}%`,
                  top: `${(lane * 100) / 3 + 4}%`,
                  height: `${100 / 3 - 8}%`,
                }}
              >
                <span
                  onPointerDown={(e) => startDrag(e, caption, "start")}
                  className="h-full w-2 shrink-0 cursor-ew-resize rounded-s-md bg-black/20"
                  aria-hidden="true"
                />
                <span className="flex-1 truncate px-1.5 text-[11px] font-medium">
                  {caption.content || t("untitledCaption")}
                </span>
                <span
                  onPointerDown={(e) => startDrag(e, caption, "end")}
                  className="h-full w-2 shrink-0 cursor-ew-resize rounded-e-md bg-black/20"
                  aria-hidden="true"
                />

                {/* Live readout while dragging: the bar shows where it is, but
                    only the numbers say exactly where it lands. */}
                {dragging === caption.id && (
                  <span
                    dir="ltr"
                    // Inside the bar, not above it: the track clips overflow,
                    // so a tooltip on the top lane would be cut off.
                    className="pointer-events-none absolute inset-x-0 -bottom-0.5 mx-auto w-fit whitespace-nowrap rounded bg-slate-900/90 px-1.5 text-[10px] font-semibold tabular-nums text-white"
                  >
                    {caption.start_time.toFixed(1)} → {caption.end_time.toFixed(1)}
                    {t("secondsShort")}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <button
        type="button"
        onClick={addCaption}
        disabled={disabled || captions.length >= MAX_CAPTIONS}
        className="btn-secondary w-full disabled:cursor-not-allowed disabled:opacity-50"
      >
        + {t("addCaption")}
        {captions.length > 0 && ` (${captions.length}/${MAX_CAPTIONS})`}
      </button>

      {/* ---- editor for the selected bar ---- */}
      {active && (
        <div className="card space-y-3 p-4">
          <textarea
            value={active.content}
            onChange={(e) => update(active.id, { content: e.target.value })}
            placeholder={t("captionTextPlaceholder")}
            rows={2}
            maxLength={200}
            disabled={disabled}
            className="w-full rounded-lg border border-slate-200 p-2 text-sm"
          />

          {/* Dragging is for finding the beat; these are for landing on an
              exact second, and for seeing the window as a number. */}
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-ink-muted">
              <span className="mb-1 block">{t("captionFrom")}</span>
              <input
                type="number"
                dir="ltr"
                step={0.1}
                min={0}
                max={round(active.end_time - MIN_SECONDS)}
                value={active.start_time}
                disabled={disabled}
                onChange={(e) =>
                  update(active.id, {
                    start_time: clamp(
                      round(Number(e.target.value)),
                      0,
                      round(active.end_time - MIN_SECONDS),
                    ),
                  })
                }
                className="w-24 rounded-lg border border-slate-200 px-2 py-1.5 text-sm tabular-nums"
              />
            </label>
            <label className="text-xs text-ink-muted">
              <span className="mb-1 block">{t("captionTo")}</span>
              <input
                type="number"
                dir="ltr"
                step={0.1}
                min={round(active.start_time + MIN_SECONDS)}
                max={span}
                value={active.end_time}
                disabled={disabled}
                onChange={(e) =>
                  update(active.id, {
                    end_time: clamp(
                      round(Number(e.target.value)),
                      round(active.start_time + MIN_SECONDS),
                      span,
                    ),
                  })
                }
                className="w-24 rounded-lg border border-slate-200 px-2 py-1.5 text-sm tabular-nums"
              />
            </label>
            <span className="pb-2 text-xs tabular-nums text-ink-muted">
              {t("captionDuration")}: {(active.end_time - active.start_time).toFixed(1)}
              {t("secondsShort")}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {POSITIONS.map((position) => (
              <button
                key={position}
                type="button"
                disabled={disabled}
                onClick={() => update(active.id, { position })}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium ${
                  active.position === position
                    ? "border-brand bg-brand/10 text-brand"
                    : "border-slate-200 text-ink-muted"
                }`}
              >
                {t(`band_${position}` as never)}
              </button>
            ))}

            <select
              value={active.animation}
              onChange={(e) => update(active.id, { animation: e.target.value as Caption["animation"] })}
              disabled={disabled}
              className="rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
            >
              <option value="fade">{t("animFade")}</option>
              <option value="zoom_fade">{t("animZoomFade")}</option>
              <option value="slide_up">{t("animSlideUp")}</option>
              <option value="none">{t("animNone")}</option>
            </select>

            <button
              type="button"
              disabled={disabled}
              onClick={() => {
                onChange(captions.filter((c) => c.id !== active.id));
                setSelected(null);
              }}
              className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600"
            >
              {t("delete")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
