"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

export function HealthBadge() {
  const [ok, setOk] = useState<boolean | null>(null);

  useEffect(() => {
    const check = () => api.health().then((h) => setOk(h.status === "ok")).catch(() => setOk(null));
    check();
    const interval = setInterval(check, 15000);
    return () => clearInterval(interval);
  }, []);

  if (ok === null) return null;

  return (
    <Link href="/system" className="flex items-center gap-1.5 text-xs ml-auto" title={ok ? "Environnement OK" : "Problème détecté — voir System"}>
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-success" : "bg-error animate-pulse"}`} />
      <span className={ok ? "text-text-muted" : "text-error"}>{ok ? "OK" : "Problème"}</span>
    </Link>
  );
}
