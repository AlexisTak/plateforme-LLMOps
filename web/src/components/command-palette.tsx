"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { LINKS } from "@/components/nav-menu";

export function normalizeForSearch(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

export function filterLinks(query: string): typeof LINKS {
  const q = normalizeForSearch(query.trim());
  if (!q) return LINKS;
  return LINKS.filter((link) => normalizeForSearch(link.label).includes(q));
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const router = useRouter();

  const results = useMemo(() => filterLinks(query), [query]);

  const close = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  const navigate = (href: string) => {
    close();
    router.push(href);
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        triggerRef.current = document.activeElement as HTMLElement;
        setOpen(true);
        setActiveIndex(0);
        setQuery("");
      }
    };

    if (open) {
      inputRef.current?.focus();
    } else {
      window.addEventListener("keydown", handleKeyDown);
      return () => window.removeEventListener("keydown", handleKeyDown);
    }
  }, [open]);

  const onInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (results[activeIndex]) navigate(results[activeIndex].href);
    } else if (e.key === "Escape") {
      close();
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-24 px-4" onClick={close}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Palette de commandes"
        className="bg-surface border border-border rounded-lg w-full max-w-md shadow-lg"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            close();
          }
        }}
      >
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActiveIndex(0);
          }}
          onKeyDown={onInputKeyDown}
          placeholder="Aller à…"
          className="w-full bg-transparent px-4 py-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none border-b border-border"
        />
        <ul className="max-h-72 overflow-y-auto py-1">
          {results.length === 0 && <li className="px-4 py-2 text-sm text-text-muted">Aucun résultat.</li>}
          {results.map((link, i) => (
            <li key={link.href}>
              <button
                type="button"
                onClick={() => navigate(link.href)}
                className={`w-full text-left px-4 py-2 text-sm transition-colors ${
                  i === activeIndex ? "bg-accent-soft text-accent-strong" : "text-text-secondary hover:bg-surface-hover hover:text-text-primary"
                }`}
              >
                {link.label}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

if (process.env.NODE_ENV !== "production") {
  console.assert(
    filterLinks("executions").some((l) => l.label === "Exécutions"),
    "command-palette: normalizeForSearch should strip accents"
  );
  console.assert(filterLinks("").length === LINKS.length, "command-palette: empty query should return all links");
  console.assert(filterLinks("zzz-inexistant").length === 0, "command-palette: no-match query should return empty");
}
