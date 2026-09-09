"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function NavLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
  return (
    <Link
      href={href}
      className={`px-3 py-1.5 rounded-md transition-colors ${
        active ? "bg-accent-soft text-accent-strong" : "text-text-secondary hover:text-text-primary hover:bg-surface-hover"
      }`}
    >
      {label}
    </Link>
  );
}
