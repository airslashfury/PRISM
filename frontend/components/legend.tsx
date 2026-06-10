import { type RGB, rgbCss } from "@/lib/colors";
import { cn } from "@/lib/utils";

export function GradientLegend({
  title,
  stops,
  minLabel,
  maxLabel,
  className,
}: {
  title: string;
  stops: RGB[];
  minLabel: string;
  maxLabel: string;
  className?: string;
}) {
  const gradient = `linear-gradient(to right, ${stops.map((s) => rgbCss(s)).join(", ")})`;
  return (
    <div
      className={cn(
        "pointer-events-none rounded-lg border border-border/70 bg-card/85 p-3 text-xs shadow-lg backdrop-blur",
        className,
      )}
    >
      <div className="mb-1.5 font-medium text-foreground/90">{title}</div>
      <div className="h-2 w-44 rounded-full" style={{ background: gradient }} />
      <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
        <span>{minLabel}</span>
        <span>{maxLabel}</span>
      </div>
    </div>
  );
}

export function DiscreteLegend({
  title,
  items,
  className,
}: {
  title: string;
  items: { label: string; color: RGB }[];
  className?: string;
}) {
  return (
    <div
      className={cn(
        "pointer-events-none rounded-lg border border-border/70 bg-card/85 p-3 text-xs shadow-lg backdrop-blur",
        className,
      )}
    >
      <div className="mb-1.5 font-medium text-foreground/90">{title}</div>
      <div className="space-y-1">
        {items.map((it) => (
          <div key={it.label} className="flex items-center gap-2">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ background: rgbCss(it.color) }}
            />
            <span className="text-muted-foreground">{it.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
