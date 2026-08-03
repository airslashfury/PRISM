"use client";

import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { X, CheckCircle2, AlertTriangle } from "lucide-react";

import { cn } from "@/lib/utils";
import { useMessages } from "@/lib/i18n/context";

export interface ToastInput {
  title: string;
  description?: string;
  variant?: "default" | "destructive";
}

interface Toast extends ToastInput {
  id: number;
}

interface ToastContextValue {
  push: (toast: ToastInput) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const MAX_VISIBLE = 3;
const AUTO_DISMISS_MS = 6000;

/** Hand-rolled toast stack — no new dependency. Fixed bottom-right, max 3
 *  visible, auto-dismiss + manual close, CSS-only enter animation. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const tc = useMessages().common;
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    const t = timers.current.get(id);
    if (t) {
      clearTimeout(t);
      timers.current.delete(id);
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (toast: ToastInput) => {
      const id = nextId.current++;
      setToasts((prev) => [...prev.slice(-(MAX_VISIBLE - 1)), { ...toast, id }]);
      const timer = setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
      timers.current.set(id, timer);
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.variant === "destructive" ? "alert" : "status"}
            className={cn(
              "animate-in slide-in-from-bottom-2 fade-in motion-reduce:animate-none pointer-events-auto flex items-start gap-2.5 rounded-lg border p-3.5 shadow-xl backdrop-blur",
              t.variant === "destructive"
                ? "border-destructive/40 bg-destructive/10 text-destructive-foreground"
                : "border-border/70 bg-card text-card-foreground",
            )}
          >
            {t.variant === "destructive" ? (
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
            ) : (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
            )}
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium leading-snug">{t.title}</div>
              {t.description && (
                <div className="mt-0.5 text-xs text-muted-foreground">{t.description}</div>
              )}
            </div>
            <button
              onClick={() => dismiss(t.id)}
              className="shrink-0 text-muted-foreground/70 hover:text-foreground"
              aria-label={tc.dismiss}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within a ToastProvider");
  return ctx;
}
