"use client";

import { useCallback, useRef } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { clampWidth, notifyMapResize, usePaneShortcut, usePaneState } from "@/lib/pane-state";
import { useMessages } from "@/lib/i18n/context";

const KEYBOARD_STEP = 24;

export interface PaneResizerProps {
  /** Which edge of the viewport the pane it resizes is docked to. */
  side: "left" | "right";
  width: number;
  minWidth: number;
  maxWidth: number;
  onWidth: (next: number) => void;
  /** Double-click / Home restores the pane's default width. */
  onReset: () => void;
  label: string;
  /** id of the pane this handle sizes — `aria-controls` (APG window-splitter). */
  controls: string;
  /**
   * Hidden by presentation mode (`?present=1` hides `[data-chrome]`). True only
   * for the nav handle, which lives *outside* the sidebar's own `data-chrome`
   * element and would otherwise survive a chrome-hide on its own. The workspace
   * handle must not carry it — the aside it sizes isn't chrome, so hiding the
   * handle without the pane would strand it.
   */
  chrome?: boolean;
}

/**
 * The drag handle (F14a). A `separator` in the a11y tree, so it is focusable
 * and arrow-key resizable — dragging is not the only way in. Pointer capture
 * keeps the drag alive when the cursor outruns the 5px hit area, and the
 * per-frame `notifyMapResize()` keeps deck.gl/MapLibre in step with the width.
 */
export function PaneResizer({
  side,
  width,
  minWidth,
  maxWidth,
  onWidth,
  onReset,
  label,
  controls,
  chrome = false,
}: PaneResizerProps) {
  const dragging = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(0);

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (e.button !== 0) return;
      dragging.current = true;
      startX.current = e.clientX;
      startWidth.current = width;
      try {
        e.currentTarget.setPointerCapture(e.pointerId);
      } catch {
        /* pointer no longer active — the move handlers still work, unclamped by capture */
      }
      // Kill text selection + cursor flicker across the whole document for the
      // duration of the drag; the map canvas otherwise swallows the cursor.
      document.body.style.userSelect = "none";
      document.body.style.cursor = "col-resize";
    },
    [width],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!dragging.current) return;
      const delta = e.clientX - startX.current;
      // A left-docked pane grows as the pointer moves right; a right-docked one
      // grows as it moves left.
      const next = startWidth.current + (side === "left" ? delta : -delta);
      onWidth(clampWidth(next, minWidth, maxWidth));
      notifyMapResize();
    },
    [side, minWidth, maxWidth, onWidth],
  );

  const endDrag = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    dragging.current = false;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* pointer already released */
    }
    document.body.style.userSelect = "";
    document.body.style.cursor = "";
    notifyMapResize();
  }, []);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      const grow = side === "left" ? "ArrowRight" : "ArrowLeft";
      const shrink = side === "left" ? "ArrowLeft" : "ArrowRight";
      if (e.key === grow) {
        e.preventDefault();
        onWidth(clampWidth(width + KEYBOARD_STEP, minWidth, maxWidth));
      } else if (e.key === shrink) {
        e.preventDefault();
        onWidth(clampWidth(width - KEYBOARD_STEP, minWidth, maxWidth));
      } else if (e.key === "Home") {
        e.preventDefault();
        onReset();
      } else {
        return;
      }
      notifyMapResize();
    },
    [side, width, minWidth, maxWidth, onWidth, onReset],
  );

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-controls={controls}
      aria-valuenow={width}
      aria-valuemin={minWidth}
      aria-valuemax={maxWidth}
      aria-valuetext={`${width} pixels`}
      tabIndex={0}
      data-pane-resizer={side}
      {...(chrome ? { "data-chrome": "" } : {})}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onDoubleClick={onReset}
      onKeyDown={onKeyDown}
      className={cn(
        "group relative hidden w-1 shrink-0 cursor-col-resize md:block",
        "focus-visible:outline-none",
      )}
    >
      {/* Hit area is wider than the visible rule — 1px is too mean to grab. */}
      <span className="absolute inset-y-0 -left-1.5 -right-1.5 z-10" />
      <span
        aria-hidden
        className={cn(
          "absolute inset-y-0 left-0 w-px bg-border/70 transition-colors",
          "group-hover:bg-primary/60 group-focus-visible:bg-primary",
        )}
      />
    </div>
  );
}

