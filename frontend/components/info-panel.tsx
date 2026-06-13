import type { ReactNode } from "react";
import { ChevronDown, Info } from "lucide-react";

import { cn } from "@/lib/utils";

interface InfoPanelSection {
  title: string;
  body: ReactNode;
}

interface InfoPanelProps {
  title?: string;
  sections: InfoPanelSection[];
  className?: string;
  defaultOpen?: boolean;
}

/** Collapsible "About this data" panel: what it is, how it's calculated, sources & accuracy. */
export function InfoPanel({ title = "About this data", sections, className, defaultOpen = false }: InfoPanelProps) {
  return (
    <details
      className={cn("group rounded-lg border border-border/60 bg-background/30", className)}
      open={defaultOpen}
    >
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        <Info className="h-3.5 w-3.5" />
        {title}
        <ChevronDown className="ml-auto h-3.5 w-3.5 transition-transform group-open:rotate-180" />
      </summary>
      <div className="space-y-3 border-t border-border/60 p-3 text-xs text-muted-foreground">
        {sections.map((s) => (
          <div key={s.title}>
            <div className="mb-1 text-[11px] font-semibold text-foreground/80">{s.title}</div>
            <div className="leading-relaxed">{s.body}</div>
          </div>
        ))}
      </div>
    </details>
  );
}
