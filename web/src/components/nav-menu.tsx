"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NavLink } from "@/components/nav-link";

const PRIMARY = [
  { href: "/", label: "Dashboard" },
  { href: "/dataset", label: "Dataset" },
  { href: "/training", label: "Training" },
  { href: "/benchmarks", label: "Benchmarks" },
  { href: "/chat", label: "Chat" },
  { href: "/opportunities", label: "Opportunités" },
];

const MANAGEMENT = [
  { href: "/rag", label: "Connaissances RAG" },
  { href: "/enterprise", label: "Entreprise" },
  { href: "/executions", label: "Exécutions" },
  { href: "/providers", label: "Fournisseurs" },
  { href: "/tools", label: "Outils et politiques" },
  { href: "/system", label: "Système" },
  { href: "/docs", label: "Documentation" },
  { href: "/settings", label: "Paramètres" },
];

export function NavMenu() {
  const pathname = usePathname();
  const managementActive = MANAGEMENT.some((item) => pathname.startsWith(item.href));
  return <nav className="order-3 lg:order-none w-full lg:w-auto flex items-center gap-1 text-sm overflow-visible">
    <div className="flex gap-1 overflow-x-auto">{PRIMARY.map((item) => <NavLink key={item.href} {...item} />)}</div>
    <details className="relative group shrink-0">
      <summary className={`list-none cursor-pointer px-3 py-1.5 rounded-md transition-colors ${managementActive ? "bg-accent-soft text-accent-strong" : "text-text-secondary hover:text-text-primary hover:bg-surface-hover"}`}>
        Gestion <span aria-hidden="true" className="ml-1 text-xs">▾</span>
      </summary>
      <div className="absolute top-full right-0 lg:left-0 lg:right-auto mt-2 w-56 rounded-lg border border-border bg-surface p-1.5 shadow-xl z-30">
        {MANAGEMENT.map((item) => {
          const active = pathname.startsWith(item.href);
          return <Link key={item.href} href={item.href} onClick={(event) => event.currentTarget.closest("details")?.removeAttribute("open")} className={`block rounded-md px-3 py-2 ${active ? "bg-accent-soft text-accent-strong" : "text-text-secondary hover:bg-surface-hover hover:text-text-primary"}`}>{item.label}</Link>;
        })}
      </div>
    </details>
  </nav>;
}
