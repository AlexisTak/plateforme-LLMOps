"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { OfflineToggle } from "@/components/offline-toggle";
import { hasRole, useAuth } from "@/lib/auth-context";

// adminOnly: listed in the sidebar only for admins in "login" mode (the page checks too).
type LinkItem = { href: string; label: string; adminOnly?: boolean };

// Core lifecycle stages (Dataset -> Training -> Evaluation -> RAG) plus the
// two most-used surfaces come first; everything else is grouped under its own
// heading. CommandPalette (Cmd+K) still searches every link below regardless
// of grouping.
const PRIMARY: LinkItem[] = [
  { href: "/", label: "Dashboard" },
  { href: "/dataset", label: "Dataset" },
  { href: "/training", label: "Training" },
  { href: "/benchmarks", label: "Benchmarks" },
  { href: "/decision-models", label: "Decision Models" },
  { href: "/rag", label: "Connaissances RAG" },
  { href: "/chat", label: "Chat" },
];

const OPERATE: LinkItem[] = [
  { href: "/executions", label: "Exécutions" },
  { href: "/opportunities", label: "Opportunités" },
];

const PLATFORM: LinkItem[] = [
  { href: "/enterprise", label: "Entreprise" },
  { href: "/users", label: "Utilisateurs", adminOnly: true },
  { href: "/providers", label: "Fournisseurs" },
  { href: "/tools", label: "Outils et politiques" },
  { href: "/system", label: "Système" },
  { href: "/settings", label: "Paramètres" },
  { href: "/docs", label: "Documentation" },
];

export const LINKS: LinkItem[] = [...PRIMARY, ...OPERATE, ...PLATFORM];

function SidebarLink({ href, label }: LinkItem) {
  const pathname = usePathname();
  const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
  return (
    <Link
      href={href}
      className={`block px-3 py-1.5 rounded-md text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg ${
        active ? "bg-accent-soft text-accent-strong" : "text-text-secondary hover:text-text-primary hover:bg-surface-hover"
      }`}
    >
      {label}
    </Link>
  );
}

function SidebarGroup({ heading, items }: { heading?: string; items: LinkItem[] }) {
  const { state, actor } = useAuth();
  const canManageUsers = state?.auth_mode === "login" && hasRole(actor, "admin");
  return (
    <div className="space-y-0.5">
      {heading && <p className="px-3 pt-3 pb-1 text-[10px] uppercase tracking-wider text-text-muted">{heading}</p>}
      {items.filter((item) => !item.adminOnly || canManageUsers).map((item) => (
        <SidebarLink key={item.href} {...item} />
      ))}
    </div>
  );
}

// Vertical sidebar navigation — grouped sections, everything visible at once
// (no dropdowns to open/close), used inside the fixed-width <aside> in
// app/layout.tsx.
export function NavMenu() {
  return (
    <nav className="flex flex-col gap-1 text-sm">
      <SidebarGroup items={PRIMARY} />
      <SidebarGroup heading="Exploiter" items={OPERATE} />
      <SidebarGroup heading="Plateforme" items={PLATFORM} />
      <OfflineToggle />
    </nav>
  );
}
