"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * F9a chunk A1 (Legibility & Trust): every score PRISM shows must explain
 * itself in place — what it measures, how it's built, and where it sits in
 * the distribution. This is the shared "ⓘ" affordance for that: a label +
 * value whose value opens a small popover with the plain-language meaning,
 * the formula in words ("Built from: …"), and — when there's enough of a
 * distribution to make it meaningful — a percentile line.
 *
 * Two layouts, matching the two places scores appear:
 *   - "stacked" (default): label over value — drops into a Metric-style grid
 *     cell (see resilience's DetailPanel); pass the box styles via className.
 *   - "row": muted label left, value right — drops into an entity-drawer
 *     section next to plain <Row> lines (water/telecom/parcels drawers).
 *
 * The popover renders through a portal into document.body and is positioned
 * with `position: fixed` computed from the trigger's viewport rect (not
 * `absolute` inside the local DOM position) — several ancestors in this app
 * (EntityDrawer, PanelBox) apply `animate-in`/`slide-in-from-*` enter
 * animations, which can leave a non-`none` CSS transform on an ancestor and
 * would otherwise silently break `position: fixed` math. Width is clamped to
 * the viewport so it can never overflow at narrow (375px) widths.
 */

const POPOVER_WIDTH = 288; // 18rem
const VIEWPORT_MARGIN = 12;

export function ScoreExplainer({
  label,
  value,
  what,
  formula,
  context,
  className,
  layout = "stacked",
}: {
  label: string;
  value: React.ReactNode;
  what: string;
  formula?: string;
  context?: string;
  className?: string;
  layout?: "stacked" | "row";
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; width: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const popoverId = useId();

  // Position (+ reposition on resize/scroll while open) relative to the
  // viewport, clamped so the popover never runs off either edge.
  useEffect(() => {
    if (!open) return;
    const reflow = () => {
      const btn = btnRef.current;
      if (!btn) return;
      const width = Math.min(POPOVER_WIDTH, window.innerWidth - VIEWPORT_MARGIN * 2);
      const rect = btn.getBoundingClientRect();
      const left = Math.min(
        Math.max(VIEWPORT_MARGIN, rect.left),
        Math.max(VIEWPORT_MARGIN, window.innerWidth - width - VIEWPORT_MARGIN),
      );
      setPos({ top: rect.bottom + 6, left, width });
    };
    reflow();
    window.addEventListener("resize", reflow);
    window.addEventListener("scroll", reflow, true);
    return () => {
      window.removeEventListener("resize", reflow);
      window.removeEventListener("scroll", reflow, true);
    };
  }, [open]);

  // Click-outside + Escape close; Escape also returns focus to the trigger.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (btnRef.current?.contains(t) || popoverRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        btnRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const trigger = (
    <button
      ref={btnRef}
      type="button"
      aria-expanded={open}
      aria-controls={open ? popoverId : undefined}
      aria-label={`What is ${label}?`}
      onClick={() => setOpen((o) => !o)}
      className={cn(
        "inline-flex items-center gap-1 text-sm tnum text-foreground transition-colors hover:text-primary",
        layout === "stacked" ? "mt-0.5 font-semibold" : "font-medium",
      )}
    >
      {value}
      <Info className="h-3 w-3 shrink-0 text-muted-foreground" aria-hidden="true" />
    </button>
  );

  const popover =
    open &&
    pos &&
    createPortal(
      <div
        ref={popoverRef}
        id={popoverId}
        style={{ position: "fixed", top: pos.top, left: pos.left, width: pos.width }}
        className="z-50 rounded-lg border border-border bg-popover p-3 text-left text-xs shadow-lg"
      >
        <p className="text-foreground">{what}</p>
        {formula && (
          <p className="mt-1.5 text-muted-foreground">
            <span className="font-medium text-foreground/80">Built from: </span>
            {formula}
          </p>
        )}
        {context && <p className="mt-1.5 text-muted-foreground">{context}</p>}
      </div>,
      document.body,
    );

  if (layout === "row") {
    return (
      <div className={cn("flex items-center justify-between gap-2 text-sm", className)}>
        <span className="text-muted-foreground">{label}</span>
        {trigger}
        {popover}
      </div>
    );
  }

  return (
    <div className={cn(className)}>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      {trigger}
      {popover}
    </div>
  );
}

/**
 * Where a value sits in a distribution, in plain words. Undefined (render
 * nothing) when the sample is too small for a percentile to mean anything.
 */
export function percentileContext(
  value: number,
  values: number[],
  nounPlural: string,
): string | undefined {
  if (values.length < 10) return undefined;
  const below = values.filter((v) => v < value).length;
  const pct = Math.round((below / values.length) * 100);
  return `Higher than ${pct}% of ${values.length.toLocaleString("en-US")} ${nounPlural}`;
}
