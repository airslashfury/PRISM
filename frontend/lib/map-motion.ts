"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { DOMAIN_RGB, type Domain } from "./colors";

/** Live `prefers-reduced-motion` state (matchMedia listener, not a one-time read —
 *  a user can flip the OS setting mid-session and every animated map should obey it). */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return reduced;
}

/** RAF-driven 0→1 sawtooth with period `periodMs`, for continuous "alive" pulses
 *  (live outage rings, selection halos). Returns 0 and runs no RAF loop while
 *  `active` is false, reduced-motion is on, or the tab is hidden — a static map
 *  must not spin an idle RAF loop. One RAF loop per hook instance. */
export function usePulse(periodMs: number, active: boolean): number {
  const reducedMotion = usePrefersReducedMotion();
  const [phase, setPhase] = useState(0);
  const rafRef = useRef<number | null>(null);

  const run = active && !reducedMotion;

  useEffect(() => {
    if (!run) {
      setPhase(0);
      return;
    }

    let cancelled = false;

    const loop = (now: number) => {
      if (cancelled || document.hidden) {
        // Tab is backgrounded — bail out cleanly instead of ticking off-screen;
        // the visibilitychange listener below restarts the loop on return.
        rafRef.current = null;
        return;
      }
      setPhase((now % periodMs) / periodMs);
      rafRef.current = requestAnimationFrame(loop);
    };

    const onVisibility = () => {
      if (!document.hidden && rafRef.current == null && !cancelled) {
        rafRef.current = requestAnimationFrame(loop);
      }
    };

    rafRef.current = requestAnimationFrame(loop);
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibility);
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [run, periodMs]);

  return run ? phase : 0;
}

export interface StagedTimelineResult {
  /** Per-stage 0→1 progress; earlier stages clamp to 1, later stages sit at 0. */
  progress: number[];
  /** True once the final stage has reached 1. */
  done: boolean;
  /** Restart the timeline from stage 0. No-op under reduced motion (there's
   *  nothing to replay — everything is already fully drawn). */
  replay: () => void;
}

/** RAF timeline that ramps `stageCount` stages in sequence, stage i covering
 *  [i*stageMs, (i+1)*stageMs]. Used to stage a cascade reveal (power → telecom →
 *  water → …) rather than dumping every downstream arc on screen at once.
 *  Changing `key` restarts the timeline (e.g. a new entity gets selected).
 *  Under reduced motion every stage snaps to progress=1 immediately. */
export function useStagedTimeline(
  stageCount: number,
  opts: { stageMs: number; active: boolean; key?: unknown },
): StagedTimelineResult {
  const { stageMs, active, key } = opts;
  const reducedMotion = usePrefersReducedMotion();
  const finalProgress = useRef<number[]>(new Array(Math.max(stageCount, 0)).fill(1));
  const zeroProgress = useRef<number[]>(new Array(Math.max(stageCount, 0)).fill(0));

  const run = active && stageCount > 0 && !reducedMotion;

  const [progress, setProgress] = useState<number[]>(() =>
    reducedMotion || stageCount === 0 ? finalProgress.current : zeroProgress.current,
  );
  const [runId, setRunId] = useState(0);
  const rafRef = useRef<number | null>(null);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    finalProgress.current = new Array(Math.max(stageCount, 0)).fill(1);
    zeroProgress.current = new Array(Math.max(stageCount, 0)).fill(0);
  }, [stageCount]);

  useEffect(() => {
    if (reducedMotion || stageCount === 0) {
      setProgress(finalProgress.current);
      return;
    }
    if (!run) {
      setProgress(zeroProgress.current);
      return;
    }

    let cancelled = false;
    startRef.current = null;

    const loop = (now: number) => {
      if (cancelled) return;
      if (startRef.current == null) startRef.current = now;
      const elapsed = now - startRef.current;
      const next = new Array(stageCount).fill(0).map((_, i) => {
        const stageStart = i * stageMs;
        const t = (elapsed - stageStart) / stageMs;
        return Math.max(0, Math.min(1, t));
      });
      setProgress(next);
      if (elapsed < stageCount * stageMs) {
        rafRef.current = requestAnimationFrame(loop);
      } else {
        rafRef.current = null;
      }
    };
    rafRef.current = requestAnimationFrame(loop);

    return () => {
      cancelled = true;
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
    // key intentionally restarts the timeline; runId is the manual replay trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, stageCount, stageMs, reducedMotion, key, runId]);

  const replay = useCallback(() => {
    if (reducedMotion) return; // nothing to replay — already fully drawn
    setRunId((n) => n + 1);
  }, [reducedMotion]);

  const done = stageCount === 0 || progress[stageCount - 1] >= 1;

  return { progress, done, replay };
}

/** Map a graph entity `kind` string (as returned by /network/consequence) onto
 *  a rendering Domain. Health facilities (hospital/health_center) render as
 *  "hazard" red — they're the human-stakes wave of the cascade, not power
 *  infrastructure, even though they're powered by the substation. */
export function kindDomain(kind: string | null): Domain {
  if (!kind) return "power";
  const k = kind.toLowerCase();
  if (k.includes("telecom") || k.includes("cell")) return "telecom";
  if (k.includes("water") || k.includes("pump") || k.includes("well")) return "water";
  if (k.includes("hospital") || k.includes("health")) return "hazard";
  if (k.includes("substation") || k.includes("plant") || k.includes("generator") || k.includes("grid")) return "power";
  if (k.includes("barrio") || k.includes("municipio")) return "economy";
  return "power";
}

/** Cascade wave order — mirrors PRISM's Power → Comms → Water → Economy →
 *  Transport dependency chain. Health facilities ride in the "hazard" wave
 *  (the human-stakes payoff), landing right after the water wave and before
 *  the place-level (barrio) wave. */
export const CASCADE_WAVES: Domain[] = ["power", "telecom", "water", "hazard", "economy"];

export function domainRgb(d: Domain): readonly [number, number, number] {
  return DOMAIN_RGB[d];
}
