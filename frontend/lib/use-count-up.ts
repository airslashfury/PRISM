"use client";

import { useEffect, useRef, useState } from "react";

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/** requestAnimationFrame count-up from 0 to `target`, ease-out cubic. Starts
 * the moment `target` first becomes a finite number, and re-animates from 0
 * if `target` later changes (e.g. a fresh /overview payload). Respects
 * prefers-reduced-motion by returning the target immediately, no animation. */
export function useCountUp(target: number | null | undefined, opts?: { duration?: number }): number {
  const duration = opts?.duration ?? 900;
  const [value, setValue] = useState(0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (target == null || !Number.isFinite(target)) return;

    if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setValue(target);
      return;
    }

    const start = performance.now();
    const from = 0;

    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      setValue(from + (target - from) * easeOutCubic(t));
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      }
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, [target, duration]);

  return target == null || !Number.isFinite(target) ? 0 : value;
}
