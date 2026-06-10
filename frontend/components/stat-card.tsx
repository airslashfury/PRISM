import { type LucideIcon } from "lucide-react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  accent = "primary",
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  icon?: LucideIcon;
  accent?: "primary" | "emerald" | "amber" | "violet" | "rose";
}) {
  const accentBar = {
    primary: "bg-primary",
    emerald: "bg-emerald-400",
    amber: "bg-amber-400",
    violet: "bg-violet-400",
    rose: "bg-rose-400",
  }[accent];

  return (
    <Card className="relative overflow-hidden">
      <div className={cn("absolute inset-y-0 left-0 w-0.5", accentBar)} />
      <div className="p-5">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            {label}
          </span>
          {Icon && <Icon className="h-4 w-4 text-muted-foreground/70" />}
        </div>
        <div className="mt-2 text-2xl font-semibold tracking-tight tnum">{value}</div>
        {sub != null && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
      </div>
    </Card>
  );
}
