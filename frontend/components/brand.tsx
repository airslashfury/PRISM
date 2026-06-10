import { cn } from "@/lib/utils";

/** PRISM mark: a beam entering a prism and refracting into a spectrum. */
export function PrismMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("h-7 w-7", className)} fill="none">
      <defs>
        <linearGradient id="prism-spectrum" x1="16" y1="16" x2="31" y2="20" gradientUnits="userSpaceOnUse">
          <stop stopColor="#22d3ee" />
          <stop offset="0.5" stopColor="#a78bfa" />
          <stop offset="1" stopColor="#f472b6" />
        </linearGradient>
      </defs>
      {/* incoming beam */}
      <path d="M1 16 H13" stroke="#e2e8f0" strokeWidth="1.5" strokeLinecap="round" />
      {/* prism triangle */}
      <path d="M13 7 L25 16 L13 25 Z" stroke="#22d3ee" strokeWidth="1.5" strokeLinejoin="round" />
      {/* refracted spectrum */}
      <path d="M25 16 L31 13" stroke="url(#prism-spectrum)" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M25 16 L31 16" stroke="url(#prism-spectrum)" strokeWidth="1.5" strokeLinecap="round" opacity="0.8" />
      <path d="M25 16 L31 19" stroke="url(#prism-spectrum)" strokeWidth="1.5" strokeLinecap="round" opacity="0.6" />
    </svg>
  );
}

export function BrandWordmark({ collapsed }: { collapsed?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <PrismMark />
      {!collapsed && (
        <div className="leading-tight">
          <div className="text-sm font-semibold tracking-[0.2em] text-foreground">PRISM</div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Infrastructure Intelligence
          </div>
        </div>
      )}
    </div>
  );
}