export interface PaneToggleProps {
  collapsed: boolean;
  onToggle: () => void;
  /** Which edge the pane is docked to — decides which way the chevron points. */
  side: "left" | "right";
  label: string;
  shortcut?: string;
  className?: string;
}

export function PaneToggle({ collapsed, onToggle, side, label, shortcut, className }: PaneToggleProps) {
  // Pointing "outward" means collapse, "inward" means expand.
  const pointsLeft = side === "left" ? !collapsed : collapsed;
  const Icon = pointsLeft ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      onClick={() => {
        onToggle();
        notifyMapResize();
      }}
      aria-label={label}
      aria-expanded={!collapsed}
      title={shortcut ? `${label} (${shortcut})` : label}
      data-pane-toggle={side}
      className={cn(
        "inline-flex h-6 w-6 items-center justify-center rounded-md border border-border/60",
        "bg-background/60 text-muted-foreground transition-colors",
        "hover:border-border hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary",
        className,
      )}
    >
      <Icon className="h-3.5 w-3.5" />
    </button>
  );
}

export interface WorkspaceAsideProps {
  /** localStorage key suffix — one per route, so /parcels and /water remember separately. */
  storageKey: string;
  defaultWidth: number;
  minWidth?: number;
  maxWidth?: number;
  /** Short pane name used in the aria labels ("Parcels panel"). */
  label: string;
  className?: string;
  children: React.ReactNode;
}

/**
 * The right-hand workspace pane (F14a) — drag-resizable, collapsible to a rail,
 * width persisted per route. Replaces the hand-rolled
 * `<aside className="… md:w-[420px] …">` that six pages and `MapWorkspace` each
 * carried their own copy of.
 *
 * Below `md` it renders exactly the pre-F14a stacked layout: full width, no
 * handle, never collapsed. Resizing a 375px viewport is not a feature.
 */
export function WorkspaceAside({
  storageKey,
  defaultWidth,
  minWidth = 300,
  maxWidth = 720,
  label,
  className,
  children,
}: WorkspaceAsideProps) {
  const t = useMessages().common;
  const pane = usePaneState(storageKey, { defaultWidth, minWidth, maxWidth });
  const toggle = useCallback(() => {
    pane.toggle();
    notifyMapResize();
  }, [pane]);
  usePaneShortcut("]", toggle);

  if (pane.collapsed) {
    return (
      <>
        {/* Collapsed: a rail on desktop; on mobile the panel stays expanded, so
            the rail is desktop-only and the content renders below it. */}
        <aside
          data-pane="workspace"
          data-collapsed="true"
          className="hidden w-8 shrink-0 flex-col items-center justify-center border-l border-border/70 bg-card/30 md:flex"
        >
          <PaneToggle collapsed side="right" onToggle={toggle} label={t.showPane(label)} shortcut="]" />
        </aside>
        <aside
          className={cn(
            "flex w-full flex-col border-t border-border/70 bg-card/30 md:hidden",
            className,
          )}
        >
          {children}
        </aside>
      </>
    );
  }

  return (
    <>
      <PaneResizer
        side="right"
        width={pane.width}
        minWidth={minWidth}
        maxWidth={maxWidth}
        onWidth={pane.setWidth}
        onReset={pane.reset}
        label={t.resizePane(label)}
        controls="prism-workspace-pane"
      />
      <aside
        id="prism-workspace-pane"
        data-pane="workspace"
        data-collapsed="false"
        style={{ ["--pane-w" as string]: `${pane.width}px` }}
        className={cn(
          "relative flex w-full flex-col border-t border-border/70 bg-card/30",
          "md:w-[var(--pane-w)] md:shrink-0 md:border-l md:border-t-0",
          className,
        )}
      >
        {/* Floats on the pane's own border, vertically centred. It intrudes
            ~12px into the panel, which sits inside every panel's own px-4
            padding at mid-height — near the top it would land on /parcels' tab
            row, which starts at y=0 with no left padding. The cost is a 24px
            dead zone in the ~650px drag track, which is the same trade every
            editor makes for an on-divider collapse chevron. */}
        <PaneToggle
          collapsed={false}
          side="right"
          onToggle={toggle}
          label={`Hide ${label}`}
          shortcut="]"
          className="absolute left-0 top-1/2 z-20 hidden -translate-x-1/2 -translate-y-1/2 shadow-sm md:inline-flex"
        />
        {children}
      </aside>
    </>
  );
}
