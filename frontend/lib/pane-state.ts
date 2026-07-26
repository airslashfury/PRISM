"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Persisted width + collapsed state for the workspace panes (F14a).
 *
 * SSR discipline: the first render always uses the caller's defaults so the
 * server-rendered markup matches the client's first paint; the stored value is
 * read in an effect and applied after mount (same pattern as
 * `CommandPaletteTrigger`'s platform sniff in `topbar.tsx`). `mounted` is
 * returned so callers can suppress width transitions on that first swap.
 *
 * This is browser-local UI chrome only — deliberately not server state, so the
 * M6 auth trigger stays untouched (see BACKLOG "Preferences panel").
 */

const PREFIX = "prism.pane.";

export interface PaneState {
  width: number;
  collapsed: boolean;
}

export interface PaneStateOptions {
  defaultWidth: number;
  minWidth: number;
  maxWidth: number;
}

function read(key: string): Partial<PaneState> | null {
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<PaneState>;
    return typeof parsed === "object" && parsed !== null ? parsed : null;
  } catch {
    // Private mode / disabled storage / corrupt value — fall back to defaults.
    return null;
  }
}

function write(key: string, state: PaneState): void {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(state));
  } catch {
    /* storage unavailable — the pane still works, it just won't persist */
  }
}

export const clampWidth = (w: number, min: number, max: number) =>
  Math.min(max, Math.max(min, Math.round(w)));

export function usePaneState(key: string, opts: PaneStateOptions) {
  const { defaultWidth, minWidth, maxWidth } = opts;
  const [width, setWidthState] = useState(defaultWidth);
  const [collapsed, setCollapsed] = useState(false);
  const [mounted, setMounted] = useState(false);
  // Kept in a ref so persistence never re-subscribes the pointer handlers.
  const latest = useRef<PaneState>({ width: defaultWidth, collapsed: false });

  useEffect(() => {
    const stored = read(key);
    if (stored) {
      const w = typeof stored.width === "number" ? clampWidth(stored.width, minWidth, maxWidth) : defaultWidth;
      const c = stored.collapsed === true;
      setWidthState(w);
      setCollapsed(c);
      latest.current = { width: w, collapsed: c };
    }
    setMounted(true);
    // Defaults are stable per call site; re-reading storage on a width-prop
    // change would fight the user's stored preference.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const persist = useCallback(
    (next: PaneState) => {
      latest.current = next;
      write(key, next);
    },
    [key],
  );

  const setWidth = useCallback(
    (next: number) => {
      const w = clampWidth(next, minWidth, maxWidth);
      setWidthState(w);
      persist({ width: w, collapsed: latest.current.collapsed });
    },
    [minWidth, maxWidth, persist],
  );

  const setCollapsedState = useCallback(
    (next: boolean) => {
      setCollapsed(next);
      persist({ width: latest.current.width, collapsed: next });
    },
    [persist],
  );

  const toggle = useCallback(() => {
    setCollapsedState(!latest.current.collapsed);
  }, [setCollapsedState]);

  const reset = useCallback(() => {
    setWidthState(defaultWidth);
    setCollapsedState(false);
    persist({ width: defaultWidth, collapsed: false });
  }, [defaultWidth, persist, setCollapsedState]);

  return { width, collapsed, mounted, setWidth, setCollapsed: setCollapsedState, toggle, reset };
}

/**
 * `[` toggles the nav pane, `]` toggles the workspace pane — ignored while the
 * user is typing, so the map pages' search inputs keep working.
 */
export function usePaneShortcut(bracket: "[" | "]", onToggle: () => void): void {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== bracket || e.metaKey || e.ctrlKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      if (
        el &&
        (el.tagName === "INPUT" ||
          el.tagName === "TEXTAREA" ||
          el.tagName === "SELECT" ||
          el.isContentEditable)
      ) {
        return;
      }
      e.preventDefault();
      onToggle();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [bracket, onToggle]);
}

/**
 * deck.gl and MapLibre both size themselves from their container and listen on
 * `window.resize`; a pane drag changes the container without one. Fire it (once
 * per animation frame) so the canvas re-renders at the new width instead of
 * staying letterboxed.
 */
export function notifyMapResize(): void {
  if (typeof window === "undefined") return;
  window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
}
