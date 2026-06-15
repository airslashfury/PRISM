"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";

import { BrandWordmark } from "@/components/brand";
import { NAV } from "./nav";
import { cn } from "@/lib/utils";

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = prevOverflow;
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open navigation"
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent/60 hover:text-foreground active:bg-accent md:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      {mounted &&
        open &&
        createPortal(
          <div className="fixed inset-0 z-[100] md:hidden">
            <div
              className="absolute inset-0 bg-background/80 backdrop-blur-sm animate-in fade-in duration-200"
              onClick={() => setOpen(false)}
            />
            <div className="absolute inset-y-0 left-0 flex w-64 flex-col border-r border-border/70 bg-card shadow-xl animate-in slide-in-from-left duration-200">
              <div className="flex h-16 items-center justify-between border-b border-border/70 px-5">
                <Link href="/" onClick={() => setOpen(false)}>
                  <BrandWordmark />
                </Link>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="Close navigation"
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <nav className="flex-1 space-y-1 overflow-y-auto p-3">
                <div className="px-2 pb-2 pt-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                  Modules
                </div>
                {NAV.map((item) => {
                  const active =
                    item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setOpen(false)}
                      className={cn(
                        "group flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
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
                      <span className="font-medium">{item.label}</span>
                      {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
                    </Link>
                  );
                })}
              </nav>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
