"use client";

/** es-PR language toggle (F12a). Sidebar footer — there is no theme control
 * to sit "next to" (none exists in this codebase yet), so it gets its own
 * slot alongside the "Model online" status block. */

import { Languages } from "lucide-react";

import { useLocale, useMessages } from "@/lib/i18n/context";
import { cn } from "@/lib/utils";

export function LanguageToggle({ collapsed }: { collapsed: boolean }) {
  const { locale, setLocale } = useLocale();
  const t = useMessages().sidebar;

  if (collapsed) {
    const other = locale === "en" ? "es-PR" : "en";
    const otherLabel = other === "en" ? t.languageEnglish : t.languageSpanish;
    return (
      <button
        type="button"
        onClick={() => setLocale(other)}
        title={`${t.language}: ${otherLabel}`}
        aria-label={`${t.language}: ${otherLabel}`}
        className="flex w-full items-center justify-center rounded-md p-2 text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
      >
        <Languages className="h-4 w-4" />
      </button>
    );
  }

  return (
    <div
      role="group"
      aria-label={t.language}
      className="flex items-center gap-0.5 rounded-md border border-border/60 bg-background/40 p-0.5 text-xs"
    >
      <button
        type="button"
        onClick={() => setLocale("en")}
        aria-pressed={locale === "en"}
        className={cn(
          "flex-1 rounded px-2 py-1 font-medium transition-colors",
          locale === "en"
            ? "bg-primary/10 text-primary"
            : "text-muted-foreground hover:text-foreground",
        )}
      >
        {t.languageEnglish}
      </button>
      <button
        type="button"
        onClick={() => setLocale("es-PR")}
        aria-pressed={locale === "es-PR"}
        className={cn(
          "flex-1 rounded px-2 py-1 font-medium transition-colors",
          locale === "es-PR"
            ? "bg-primary/10 text-primary"
            : "text-muted-foreground hover:text-foreground",
        )}
      >
        {t.languageSpanish}
      </button>
    </div>
  );
}
