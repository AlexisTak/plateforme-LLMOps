"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { NavLink } from "@/components/nav-link";

type LinkItem = { href: string; label: string };

// Core lifecycle stages (Dataset -> Training -> Evaluation -> RAG) plus the
// two most-used surfaces stay inline; everything else is grouped so the bar
// doesn't grow every time a new page is added. CommandPalette (Cmd+K) still
// searches every link below regardless of grouping.
const PRIMARY: LinkItem[] = [
  { href: "/", label: "Dashboard" },
  { href: "/dataset", label: "Dataset" },
  { href: "/training", label: "Training" },
  { href: "/benchmarks", label: "Benchmarks" },
  { href: "/rag", label: "Connaissances RAG" },
  { href: "/chat", label: "Chat" },
];

const OPERATE: LinkItem[] = [
  { href: "/executions", label: "Exécutions" },
  { href: "/opportunities", label: "Opportunités" },
];

const PLATFORM: LinkItem[] = [
  { href: "/enterprise", label: "Entreprise" },
  { href: "/providers", label: "Fournisseurs" },
  { href: "/tools", label: "Outils et politiques" },
  { href: "/system", label: "Système" },
  { href: "/settings", label: "Paramètres" },
  { href: "/docs", label: "Documentation" },
];

export const LINKS: LinkItem[] = [...PRIMARY, ...OPERATE, ...PLATFORM];

function NavGroup({ label, items }: { label: string; items: LinkItem[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const pathname = usePathname();
  const active = items.some((item) => pathname.startsWith(item.href));

  useEffect(() => {
    if (!open) return;
    const onClickOutside = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onEscape);
    };
  }, [open]);

  return (
    <div className="relative shrink-0" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className={`flex items-center gap-1 px-3 py-1.5 rounded-md text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg ${
          active ? "bg-accent-soft text-accent-strong" : "text-text-secondary hover:text-text-primary hover:bg-surface-hover"
        }`}
      >
        {label}
        <span aria-hidden className={`text-[10px] transition-transform ${open ? "rotate-180" : ""}`}>▾</span>
      </button>
      {open && (
        <div role="menu" className="absolute top-full left-0 mt-1 bg-surface border border-border rounded-lg shadow-lg py-1 min-w-[13rem] z-20">
          {items.map((item) => {
            const itemActive = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                role="menuitem"
                onClick={() => setOpen(false)}
                className={`block px-3 py-1.5 text-sm transition-colors ${
                  itemActive ? "bg-accent-soft text-accent-strong" : "text-text-secondary hover:text-text-primary hover:bg-surface-hover"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function NavMenu() {
  // flex-wrap, not overflow-x-auto: an ancestor with overflow-x set to
  // anything but visible forces overflow-y to auto too (CSS2.1 overflow
  // rules), which would clip the absolutely-positioned dropdown panels
  // below. Wrapping to a second line on narrow viewports keeps the panels
  // visible instead.
  return (
    <nav className="order-3 lg:order-none w-full lg:w-auto flex flex-wrap items-center gap-1 text-sm">
      {PRIMARY.map((item) => <NavLink key={item.href} {...item} />)}
      <NavGroup label="Exploiter" items={OPERATE} />
      <NavGroup label="Plateforme" items={PLATFORM} />
    </nav>
  );
}
