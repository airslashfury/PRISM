import { ChevronLeft } from "lucide-react";

/**
 * Reusable 7-section entity-detail grammar (extracted from resilience/page.tsx's
 * DetailPanel). Any map-page detail drawer — substation, water source, etc. —
 * assembles the same shape: what / where / depends / hazards / data / changed /
 * actions, each rendered as a PanelBox.
 */
export type DrawerSectionId = "what" | "where" | "depends" | "hazards" | "data" | "changed" | "actions";

export interface DrawerSection {
  id: DrawerSectionId;
  title: string;
  badge?: React.ReactNode;
  rows?: { label: string; value: React.ReactNode }[];
  body?: React.ReactNode;
  hidden?: boolean;
}

export interface EntityDrawerProps {
  header: React.ReactNode;
  sections: DrawerSection[];
  onBack?: () => void;
}

export function EntityDrawer({ header, sections, onBack }: EntityDrawerProps) {
  return (
    <div className="p-4">
      {onBack && (
        <button
          onClick={onBack}
          className="mb-3 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <ChevronLeft className="h-3.5 w-3.5" /> Back to list
        </button>
      )}
      <div className="space-y-4">
        {header}
        {sections
          .filter((s) => !s.hidden)
          .map((s) => (
            <PanelBox key={s.id} title={s.title} badge={s.badge}>
              {s.rows?.map((r) => <Row key={r.label} label={r.label} value={r.value} />)}
              {s.body}
            </PanelBox>
          ))}
      </div>
    </div>
  );
}

export function PanelBox({
  title,
  badge,
  children,
}: {
  title: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border/60 bg-background/30 p-3">
      <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
        {badge}
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

export function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium tnum">{value}</span>
    </div>
  );
}
