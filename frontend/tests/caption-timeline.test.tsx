import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CaptionTimeline } from "@/components/caption-timeline";
import type { Caption } from "@/lib/types";

import { renderPage } from "./helpers";

function caption(overrides: Partial<Caption> = {}): Caption {
  return {
    id: "txt_1",
    content: "الهوك",
    start_time: 0,
    end_time: 3,
    position: "top",
    animation: "fade",
    ...overrides,
  };
}

describe("caption timeline", () => {
  it("adds a caption without overlapping the one already in that band", () => {
    const onChange = vi.fn();
    renderPage(
      <CaptionTimeline captions={[caption()]} duration={15} onChange={onChange} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /إضافة نص/ }));

    const [next] = onChange.mock.calls.at(-1) as [Caption[]];
    expect(next).toHaveLength(2);
    // The server rejects overlapping captions in the same band, so the editor
    // must not create one by default.
    const sameBand = next.filter((c) => c.position === next[1].position);
    if (sameBand.length > 1) {
      const [earlier, later] = sameBand.sort((a, b) => a.start_time - b.start_time);
      expect(later.start_time).toBeGreaterThanOrEqual(earlier.end_time);
    }
  });

  it("stops adding captions once the cap is reached", () => {
    const full = Array.from({ length: 12 }, (_, i) =>
      caption({ id: `c${i}`, start_time: i, end_time: i + 0.5 }),
    );
    renderPage(<CaptionTimeline captions={full} duration={60} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /إضافة نص/ })).toBeDisabled();
  });

  it("shows each caption's text on its bar", () => {
    renderPage(
      <CaptionTimeline
        captions={[caption({ content: "مرحباً" })]}
        duration={15}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "مرحباً" })).toBeInTheDocument();
  });

  it("edits the selected caption's text", () => {
    const onChange = vi.fn();
    renderPage(
      <CaptionTimeline captions={[caption()]} duration={15} onChange={onChange} />,
    );

    fireEvent.keyDown(screen.getByRole("button", { name: "الهوك" }), { key: "Enter" });
    fireEvent.change(screen.getByPlaceholderText(/اكتب النص/), {
      target: { value: "نص جديد" },
    });

    const [next] = onChange.mock.calls.at(-1) as [Caption[]];
    expect(next[0].content).toBe("نص جديد");
  });

  it("removes a caption", () => {
    const onChange = vi.fn();
    renderPage(
      <CaptionTimeline captions={[caption()]} duration={15} onChange={onChange} />,
    );

    fireEvent.keyDown(screen.getByRole("button", { name: "الهوك" }), { key: "Enter" });
    fireEvent.click(screen.getByRole("button", { name: "حذف" }));

    const [next] = onChange.mock.calls.at(-1) as [Caption[]];
    expect(next).toEqual([]);
  });

  it("does not let a disabled timeline be edited", () => {
    renderPage(
      <CaptionTimeline captions={[caption()]} duration={15} onChange={vi.fn()} disabled />,
    );
    expect(screen.getByRole("button", { name: /إضافة نص/ })).toBeDisabled();
  });
});
