"use client";

import { NavLink } from "@/components/nav-link";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/dataset", label: "Dataset" },
  { href: "/training", label: "Training" },
  { href: "/benchmarks", label: "Benchmarks" },
  { href: "/chat", label: "Chat" },
  { href: "/opportunities", label: "Opportunités" },
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
  return <nav className="order-3 lg:order-none w-full lg:w-auto flex items-center gap-1 text-sm whitespace-nowrap overflow-x-auto [&>a]:shrink-0">
    {LINKS.map((item) => <NavLink key={item.href} {...item} />)}
  </nav>;
}
