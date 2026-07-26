"use client";

import { useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { BrandWordmark } from "@/components/brand";
import { PaneResizer, PaneToggle } from "@/components/ui/resizable-pane";
import { notifyMapResize, usePaneShortcut, usePaneState } from "@/lib/pane-state";
import { NAV, type NavGroup } from "./nav";
import { cn } from "@/lib/utils";

const GROUPS: NavGroup[] = ["Live", "Explore", "Decide", "Reference"];

const NAV_DEFAULT_WIDTH = 240;
const NAV_MIN_WIDTH = 180;
const NAV_MAX_WIDTH = 360;
/** Collapsed: an icon rail wide enough for a 16px icon and its hit target. */
const NAV_RAIL_WIDTH = 56;

export function Sidebar() {
  const pathname = usePathname();
  const pane = usePaneState("nav", {
    defaultWidth: NAV_DEFAULT_WIDTH,
    minWidth: NAV_MIN_WIDTH,
    maxWidth: NAV_MAX_WIDTH,
  });

  const toggle = useCallback(() => {
    pane.toggle();
    notifyMapResize();
  }, [pane]);
  usePaneShortcut("[", toggle);

  const collapsed = pane.collapsed;

  return (
    <>
      <aside
        id="prism-nav-pane"
        data-chrome
        data-pane="nav"
        data-collapsed={collapsed ? "true" : "false"}
        style={{ width: collapsed ? NAV_RAIL_WIDTH : pane.width }}
        className="hidden shrink-0 flex-col border-r border-border/70 bg-card/40 md:flex"
      >
        <div
          className={cn(
            "flex h-16 items-center border-b border-border/70",
            collapsed ? "justify-center px-2" : "justify-between px-5",
          )}
        >
          {!collapsed && (
            <Link href="/">
              <BrandWordmark />
            </Link>
          )}
          <PaneToggle
            collapsed={collapsed}
            side="left"
            onToggle={toggle}
            label={collapsed ? "Expand navigation" : "Collapse navigation"}
            shortcut="["
          />
        </div>

        <nav className={cn("flex-1 space-y-4 overflow-y-auto", collapsed ? "p-2" : "p-3")}>
          {GROUPS.map((group) => (
            <div key={group}>
              {collapsed ? (
                // The group label can't fit in a 56px rail; a rule keeps the
                // grouping legible without pretending the words are still there.
                <div className="mx-auto mb-2 h-px w-6 bg-border/60" aria-hidden />
              ) : (
                <div className="px-2 pb-2 pt-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                  {group}
                </div>
              )}
              <div className="space-y-1">
                {NAV.filter((item) => item.group === group).map((item) => {
                  const active =
                    item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      title={collapsed ? item.label : undefined}
                      aria-label={collapsed ? item.label : undefined}
                      className={cn(
                        "group flex items-center rounded-md py-2 text-sm transition-colors",
                        collapsed ? "justify-center px-2" : "gap-3 px-3",
                        active
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                      )}
                    >
                      <Icon
                        className={cn(
                          "h-4 w-4 shrink-0",
                          active ? "text-primary" : "text-muted-foreground/70 group-hover:text-foreground",
                        )}
                      />
                      {!collapsed && (
                        <>
                          <span className="truncate font-medium">{item.label}</span>
                          {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                        </>
                      )}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className={cn("border-t border-border/70", collapsed ? "p-2" : "p-4")}>
          <div
            className={cn(
              "rounded-lg border border-border/60 bg-background/60",
              collapsed ? "flex justify-center p-2" : "p-3",
            )}
            title={collapsed ? "Model online — PostGIS · EPSG:32161" : undefined}
          >
            <div className={cn("flex items-center text-xs", collapsed ? "" : "gap-2")}>
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
              </span>
              {!collapsed && <span className="text-muted-foreground">Model online</span>}
            </div>
            {!collapsed && (
              <div className="mt-1 text-[10px] text-muted-foreground/70">PostGIS · EPSG:32161</div>
            )}
          </div>
        </div>
      </aside>

      {!collapsed && (
        <PaneResizer
          side="left"
          width={pane.width}
          minWidth={NAV_MIN_WIDTH}
          maxWidth={NAV_MAX_WIDTH}
          onWidth={pane.setWidth}
          onReset={pane.reset}
          label="Resize navigation"
          controls="prism-nav-pane"
          chrome
        />
      )}
    </>
  );
}
