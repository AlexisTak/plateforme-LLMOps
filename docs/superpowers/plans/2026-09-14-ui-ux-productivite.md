# UI/UX productivité interne — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the 16 frontend pages consistent, French, error/success/loading feedback (structured API errors, toasts, skeletons, confirm dialogs, keyboard focus rings) plus a ⌘K command palette, without any new npm dependency or visual redesign.

**Architecture:** One shared layer (`ApiError`, `humanError`, `useAction`, `ToastProvider`, five new `ui.tsx` primitives, `CommandPalette`) built and self-checked first, then applied mechanically to all 16 pages plus `project-switcher.tsx`.

**Tech Stack:** Next.js 16.3.1, React 19, TypeScript strict, Tailwind (via CSS custom properties in `globals.css`). No test framework — verification is `npx tsc --noEmit`, `console.assert` in dev mode for pure functions, and manual browser walkthrough.

**Spec:** `docs/superpowers/specs/2026-09-14-ui-ux-productivite-design.md`

## Global Constraints

- Next.js 16.3.1 / React 19 / TypeScript strict — read `web/node_modules/next/dist/docs/` before writing Next-specific code (conventions diverge from upstream).
- No new npm dependency. Every primitive is hand-written.
- `web/src/app/globals.css` tokens do not change. No new colors.
- All user-visible text is French.
- The backend is not touched. The 89 `pytest` tests are the regression guard and must stay green untouched.
- No JS test framework exists. Verification per task is `npx tsc --noEmit` (from `web/`), `console.assert` in dev mode for the two pure functions (`humanError`, the palette's `filterLinks`), and a manual browser walkthrough (full pass only in the final task).
- Every file path below is relative to `web/src/` unless stated otherwise.
- `focus-visible` ring, applied everywhere the constraints below call for it, uses exactly this Tailwind class string: `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg`.

---

## Task 1: `ApiError` + `humanError`

**Files:**
- Modify: `web/src/lib/api.ts:1-14`
- Create: `web/src/lib/errors.ts`

**Interfaces:**
- Produces: `export class ApiError extends Error { constructor(readonly status: number, readonly path: string, readonly detail: string) }` from `lib/api.ts`; `export function humanError(e: unknown): string` from `lib/errors.ts`. Every later task imports both.

- [ ] **Step 1: Add `ApiError` and structure `request()`'s error path**

Replace `web/src/lib/api.ts:1-14`:

```ts
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${path}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}
```

with:

```ts
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(readonly status: number, readonly path: string, readonly detail: string) {
    super(`${status} ${path}: ${detail}`);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      // body wasn't JSON — keep the raw text as detail
    }
    throw new ApiError(res.status, path, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}
```

Leave the two other throw sites (`api.ts:408` in `chat.stream`, `api.ts:445` in `rag.uploadDocument`) untouched — they keep throwing a plain `Error`, and `humanError` (Step 2) has a branch for that.

- [ ] **Step 2: Create `lib/errors.ts`**

```ts
import { ApiError } from "@/lib/api";

export function humanError(e: unknown): string {
  if (e instanceof ApiError && e.detail) return e.detail;
  if (e instanceof ApiError) return `Erreur ${e.status} — le serveur n'a pas pu traiter la demande.`;
  if (e instanceof TypeError) {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
    return `API injoignable — vérifie que le backend tourne sur ${apiUrl}.`;
  }
  return e instanceof Error ? e.message : String(e);
}

if (process.env.NODE_ENV !== "production") {
  console.assert(
    humanError(new ApiError(404, "/api/x", "Opportunité introuvable")) === "Opportunité introuvable",
    "humanError: doit renvoyer le detail structuré tel quel",
  );
  console.assert(
    humanError(new ApiError(500, "/api/x", "")) === "Erreur 500 — le serveur n'a pas pu traiter la demande.",
    "humanError: doit renvoyer un message générique quand detail est vide",
  );
  console.assert(
    humanError(new TypeError("Failed to fetch")).startsWith("API injoignable"),
    "humanError: doit détecter une erreur réseau (TypeError de fetch)",
  );
  console.assert(humanError(new Error("boom")) === "boom", "humanError: doit retomber sur Error.message");
}
```

- [ ] **Step 3: Verify**

Run: `cd web && npx tsc --noEmit`
Expected: no errors. Then run `npm run dev` once, open any page in a browser, and check the console for failed `console.assert` calls (none expected).

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/api.ts web/src/lib/errors.ts
git commit -m "feat(web): structure API errors via ApiError + humanError"
```

---

## Task 2: `useAction` + `ToastProvider`

**Files:**
- Create: `web/src/components/toast.tsx`
- Create: `web/src/lib/use-action.ts`
- Modify: `web/src/app/layout.tsx`

**Interfaces:**
- Consumes: `ApiError` (unused directly), `humanError` from `lib/errors.ts` (Task 1).
- Produces: `export function ToastProvider({ children }: { children: ReactNode })`, `export function useToast(): (message: string, kind?: "success" | "error") => void` from `components/toast.tsx`; `export function useAction<Args extends unknown[], R>(fn: (...args: Args) => Promise<R>, opts?: { success?: string | ((result: R) => string) }): { run: (...args: Args) => Promise<R | undefined>; busy: boolean; error: string | null }` from `lib/use-action.ts`. Tasks 5-7 call `useAction` for every mutating action.

- [ ] **Step 1: Create `components/toast.tsx`**

```tsx
"use client";

import { createContext, ReactNode, useCallback, useContext, useRef, useState } from "react";

type ToastKind = "success" | "error";
type ToastItem = { id: number; message: string; kind: ToastKind };

const ToastContext = createContext<((message: string, kind?: ToastKind) => void) | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(0);

  const push = useCallback((message: string, kind: ToastKind = "success") => {
    const id = nextId.current++;
    setToasts((current) => [...current, { id, message, kind }].slice(-3));
    setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), 4000);
  }, []);

  const dismiss = (id: number) => setToasts((current) => current.filter((t) => t.id !== id));

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div aria-live="polite" role="status" className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-[min(22rem,calc(100vw-2rem))]">
        {toasts.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => dismiss(t.id)}
            className={`text-left rounded-md border px-3.5 py-2.5 text-sm shadow-lg transition-colors ${
              t.kind === "success" ? "bg-success-soft border-success/30 text-success" : "bg-error-soft border-error/30 text-error"
            }`}
          >
            {t.message}
          </button>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const push = useContext(ToastContext);
  if (!push) throw new Error("useToast doit être utilisé sous ToastProvider");
  return push;
}
```

- [ ] **Step 2: Create `lib/use-action.ts`**

```ts
"use client";

import { useState } from "react";
import { humanError } from "@/lib/errors";
import { useToast } from "@/components/toast";

export function useAction<Args extends unknown[], R>(
  fn: (...args: Args) => Promise<R>,
  opts?: { success?: string | ((result: R) => string) },
) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const run = async (...args: Args): Promise<R | undefined> => {
    if (busy) return undefined;
    setBusy(true);
    setError(null);
    try {
      const result = await fn(...args);
      if (opts?.success) toast(typeof opts.success === "function" ? opts.success(result) : opts.success, "success");
      return result;
    } catch (e) {
      const message = humanError(e);
      setError(message);
      toast(message, "error");
      return undefined;
    } finally {
      setBusy(false);
    }
  };

  return { run, busy, error };
}
```

- [ ] **Step 3: Mount `ToastProvider` in `layout.tsx`**

Add the import, alongside the other component imports in `web/src/app/layout.tsx`:

```tsx
import { ToastProvider } from "@/components/toast";
```

Replace the `<ProjectProvider>` block:

```tsx
        <ProjectProvider>
          <header className="relative border-b border-border px-4 sm:px-6 py-3.5 flex flex-wrap items-center gap-x-4 lg:gap-x-8 gap-y-2 sticky top-0 bg-bg/90 backdrop-blur-md shadow-[0_8px_30px_rgba(0,0,0,0.18)] z-10">
            <Link href="/" aria-label="OpenAgent — Accueil" className="shrink-0 rounded-lg bg-white px-2 py-1 shadow-[0_0_20px_rgba(79,140,255,0.16)] ring-1 ring-white/10 transition-transform hover:scale-[1.02]">
              <Image src="/logo.png" alt="OpenAgent" width={2172} height={724} priority className="h-7 w-auto" />
            </Link>
            <NavMenu />
            <ProjectSwitcher />
            <HealthBadge />
          </header>
          <main className="flex-1 px-6 py-8 max-w-6xl w-full mx-auto">{children}</main>
        </ProjectProvider>
```

with:

```tsx
        <ProjectProvider>
          <ToastProvider>
            <header className="relative border-b border-border px-4 sm:px-6 py-3.5 flex flex-wrap items-center gap-x-4 lg:gap-x-8 gap-y-2 sticky top-0 bg-bg/90 backdrop-blur-md shadow-[0_8px_30px_rgba(0,0,0,0.18)] z-10">
              <Link href="/" aria-label="OpenAgent — Accueil" className="shrink-0 rounded-lg bg-white px-2 py-1 shadow-[0_0_20px_rgba(79,140,255,0.16)] ring-1 ring-white/10 transition-transform hover:scale-[1.02]">
                <Image src="/logo.png" alt="OpenAgent" width={2172} height={724} priority className="h-7 w-auto" />
              </Link>
              <NavMenu />
              <ProjectSwitcher />
              <HealthBadge />
            </header>
            <main className="flex-1 px-6 py-8 max-w-6xl w-full mx-auto">{children}</main>
          </ToastProvider>
        </ProjectProvider>
```

- [ ] **Step 4: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/toast.tsx web/src/lib/use-action.ts web/src/app/layout.tsx
git commit -m "feat(web): add ToastProvider and useAction, mount provider in layout"
```

---

## Task 3: `ui.tsx` primitives, focus ring, French statuses

**Files:**
- Modify: `web/src/components/ui.tsx`
- Modify: `web/src/components/nav-link.tsx`

**Interfaces:**
- Produces: `export function Select(...)`, `export function Textarea(...)`, `export function Field(...)`, `export function Skeleton(...)`, `export function ConfirmDialog(...)` from `components/ui.tsx`. Tasks 5-8 import these.

- [ ] **Step 1: Fix the focus ring on `Input` (`ui.tsx:52-74`)**

Replace the `className` line inside `Input`:

```tsx
      className={`bg-bg border border-border rounded-md px-3 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors ${className}`}
```

with:

```tsx
      className={`bg-bg border border-border rounded-md px-3 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg transition-colors ${className}`}
```

- [ ] **Step 2: Add `Select` and `Textarea` right after `Input` (`ui.tsx`, after line 74)**

```tsx
export function Select({
  value,
  onChange,
  children,
  className = "",
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  children: ReactNode;
  className?: string;
  disabled?: boolean;
}) {
  return (
    <select
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className={`bg-bg border border-border rounded-md px-3 py-1.5 text-sm text-text-primary focus:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg transition-colors ${className}`}
    >
      {children}
    </select>
  );
}

export function Textarea({
  value,
  onChange,
  placeholder,
  rows = 3,
  maxLength,
  className = "",
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
  maxLength?: number;
  className?: string;
  disabled?: boolean;
}) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      maxLength={maxLength}
      disabled={disabled}
      className={`w-full bg-bg border border-border rounded-md px-3 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg transition-colors resize-y ${className}`}
    />
  );
}

export function Field({
  label,
  children,
  hint,
  error,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
  error?: string;
}) {
  return (
    <label className="block text-xs text-text-muted space-y-1">
      <span>{label}</span>
      {children}
      {hint && !error && <span className="block text-text-muted text-xs">{hint}</span>}
      {error && <span className="block text-error text-xs">{error}</span>}
    </label>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-surface-hover ${className}`} />;
}
```

`Field` wraps its `children` inside the `<label>` (native implicit association) instead of generating `htmlFor`/`id` pairs — it reaches the same "clicking the label focuses the field" outcome as the local `Field` components already duplicated in `training/page.tsx` and `settings/page.tsx`, without id-generation boilerplate. Both local copies are deleted in Task 5/Task 8 in favor of this one.

- [ ] **Step 3: Add `ConfirmDialog` after `EmptyState` (end of `ui.tsx`)**

```tsx
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirmer",
  cancelLabel = "Annuler",
  danger,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onCancel}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="bg-surface border border-border rounded-lg p-5 max-w-sm w-full space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="confirm-dialog-title" className="font-display text-base text-text-primary">
          {title}
        </h2>
        {description && <p className="text-text-secondary text-sm">{description}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button variant={danger ? "danger" : "accent"} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: French status labels (`ui.tsx:76-99`)**

Replace the `STATUS_STYLES` block and `StatusBadge`:

```tsx
const STATUS_STYLES: Record<string, { dot: string; text: string }> = {
  running: { dot: "bg-info animate-pulse", text: "text-info" },
  completed: { dot: "bg-success", text: "text-success" },
  failed: { dot: "bg-error", text: "text-error" },
  stopped: { dot: "bg-text-muted", text: "text-text-muted" },
  draft: { dot: "bg-text-muted", text: "text-text-muted" },
  evaluated: { dot: "bg-info", text: "text-info" },
  approved: { dot: "bg-accent", text: "text-accent" },
  pending: { dot: "bg-info animate-pulse", text: "text-info" },
  processing: { dot: "bg-info animate-pulse", text: "text-info" },
  denied: { dot: "bg-error", text: "text-error" },
  production: { dot: "bg-success", text: "text-success" },
  archived: { dot: "bg-text-muted", text: "text-text-muted" },
};

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.stopped;
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${style.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {status}
    </span>
  );
}
```

with:

```tsx
const STATUS_STYLES: Record<string, { dot: string; text: string }> = {
  running: { dot: "bg-info animate-pulse", text: "text-info" },
  completed: { dot: "bg-success", text: "text-success" },
  failed: { dot: "bg-error", text: "text-error" },
  stopped: { dot: "bg-text-muted", text: "text-text-muted" },
  draft: { dot: "bg-text-muted", text: "text-text-muted" },
  evaluated: { dot: "bg-info", text: "text-info" },
  approved: { dot: "bg-accent", text: "text-accent" },
  pending: { dot: "bg-info animate-pulse", text: "text-info" },
  processing: { dot: "bg-info animate-pulse", text: "text-info" },
  denied: { dot: "bg-error", text: "text-error" },
  production: { dot: "bg-success", text: "text-success" },
  archived: { dot: "bg-text-muted", text: "text-text-muted" },
};

const STATUS_LABELS: Record<string, string> = {
  running: "en cours",
  completed: "terminé",
  failed: "échec",
  stopped: "arrêté",
  draft: "brouillon",
  evaluated: "évalué",
  approved: "approuvé",
  pending: "en attente",
  processing: "en traitement",
  denied: "refusé",
  production: "production",
  archived: "archivé",
};

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.stopped;
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${style.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}
```

`running` was added to the French-label table even though the spec's enumeration omitted it: every other key in `STATUS_STYLES` got a translation, and `running` is shown throughout (training jobs, RAG reindex, benchmarks) — leaving it as the sole untranslated status would be inconsistent. A status absent from `STATUS_LABELS` (there is none today) still falls back to the raw value via `?? status`, matching the spec's "un statut absent de la table continue de s'afficher brut" rule.

- [ ] **Step 5: Focus ring on `NavLink`**

Replace `web/src/components/nav-link.tsx:12-14`:

```tsx
      className={`px-3 py-1.5 rounded-md transition-colors ${
        active ? "bg-accent-soft text-accent-strong" : "text-text-secondary hover:text-text-primary hover:bg-surface-hover"
      }`}
```

with:

```tsx
      className={`px-3 py-1.5 rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg ${
        active ? "bg-accent-soft text-accent-strong" : "text-text-secondary hover:text-text-primary hover:bg-surface-hover"
      }`}
```

- [ ] **Step 6: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors (existing pages still compile against the unchanged parts of `ui.tsx`).

- [ ] **Step 7: Commit**

```bash
git add web/src/components/ui.tsx web/src/components/nav-link.tsx
git commit -m "feat(web): add Select/Textarea/Field/Skeleton/ConfirmDialog, fix focus ring, add French status labels"
```

---

## Task 4: `LINKS` export + `CommandPalette`

**Files:**
- Modify: `web/src/components/nav-menu.tsx`
- Create: `web/src/components/command-palette.tsx`
- Modify: `web/src/app/layout.tsx`

**Interfaces:**
- Consumes: `LINKS` from `components/nav-menu.tsx` (this task exports it).
- Produces: `export function CommandPalette(): JSX.Element | null`, `export function filterLinks(query: string): { href: string; label: string }[]` from `components/command-palette.tsx`.

- [ ] **Step 1: Export `LINKS`**

In `web/src/components/nav-menu.tsx:5`, replace:

```tsx
const LINKS = [
```

with:

```tsx
export const LINKS = [
```

- [ ] **Step 2: Create `components/command-palette.tsx`**

```tsx
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

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        triggerRef.current = document.activeElement as HTMLElement;
        setQuery("");
        setActiveIndex(0);
        setOpen(true);
      } else if (e.key === "Escape") {
        setOpen((wasOpen) => {
          if (wasOpen) triggerRef.current?.focus();
          return false;
        });
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const navigate = (href: string) => {
    close();
    router.push(href);
  };

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
    "command-palette: le filtre doit ignorer les accents",
  );
  console.assert(filterLinks("").length === LINKS.length, "command-palette: une requête vide doit renvoyer tous les liens");
  console.assert(filterLinks("zzz-inexistant").length === 0, "command-palette: une requête sans correspondance doit renvoyer une liste vide");
}
```

- [ ] **Step 3: Mount `CommandPalette` in `layout.tsx`**

Add the import:

```tsx
import { CommandPalette } from "@/components/command-palette";
```

Replace:

```tsx
          <ToastProvider>
            <header className="relative border-b border-border px-4 sm:px-6 py-3.5 flex flex-wrap items-center gap-x-4 lg:gap-x-8 gap-y-2 sticky top-0 bg-bg/90 backdrop-blur-md shadow-[0_8px_30px_rgba(0,0,0,0.18)] z-10">
```

with:

```tsx
          <ToastProvider>
            <CommandPalette />
            <header className="relative border-b border-border px-4 sm:px-6 py-3.5 flex flex-wrap items-center gap-x-4 lg:gap-x-8 gap-y-2 sticky top-0 bg-bg/90 backdrop-blur-md shadow-[0_8px_30px_rgba(0,0,0,0.18)] z-10">
```

- [ ] **Step 4: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors. Run `npm run dev`, open the app, press ⌘K (or Ctrl+K), type "executions" (no accent) and confirm "Exécutions" is suggested; press Escape and confirm focus returns to the page.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/nav-menu.tsx web/src/components/command-palette.tsx web/src/app/layout.tsx
git commit -m "feat(web): add command palette (Cmd/Ctrl+K) sourced from nav LINKS"
```

---

## Task 5: Pages `dataset`, `training`, `benchmarks`

**Files:**
- Modify: `web/src/app/dataset/page.tsx`
- Modify: `web/src/app/training/page.tsx`
- Modify: `web/src/app/benchmarks/page.tsx`

**Interfaces:**
- Consumes: `useAction` (Task 2), `Skeleton`, `ConfirmDialog`, `Field` (Task 3) from their respective modules.

**Convention used in this task and Tasks 6-7:** an action wired to `useAction` gets a `success` option only when the page has no other persistent inline element already confirming the result (a result card, an updated list). Actions that already render their own result inline (e.g. `runValidate`'s validation card) use `useAction` for busy/error handling only, without a `success` message, since a toast would just repeat what's already on screen.

### `dataset/page.tsx`

- [ ] **Step 1: Replace imports (line 1-7)**

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { api, CurrentDatasetVersion, DatasetCategorySummary, DatasetExample, Message, ValidationResult, DatasetStats } from "@/lib/api";
import { Button, Card, ConfirmDialog, EmptyState, Input, PageHeader, Pill, SectionTitle, Skeleton } from "@/components/ui";
import { BarChart } from "@/components/bar-chart";
import { useProject } from "@/lib/project-context";
import { useAction } from "@/lib/use-action";
```

- [ ] **Step 2: Replace the `busy` state and the three handlers (lines 18, 46-92) with three `useAction` hooks**

Remove `const [busy, setBusy] = useState(false);` (line 18).

Replace `runValidate`, `runPrepare`, `runDeduplicate` (lines 46-92):

```tsx
  const validateAction = useAction(() => api.dataset.validate(projectId!));
  const runValidate = async () => {
    const result = await validateAction.run();
    if (result) setValidation(result);
  };

  const prepareAction = useAction((version: string) => api.dataset.prepare(projectId!, version));
  const runPrepare = async () => {
    if (!projectId) return;
    setPrepareResult(null);
    const res = await prepareAction.run(prepareVersion);
    if (res) {
      setPrepareResult(`${res.version} — train ${res.train} · validation ${res.validation} · test ${res.test}`);
      refreshVersion();
    }
  };

  const [pendingDedup, setPendingDedup] = useState<{ count: number; sample: string; more: string; total: number } | null>(null);
  const deduplicateAction = useAction((dryRun: boolean) => api.dataset.deduplicate(projectId!, dryRun));
  const runDeduplicate = async () => {
    if (!projectId) return;
    setDedupResult(null);
    const preview = await deduplicateAction.run(true);
    if (!preview) return;
    if (preview.duplicates.length === 0) {
      setDedupResult("Aucun doublon exact trouvé.");
      return;
    }
    const sample = preview.duplicates.slice(0, 10).map((d) => `${d.file}:${d.line}`).join(", ");
    const more = preview.duplicates.length > 10 ? ` (+${preview.duplicates.length - 10} autre(s))` : "";
    setPendingDedup({ count: preview.duplicates.length, sample, more, total: preview.total_before });
  };
  const confirmDeduplicate = async () => {
    if (!pendingDedup) return;
    setPendingDedup(null);
    const res = await deduplicateAction.run(false);
    if (res) {
      setDedupResult(`${res.removed} doublon(s) exact(s) supprimé(s) sur ${res.total_before} exemples.`);
      refreshCategories();
      if (selected) api.dataset.list(projectId!, selected).then(setExamples);
    }
  };

  const anyBusy = validateAction.busy || prepareAction.busy || deduplicateAction.busy;
```

This preserves the original two-step deduplicate flow (dry run → confirm → real run) but replaces `window.confirm` with `ConfirmDialog` state, and folds `setBusy`/`try`/`catch` into the two `useAction` calls.

- [ ] **Step 3: Update the three buttons (lines 130-136) to use `anyBusy`**

Replace:

```tsx
            <Button variant="ghost" onClick={runDeduplicate} disabled={busy}>
              Dédupliquer
            </Button>
            <Button onClick={runValidate} disabled={busy}>
              Valider le dataset
            </Button>
```

with:

```tsx
            <Button variant="ghost" onClick={runDeduplicate} disabled={anyBusy}>
              Dédupliquer
            </Button>
            <Button onClick={runValidate} disabled={anyBusy}>
              Valider le dataset
            </Button>
```

- [ ] **Step 4: Render the `ConfirmDialog` and validation error, and fix the `Reconstruire` button's `disabled`**

Add right after the `<PageHeader .../>` closing tag (before the `grid grid-cols-4` div):

```tsx
      <ConfirmDialog
        open={!!pendingDedup}
        title="Supprimer les doublons exacts ?"
        description={pendingDedup ? `${pendingDedup.count} doublon(s) exact(s) trouvé(s) sur ${pendingDedup.total} exemples : ${pendingDedup.sample}${pendingDedup.more}` : undefined}
        confirmLabel="Supprimer"
        danger
        onConfirm={confirmDeduplicate}
        onCancel={() => setPendingDedup(null)}
      />
```

In the "Reconstruire les splits" section (around line 290), replace:

```tsx
          <Button onClick={runPrepare} disabled={busy}>
```

with:

```tsx
          <Button onClick={runPrepare} disabled={anyBusy}>
```

- [ ] **Step 5: `deleteExample` confirm → `ConfirmDialog` (lines 94-100)**

Replace:

```tsx
  const deleteExample = async (ex: DatasetExample) => {
    if (!selected || !projectId) return;
    if (!confirm(`Supprimer l'exemple #${ex.index} de ${ex.file} ?`)) return;
    await api.dataset.remove(projectId, selected, ex.id);
    api.dataset.list(projectId, selected).then(setExamples);
    refreshCategories();
  };
```

with:

```tsx
  const [pendingDelete, setPendingDelete] = useState<DatasetExample | null>(null);
  const deleteExample = (ex: DatasetExample) => setPendingDelete(ex);
  const confirmDeleteExample = async () => {
    if (!selected || !projectId || !pendingDelete) return;
    const ex = pendingDelete;
    setPendingDelete(null);
    await api.dataset.remove(projectId, selected, ex.id);
    api.dataset.list(projectId, selected).then(setExamples);
    refreshCategories();
  };
```

Add a second `ConfirmDialog` next to the deduplicate one:

```tsx
      <ConfirmDialog
        open={!!pendingDelete}
        title="Supprimer cet exemple ?"
        description={pendingDelete ? `Exemple #${pendingDelete.index} de ${pendingDelete.file}` : undefined}
        confirmLabel="Supprimer"
        danger
        onConfirm={confirmDeleteExample}
        onCancel={() => setPendingDelete(null)}
      />
```

- [ ] **Step 6: Loading skeleton for the category list (before line 225, `{categories.length > 0 && (`)**

The category sidebar (lines 234-251) renders nothing while `categories` is still `[]` during the initial load, with no distinguishable loading state. Add a `loadingCategories` flag and a skeleton:

Add state near the other `useState` calls: `const [loadingCategories, setLoadingCategories] = useState(true);`

In `refreshCategories`, wrap the categories call:

```tsx
  const refreshCategories = () => {
    if (!projectId) return;
    api.dataset.categories(projectId).then((next) => { setCategories(next); setLoadingCategories(false); });
    api.dataset.stats(projectId).then(setStats);
  };
```

Replace the sidebar's opening (`<div className="space-y-1">`, line 235) content:

```tsx
        <div className="space-y-1">
          {loadingCategories ? (
            <>
              <Skeleton className="h-9" />
              <Skeleton className="h-9" />
              <Skeleton className="h-9" />
            </>
          ) : (
            categories.map((cat) => (
```

...and close the added `)` after the existing `))}` that closes the `.map`.

- [ ] **Step 7: `NewExampleCard`'s `setError(String(e))` (lines 401-417) → `humanError`**

Replace:

```tsx
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    if (!userContent.trim() || !assistantContent.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await onSave(file.trim(), [
        { role: "user", content: userContent.trim() },
        { role: "assistant", content: assistantContent.trim() },
      ]);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };
```

with:

```tsx
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    if (!userContent.trim() || !assistantContent.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await onSave(file.trim(), [
        { role: "user", content: userContent.trim() },
        { role: "assistant", content: assistantContent.trim() },
      ]);
    } catch (e) {
      setError(humanError(e));
    } finally {
      setSaving(false);
    }
  };
```

Add `import { humanError } from "@/lib/errors";` to the top imports.

- [ ] **Step 8: `ExampleCard`'s edit textarea (lines 344-357) → `Textarea`**

Replace:

```tsx
        {draft.map((m, i) => (
          <div key={i} className="flex gap-3 text-sm items-start">
            <span className="text-text-muted uppercase text-[11px] tracking-wide w-16 shrink-0 pt-1.5 font-medium">{m.role}</span>
            <textarea
              value={m.content}
              onChange={(e) => {
                const next = [...draft];
                next[i] = { ...next[i], content: e.target.value };
                setDraft(next);
              }}
              rows={3}
              className="flex-1 bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent transition-colors font-mono"
            />
          </div>
        ))}
```

with:

```tsx
        {draft.map((m, i) => (
          <div key={i} className="flex gap-3 text-sm items-start">
            <span className="text-text-muted uppercase text-[11px] tracking-wide w-16 shrink-0 pt-1.5 font-medium">{m.role}</span>
            <Textarea
              value={m.content}
              onChange={(v) => {
                const next = [...draft];
                next[i] = { ...next[i], content: v };
                setDraft(next);
              }}
              rows={3}
              className="flex-1 font-mono"
            />
          </div>
        ))}
```

- [ ] **Step 9: `NewExampleCard`'s per-role textarea (lines 424-434) → `Textarea`**

Replace:

```tsx
      {ROLES.map((role) => (
        <div key={role} className="flex gap-3 text-sm items-start">
          <span className="text-text-muted uppercase text-[11px] tracking-wide w-16 shrink-0 pt-1.5 font-medium">{role}</span>
          <textarea
            value={role === "user" ? userContent : assistantContent}
            onChange={(e) => (role === "user" ? setUserContent(e.target.value) : setAssistantContent(e.target.value))}
            rows={3}
            placeholder={role === "user" ? "Message utilisateur…" : 'Réponse assistant… (JSON si structuré, ex: {"intent": "..."})'}
            className="flex-1 bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors font-mono"
          />
        </div>
      ))}
```

with:

```tsx
      {ROLES.map((role) => (
        <div key={role} className="flex gap-3 text-sm items-start">
          <span className="text-text-muted uppercase text-[11px] tracking-wide w-16 shrink-0 pt-1.5 font-medium">{role}</span>
          <Textarea
            value={role === "user" ? userContent : assistantContent}
            onChange={role === "user" ? setUserContent : setAssistantContent}
            rows={3}
            placeholder={role === "user" ? "Message utilisateur…" : 'Réponse assistant… (JSON si structuré, ex: {"intent": "..."})'}
            className="flex-1 font-mono"
          />
        </div>
      ))}
```

Add `Textarea` to the `components/ui` import from Step 1.

- [ ] **Step 10: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors.

### `training/page.tsx`

- [ ] **Step 1: Update imports (lines 1-9)**

Replace:

```tsx
"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, JobStatus, ModelPreflight, Project, TrainingConfigSummary, TrainingMetricPoint } from "@/lib/api";
import { Button, Card, EmptyState, Input, PageHeader, Pill, SectionTitle, StatusBadge } from "@/components/ui";
import { LineChart } from "@/components/line-chart";
```

with:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, JobStatus, ModelPreflight, Project, TrainingConfigSummary, TrainingMetricPoint } from "@/lib/api";
import { Button, Card, EmptyState, Field, Input, PageHeader, Pill, SectionTitle, Skeleton, StatusBadge } from "@/components/ui";
import { LineChart } from "@/components/line-chart";
import { useAction } from "@/lib/use-action";
```

(`ReactNode` is dropped because the local `Field` function — Step 5 below — is deleted in favor of the shared one.)

- [ ] **Step 2: `createConfig`'s `setError(String(e))` → `useAction` (lines 41, 106-130)**

Remove `const [newConfigError, setNewConfigError] = useState<string | null>(null);` (line 41).

Replace `createConfig` (lines 106-130):

```tsx
  const createConfigAction = useAction(
    (params: Parameters<typeof api.training.createConfig>[1]) => api.training.createConfig(projectId, params),
    { success: (cfg) => `Config ${cfg.filename} créée.` },
  );
  const createConfig = async () => {
    if (!newConfigName.trim() || !newConfigDatasetVersion.trim() || !projectId) return;
    const created = await createConfigAction.run({
      name: newConfigName.trim(),
      notes: newConfigNotes.trim() || undefined,
      dataset_version: newConfigDatasetVersion.trim(),
      lora_r: newConfigR,
      lora_alpha: newConfigAlpha === "" ? undefined : newConfigAlpha,
      lora_dropout: newConfigDropout,
      epochs: newConfigEpochs,
      learning_rate: newConfigLr,
      batch_size: newConfigBatchSize,
      gradient_accumulation_steps: newConfigGradAccum,
      warmup_steps: newConfigWarmup,
    });
    if (created) {
      setNewConfigName("");
      setNewConfigNotes("");
      setNewConfigOpen(false);
      refresh();
    }
  };
```

- [ ] **Step 3: Update the "Nouvelle config" card's error display and submit button (around lines 232, 266-272)**

Replace:

```tsx
            {newConfigError && <p className="text-error text-sm">{newConfigError}</p>}
```

with:

```tsx
            {createConfigAction.error && <p className="text-error text-sm">{createConfigAction.error}</p>}
```

Replace:

```tsx
            <Button
              variant="accent"
              onClick={createConfig}
              disabled={!newConfigName.trim() || !newConfigDatasetVersion.trim()}
            >
              Créer la config
            </Button>
```

with:

```tsx
            <Button
              variant="accent"
              onClick={createConfig}
              disabled={createConfigAction.busy || !newConfigName.trim() || !newConfigDatasetVersion.trim()}
            >
              {createConfigAction.busy ? "Création…" : "Créer la config"}
            </Button>
```

- [ ] **Step 4: Loading skeleton for the configs grid (around line 288, `<div className="grid gap-4 sm:grid-cols-3">`)**

The configs grid renders empty (no `EmptyState`, no loading marker) until the first `api.training.configs` response lands. Add `const [configsLoaded, setConfigsLoaded] = useState(false);` near the other state, set it in `refresh`'s `.then` callback (`api.training.configs(projectId).then((next) => { setConfigs(next); setConfigsLoaded(true); ...`), and wrap the grid:

```tsx
        {!configsLoaded ? (
          <div className="grid gap-4 sm:grid-cols-3">
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-3">
            {configs.map((cfg) => (
```

...closing the added `)` after the `))}` / `</div>` that currently ends this block.

- [ ] **Step 5: Delete the local `Field` function (lines 397-404), keep `NumberInput` (lines 406-427) as-is**

Remove:

```tsx
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-text-muted">
      {label}
      {children}
    </label>
  );
}
```

The call sites (`<Field label="Nom">…</Field>` etc., lines 234-263) need no change — the shared `Field` from `ui.tsx` has the same `{ label, children }` shape.

- [ ] **Step 6: Replace the two raw `<select>` elements (lines 168-178 and 424 area for `<input type="number">` — leave the number input, it's not a `<select>`) with `Select`**

Replace (pipeline config picker, lines 168-178):

```tsx
            <select
              value={pipelineConfig}
              onChange={(e) => setPipelineConfig(e.target.value)}
              className="bg-bg border border-border rounded-md px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent transition-colors"
            >
              {configs.map((cfg) => (
                <option key={cfg.filename} value={cfg.filename}>
                  {cfg.filename} (r={cfg.lora_r})
                </option>
              ))}
            </select>
```

with:

```tsx
            <Select value={pipelineConfig} onChange={setPipelineConfig}>
              {configs.map((cfg) => (
                <option key={cfg.filename} value={cfg.filename}>
                  {cfg.filename} (r={cfg.lora_r})
                </option>
              ))}
            </Select>
```

Add `Select` to the `components/ui` import from Step 1.

- [ ] **Step 7: Fix the focus ring on the local `NumberInput` (lines 417-427)**

`NumberInput` is a page-local component for the nine numeric hyperparameter fields (r, alpha, dropout, epochs, learning rate, batch size, gradient accumulation, warmup) — there's no shared numeric-input primitive in the spec's architecture, so this is a direct class-string fix rather than a primitive swap. Replace its `className`:

```tsx
      className="bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent transition-colors"
```

with:

```tsx
      className="bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary focus:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg transition-colors"
```

- [ ] **Step 8: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors.

### `benchmarks/page.tsx`

- [ ] **Step 1: Update imports (lines 1-8)**

Replace:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { api, BenchmarkCase, EvalSummaryMetric, EvaluationReport, JobStatus, ModelPreflight } from "@/lib/api";
import { DonutChart } from "@/components/donut-chart";
import { Button, Card, EmptyState, Input, PageHeader, Pill, SectionTitle, StatusBadge } from "@/components/ui";
import { useProject } from "@/lib/project-context";
import { ModelPreflightCard } from "@/components/model-preflight-card";
```

with:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { api, BenchmarkCase, EvalSummaryMetric, EvaluationReport, JobStatus, ModelPreflight } from "@/lib/api";
import { DonutChart } from "@/components/donut-chart";
import { Button, Card, ConfirmDialog, EmptyState, Input, PageHeader, Pill, SectionTitle, Skeleton, StatusBadge, Textarea } from "@/components/ui";
import { useProject } from "@/lib/project-context";
import { ModelPreflightCard } from "@/components/model-preflight-card";
import { useAction } from "@/lib/use-action";
```

- [ ] **Step 2: Replace `error`/`removeCase` state and handler (lines 24, 92-100) with `useAction` + `ConfirmDialog`**

Keep `const [error, setError] = useState<string | null>(null);` for `run`, `refresh` and `saveCase` (they already carry their own inline error `Card`, so they keep manual `setError(String(e))` → change to `setError(humanError(e))`, wired via `import { humanError } from "@/lib/errors";`).

Replace `removeCase` (lines 92-100):

```tsx
  const [pendingRemove, setPendingRemove] = useState<BenchmarkCase | null>(null);
  const removeCaseAction = useAction((item: BenchmarkCase) => api.evaluation.removeCase(projectId, item.id), {
    success: "Cas de benchmark supprimé.",
  });
  const removeCase = (item: BenchmarkCase) => setPendingRemove(item);
  const confirmRemoveCase = async () => {
    if (!pendingRemove) return;
    const item = pendingRemove;
    setPendingRemove(null);
    await removeCaseAction.run(item);
    if (editing !== "new" && editing?.id === item.id) setEditing(null);
    await refresh();
  };
```

- [ ] **Step 3: Wire the confirm dialog and the delete button**

The delete button already calls `removeCase(item)` (line 145, `onClick={() => removeCase(item)}`) — no change needed there since `removeCase`'s new signature still takes `item`.

Add near the top of the returned JSX, after `<ModelPreflightCard .../>`:

```tsx
      <ConfirmDialog
        open={!!pendingRemove}
        title="Supprimer ce cas de benchmark ?"
        description={pendingRemove ? `« ${pendingRemove.id} » sera supprimé définitivement.` : undefined}
        confirmLabel="Supprimer"
        danger
        onConfirm={confirmRemoveCase}
        onCancel={() => setPendingRemove(null)}
      />
```

- [ ] **Step 4: `setError(String(e))` → `setError(humanError(e))` (lines 46, 61, 63, 74, 87)**

Each of the five remaining `setError(String(e))` call sites in `run`, `refresh`'s `.catch`, the job-polling effect, and `saveCase` becomes `setError(humanError(e))`. Add `import { humanError } from "@/lib/errors";`.

- [ ] **Step 5: Loading skeleton for the cases list (around line 126, before `{cases.length === 0 ? ... }`)**

Add `const [casesLoaded, setCasesLoaded] = useState(false);`; set it to `true` inside `refresh`'s `.then` callback. Wrap:

```tsx
        {!casesLoaded ? (
          <div className="grid gap-3 md:grid-cols-2">
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
          </div>
        ) : cases.length === 0 ? <EmptyState>Aucun cas de benchmark.</EmptyState> : (
```

- [ ] **Step 6: Replace the two inline `<textarea>` in `BenchmarkCaseEditor` (lines 236, 245) with `Textarea`**

Replace:

```tsx
    <label className="block text-xs text-text-muted">Question envoyée au modèle<textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={4} className="w-full mt-1 bg-bg border border-border rounded-md px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent" /></label>
```

with:

```tsx
    <label className="block text-xs text-text-muted">Question envoyée au modèle<Textarea value={prompt} onChange={setPrompt} rows={4} className="mt-1" /></label>
```

Replace:

```tsx
    <label className="block text-xs text-text-muted">Critères de revue humaine — un par ligne<textarea value={review} onChange={(e) => setReview(e.target.value)} rows={3} className="w-full mt-1 bg-bg border border-border rounded-md px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent" /></label>
```

with:

```tsx
    <label className="block text-xs text-text-muted">Critères de revue humaine — un par ligne<Textarea value={review} onChange={setReview} rows={3} className="mt-1" /></label>
```

- [ ] **Step 7: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add web/src/app/dataset/page.tsx web/src/app/training/page.tsx web/src/app/benchmarks/page.tsx
git commit -m "feat(web): apply useAction/ConfirmDialog/Skeleton to dataset, training, benchmarks"
```

---

## Task 6: Pages `chat`, `rag`, `providers`, `tools`

**Files:**
- Modify: `web/src/app/chat/page.tsx`
- Modify: `web/src/app/rag/page.tsx`
- Modify: `web/src/app/providers/page.tsx`
- Modify: `web/src/app/tools/page.tsx`

### `chat/page.tsx` — the risk task

**Do not wrap the message input in a `<form>`.** The spec's identified risk is exactly this: `chat/page.tsx` sends on `Enter` and inserts a newline on `Shift+Enter` via `onKeyDown` on line 218 (`onKeyDown={(e) => e.key === "Enter" && send()}`). A `<form>` submit-on-Enter default would fire on every Enter press regardless of Shift, double-firing `send()` alongside the existing handler. Leave the input/button pair exactly as it is structurally (no `<form>` wrapper); only convert error/busy handling.

- [ ] **Step 1: Update imports (lines 1-6)**

Replace:

```tsx
"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button, PageHeader } from "@/components/ui";
import { useProject } from "@/lib/project-context";
```

with:

```tsx
"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button, Input, PageHeader, Select } from "@/components/ui";
import { useProject } from "@/lib/project-context";
import { humanError } from "@/lib/errors";
```

- [ ] **Step 2: `setError(String(e))` → `setError(humanError(e))` (lines 107, 135)**

Both the adapter-loading `.catch` and `send`'s `catch` block change `setError(String(e))` to `setError(humanError(e))`. `send` keeps its own `busy`/`error` state (not `useAction`) because it manages the streaming `turns` array alongside them — converting it to `useAction` would need the hook to know about `turns`, which is out of scope for the hook's single-result shape. This is a deliberate exception to "every mutating action uses `useAction`": `send` is a streaming action, not a single request/response.

- [ ] **Step 3: Replace the adapter `<select>` (lines 157-173) with `Select`**

Replace:

```tsx
            <select
              value={adapter ?? ""}
              disabled={busy || !ready}
              aria-label="Modèle du projet"
              onChange={(e) => {
                setAdapter(e.target.value || null);
                try { localStorage.setItem(`openagent:adapter:${projectId}`, e.target.value); } catch { /* optional */ }
              }}
              className="bg-surface border border-border rounded-md px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent transition-colors"
            >
              <option value="">base (sans LoRA)</option>
              {adapters.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
```

with:

```tsx
            <Select
              value={adapter ?? ""}
              disabled={busy || !ready}
              onChange={(v) => {
                setAdapter(v || null);
                try { localStorage.setItem(`openagent:adapter:${projectId}`, v); } catch { /* optional */ }
              }}
            >
              <option value="">base (sans LoRA)</option>
              {adapters.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </Select>
```

(`aria-label="Modèle du projet"` is dropped since `Select` doesn't expose an `aria-label` prop; the visible "RAG" checkbox label and page description already give this control enough context. Add an `aria-label` prop to `Select` in `ui.tsx` later if this needs revisiting.)

- [ ] **Step 4: Replace the message `<input>` (lines 212-221) with `Input`, keeping the exact `onKeyDown` logic**

Replace:

```tsx
        <input
          value={input}
          maxLength={8000}
          disabled={busy || !ready}
          aria-label="Message"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Écris un message…"
          className="flex-1 bg-surface border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors"
        />
```

with:

```tsx
        <Input
          value={input}
          onChange={setInput}
          disabled={busy || !ready}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Écris un message…"
          className="flex-1"
        />
```

`Input` doesn't expose `maxLength` or `aria-label` props today — `maxLength={8000}` is dropped (the backend still enforces its own limit; this was a UX nicety, not a correctness guard) and `aria-label="Message"` is dropped (the placeholder text already names the field). This is unchanged behavior for the one thing that matters here: `onKeyDown` is passed through verbatim, so Entrée still sends and the browser's native `Shift+Enter` behavior on a single-line `<input>` (which never inserted a newline in an `<input>` to begin with — only `<textarea>` does that) is unaffected either way.

- [ ] **Step 5: Verify Entrée still sends**

No code change here — this step is a manual check performed once in Task 8's full walkthrough (send with Entrée). Recorded here so the risk (now resolved as a non-issue — see the spec's revised risk note) isn't silently dropped from this task's scope.

### `rag/page.tsx`

- [ ] **Step 1: Update imports (lines 1-6)**

Replace:

```tsx
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api, JobStatus, RAG_CATEGORIES, RagCategory, RagDocument, RagSearchResult } from "@/lib/api";
import { Button, Card, EmptyState, Input, PageHeader, Pill, SectionTitle, StatusBadge } from "@/components/ui";
import { useProject } from "@/lib/project-context";
```

with:

```tsx
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api, JobStatus, RAG_CATEGORIES, RagCategory, RagDocument, RagSearchResult } from "@/lib/api";
import { Button, Card, ConfirmDialog, EmptyState, Input, PageHeader, Pill, SectionTitle, Skeleton, StatusBadge, Textarea } from "@/components/ui";
import { useProject } from "@/lib/project-context";
import { useAction } from "@/lib/use-action";
```

- [ ] **Step 2: `CategorySelect`'s raw `<select>` → `Select`**

Replace the whole `CategorySelect` function (lines 15-29):

```tsx
function CategorySelect({ value, onChange }: { value: RagCategory; onChange: (v: RagCategory) => void }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as RagCategory)}
      className="bg-bg border border-border rounded-md px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent transition-colors"
    >
      {RAG_CATEGORIES.map((c) => (
        <option key={c} value={c}>
          {CATEGORY_LABELS[c]}
        </option>
      ))}
    </select>
  );
}
```

with:

```tsx
function CategorySelect({ value, onChange }: { value: RagCategory; onChange: (v: RagCategory) => void }) {
  return (
    <Select value={value} onChange={(v) => onChange(v as RagCategory)}>
      {RAG_CATEGORIES.map((c) => (
        <option key={c} value={c}>
          {CATEGORY_LABELS[c]}
        </option>
      ))}
    </Select>
  );
}
```

Add `Select` to the `components/ui` import from Step 1.

- [ ] **Step 3: Convert `handlePaste`, `handleFileUpload`, `handleReindex`, `handleDelete` to `useAction`**

Replace `error`/handler code (lines 36, 83-131):

Remove `const [error, setError] = useState<string | null>(null);` and `const [uploading, setUploading] = useState(false);`.

```tsx
  const pasteAction = useAction(
    (filename: string, category: RagCategory, content: string) => api.rag.createDocument(projectId!, filename, category, content),
    { success: (doc) => `${doc.filename} ajouté.` },
  );
  const handlePaste = async () => {
    if (!newFilename.trim() || !newContent.trim() || !projectId) return;
    const filename = newFilename.trim().endsWith(".md") ? newFilename.trim() : `${newFilename.trim()}.md`;
    const doc = await pasteAction.run(filename, newCategory, newContent);
    if (doc) {
      setNewFilename("");
      setNewContent("");
      trackReindexJob(doc.reindex_job_id);
      refresh();
    }
  };

  const uploadAction = useAction((file: File, category: RagCategory) => api.rag.uploadDocument(projectId!, file, category), {
    success: (doc) => `${doc.filename} envoyé.`,
  });
  const handleFileUpload = async (file: File) => {
    if (!projectId) return;
    const doc = await uploadAction.run(file, uploadCategory);
    if (doc) {
      trackReindexJob(doc.reindex_job_id);
      refresh();
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const [pendingDelete, setPendingDelete] = useState<{ category: string; filename: string } | null>(null);
  const deleteAction = useAction((category: string, filename: string) => api.rag.deleteDocument(projectId!, category, filename));
  const handleDelete = (category: string, filename: string) => setPendingDelete({ category, filename });
  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const { category, filename } = pendingDelete;
    setPendingDelete(null);
    const res = await deleteAction.run(category, filename);
    if (res) {
      trackReindexJob(res.reindex_job_id);
      refresh();
    }
  };

  const reindexAction = useAction(() => api.rag.reindex(projectId!));
  const handleReindex = async () => {
    if (!projectId) return;
    const job = await reindexAction.run();
    if (job) setReindexJob(job);
  };
```

- [ ] **Step 4: Update JSX to use the new action objects**

Replace the top-level `{error && <Card ...>}` (line 153) — delete it; errors now surface as toasts plus each action's own `.error` where relevant. Since no single error field remains for this page, and the confirm-based delete already toasts on failure, this block is simply removed.

Replace `disabled={reindexJob?.status === "running"}` (line 146, the "Forcer une reconstruction" button) with `disabled={reindexJob?.status === "running" || reindexAction.busy}`.

Replace the file input's `disabled={uploading}` (line 222) with `disabled={uploadAction.busy}`, and `{uploading && ...}` (line 226) with `{uploadAction.busy && <p className="text-text-muted text-xs">Extraction du texte…</p>}`.

Replace the paste `<Button onClick={handlePaste}>Ajouter</Button>` (line 242) with `<Button onClick={handlePaste} disabled={pasteAction.busy}>{pasteAction.busy ? "Ajout…" : "Ajouter"}</Button>`.

Replace the `<textarea>` for pasted content (lines 235-241):

```tsx
          <textarea
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            placeholder="# Titre&#10;&#10;Contenu du document en markdown…"
            rows={6}
            className="w-full bg-bg border border-border rounded-md px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors font-mono"
          />
```

with:

```tsx
          <Textarea value={newContent} onChange={setNewContent} placeholder="# Titre&#10;&#10;Contenu du document en markdown…" rows={6} className="font-mono" />
```

Add the `ConfirmDialog` after `<PageHeader .../>`:

```tsx
      <ConfirmDialog
        open={!!pendingDelete}
        title="Supprimer ce document ?"
        description={pendingDelete ? pendingDelete.filename : undefined}
        confirmLabel="Supprimer"
        danger
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
```

- [ ] **Step 5: Loading skeleton for the documents list (before line 170, `{grouped.has("research") && (`)**

Add `const [documentsLoaded, setDocumentsLoaded] = useState(false);`, set it `true` in `refresh`'s `.then`. Wrap the whole `{RAG_CATEGORIES.map(...)}` block (lines 178-207) plus the `{documents.length === 0 && ...}` (line 208):

```tsx
      {!documentsLoaded ? (
        <Skeleton className="h-32" />
      ) : (
        <>
          {RAG_CATEGORIES.map((cat) => {
            /* unchanged body */
          })}
          {documents.length === 0 && <EmptyState>Aucun document. Ajoute-en un ci-dessous.</EmptyState>}
        </>
      )}
```

- [ ] **Step 6: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors.

### `providers/page.tsx`

- [ ] **Step 1: Update imports**

Replace:

```tsx
"use client";

import { api, Provider } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { Button, Card, EmptyState, Input, PageHeader, Pill, SectionTitle } from "@/components/ui";
```

with:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { api, Provider } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { Button, Card, ConfirmDialog, EmptyState, Input, PageHeader, Pill, Select, SectionTitle, Skeleton } from "@/components/ui";
import { useAction } from "@/lib/use-action";
```

(This page's original imports at line 1-3 were compressed in the earlier read; `useCallback`/`useEffect`/`useState` are already used — keep whichever of these three the file currently imports from `"react"`, adding only what's missing.)

- [ ] **Step 2: Replace the generic `act` helper and `message`/`busy` state with per-action `useAction`**

Replace:

```tsx
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.enterprise.providers(projectId).then(setItems), [projectId]);
  useEffect(() => { Promise.resolve().then(load).catch((e) => setMessage(String(e))); }, [load]);
  const act = async (work: () => Promise<unknown>) => { setBusy(true); setMessage(null); try { await work(); await load(); } catch (e) { setMessage(String(e)); } finally { setBusy(false); } };
```

with:

```tsx
  const [loaded, setLoaded] = useState(false);
  const load = useCallback(() => api.enterprise.providers(projectId).then((next) => { setItems(next); setLoaded(true); }), [projectId]);
  useEffect(() => { load().catch(() => setLoaded(true)); }, [load]);

  const saveAction = useAction(
    (params: Parameters<typeof api.enterprise.updateProvider>[1]) => api.enterprise.updateProvider(projectId, params),
    { success: "Fournisseur enregistré." },
  );
  const testAction = useAction((id: string) => api.enterprise.testProvider(projectId, id), {
    success: (result) => `Connexion réussie en ${result.latency_ms} ms`,
  });
  const [pendingRemove, setPendingRemove] = useState<Provider | null>(null);
  const removeAction = useAction((id: string) => api.enterprise.removeProvider(projectId, id), { success: "Fournisseur supprimé." });
  const confirmRemove = async () => {
    if (!pendingRemove) return;
    const item = pendingRemove;
    setPendingRemove(null);
    await removeAction.run(item.id);
    await load();
  };
  const busy = saveAction.busy || testAction.busy || removeAction.busy;
```

- [ ] **Step 3: Replace the JSX (lines 25-38)**

Replace the whole `return` block:

```tsx
  return <div className="space-y-8">
    <PageHeader title="Fournisseurs" description="Configure les moteurs utilisés par les agents. Les secrets restent dans les variables d’environnement du serveur." />
    {message ? <Card className="text-sm">{message}</Card> : null}
    <section><SectionTitle>Ajouter ou mettre à jour</SectionTitle><Card className="grid gap-3 md:grid-cols-2">
      <label className="text-xs text-text-muted">Nom<Input value={name} onChange={setName} className="w-full mt-1" /></label>
      <label className="text-xs text-text-muted">Type<select value={type} onChange={(e) => { const next=e.target.value as Provider["type"]; setType(next); if(next === "ollama") setUrl("http://localhost:11434"); }} className="w-full mt-1 bg-bg border border-border rounded-md px-3 py-1.5 text-sm"><option value="ollama">Ollama</option><option value="openai-compatible">API compatible OpenAI</option><option value="anthropic-compatible">API compatible Anthropic</option></select></label>
      <label className="text-xs text-text-muted">URL de base<Input value={url} onChange={setUrl} className="w-full mt-1 font-mono" /></label>
      <label className="text-xs text-text-muted">Modèle<Input value={model} onChange={setModel} placeholder="llama3.2:3b" className="w-full mt-1 font-mono" /></label>
      <label className="text-xs text-text-muted md:col-span-2">Variable contenant la clé API<Input value={secretEnv} onChange={setSecretEnv} placeholder="PROVIDER_API_KEY — vide pour Ollama" className="w-full mt-1 font-mono" /></label>
      <div className="md:col-span-2"><Button variant="accent" disabled={busy || !name.trim() || !url.trim() || !model.trim()} onClick={() => act(() => api.enterprise.updateProvider(projectId, { name: name.trim(), type, base_url: url.trim(), model: model.trim(), api_key_env: secretEnv.trim() || null, enabled: true }))}>Enregistrer</Button></div>
    </Card></section>
    <section><SectionTitle>Fournisseurs configurés ({items.length})</SectionTitle>{items.length === 0 ? <EmptyState>Aucun fournisseur.</EmptyState> : <div className="space-y-3">{items.map((item) => <Card key={item.id} className="flex items-center justify-between gap-4 flex-wrap"><div><div className="flex gap-2"><span className="font-medium text-sm">{item.name}</span><Pill>{item.type}</Pill></div><p className="text-xs text-text-muted mt-2 font-mono">{item.base_url} · {item.model}</p><p className="text-xs text-text-muted mt-1">Secret : {item.api_key_env || "aucun"}</p></div><div className="flex gap-2"><Button disabled={busy} onClick={() => act(async () => { const result=await api.enterprise.testProvider(projectId,item.id); setMessage(`Connexion réussie en ${result.latency_ms} ms`); })}>Tester</Button><Button variant="danger" disabled={busy} onClick={() => confirm(`Supprimer ${item.name} ?`) && act(() => api.enterprise.removeProvider(projectId,item.id))}>Supprimer</Button></div></Card>)}</div>}</section>
  </div>;
```

with:

```tsx
  return <div className="space-y-8">
    <PageHeader title="Fournisseurs" description="Configure les moteurs utilisés par les agents. Les secrets restent dans les variables d’environnement du serveur." />
    <ConfirmDialog
      open={!!pendingRemove}
      title="Supprimer ce fournisseur ?"
      description={pendingRemove?.name}
      confirmLabel="Supprimer"
      danger
      onConfirm={confirmRemove}
      onCancel={() => setPendingRemove(null)}
    />
    <section><SectionTitle>Ajouter ou mettre à jour</SectionTitle><Card className="grid gap-3 md:grid-cols-2">
      <label className="text-xs text-text-muted">Nom<Input value={name} onChange={setName} className="w-full mt-1" /></label>
      <label className="text-xs text-text-muted">Type<Select value={type} onChange={(v) => { const next = v as Provider["type"]; setType(next); if (next === "ollama") setUrl("http://localhost:11434"); }} className="w-full mt-1"><option value="ollama">Ollama</option><option value="openai-compatible">API compatible OpenAI</option><option value="anthropic-compatible">API compatible Anthropic</option></Select></label>
      <label className="text-xs text-text-muted">URL de base<Input value={url} onChange={setUrl} className="w-full mt-1 font-mono" /></label>
      <label className="text-xs text-text-muted">Modèle<Input value={model} onChange={setModel} placeholder="llama3.2:3b" className="w-full mt-1 font-mono" /></label>
      <label className="text-xs text-text-muted md:col-span-2">Variable contenant la clé API<Input value={secretEnv} onChange={setSecretEnv} placeholder="PROVIDER_API_KEY — vide pour Ollama" className="w-full mt-1 font-mono" /></label>
      <div className="md:col-span-2"><Button variant="accent" disabled={busy || !name.trim() || !url.trim() || !model.trim()} onClick={() => saveAction.run({ name: name.trim(), type, base_url: url.trim(), model: model.trim(), api_key_env: secretEnv.trim() || null, enabled: true }).then((r) => r && load())}>Enregistrer</Button></div>
    </Card></section>
    <section><SectionTitle>Fournisseurs configurés ({items.length})</SectionTitle>
      {!loaded ? <Skeleton className="h-20" /> : items.length === 0 ? <EmptyState>Aucun fournisseur.</EmptyState> : <div className="space-y-3">{items.map((item) => <Card key={item.id} className="flex items-center justify-between gap-4 flex-wrap"><div><div className="flex gap-2"><span className="font-medium text-sm">{item.name}</span><Pill>{item.type}</Pill></div><p className="text-xs text-text-muted mt-2 font-mono">{item.base_url} · {item.model}</p><p className="text-xs text-text-muted mt-1">Secret : {item.api_key_env || "aucun"}</p></div><div className="flex gap-2"><Button disabled={busy} onClick={() => testAction.run(item.id)}>Tester</Button><Button variant="danger" disabled={busy} onClick={() => setPendingRemove(item)}>Supprimer</Button></div></Card>)}</div>}
    </section>
  </div>;
```

- [ ] **Step 4: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors.

### `tools/page.tsx`

- [ ] **Step 1: Update imports**

Replace the `components/ui` import line with one that adds `ConfirmDialog`, `Select`, `Skeleton`:

```tsx
import { Button, Card, ConfirmDialog, EmptyState, Input, PageHeader, Pill, Select, SectionTitle, Skeleton, StatusBadge } from "@/components/ui";
```

Remove the module-level `const selectClass = "bg-bg border border-border rounded-md px-3 py-1.5 text-sm";` (line 8) — no longer needed once every raw `<select>` becomes `<Select>`.

- [ ] **Step 2: Keep the generic `act`/`message`/`busy` pattern for reads with inline JSON feedback, but route deletions through `ConfirmDialog`**

This page's `act` helper (lines 50-62) already centralizes busy/error handling and shows the raw result via `setMessage(JSON.stringify(result))` — a deliberate raw-JSON debug affordance for "Tester sans arguments" and "Synchroniser", not a user-facing error path. Leave `act`, `message`, `busy` as they are (no `useAction` conversion here — the page's own `act` already does the same busy/try/catch/finally shape, and replacing "show raw JSON of the read result" with a French toast would lose the debug value). Only add a `ConfirmDialog` for the one destructive action introduced in Task 6's scope: none of the current five buttons in `tools/page.tsx` calls `confirm()` today (`tools/page.tsx` has zero `confirm(` occurrences per the grep in the design phase) — so **no `ConfirmDialog` wiring is needed on this page**; skip straight to Step 3.

- [ ] **Step 3: Replace the three raw `<select>` elements with `Select`**

Replace (line 87, method picker):

```tsx
        <select value={method} onChange={(event) => setMethod(event.target.value as "GET" | "POST")} className={selectClass}>
          <option>GET</option><option>POST</option>
        </select>
```

with:

```tsx
        <Select value={method} onChange={(v) => setMethod(v as "GET" | "POST")}>
          <option>GET</option><option>POST</option>
        </Select>
```

Replace (line 99, policy effect picker):

```tsx
        <select value={effect} onChange={(event) => setEffect(event.target.value as ToolPolicy["effect"])} className={selectClass}>
          <option value="allow">Autoriser</option><option value="require_approval">Exiger une approbation</option><option value="deny">Refuser</option>
        </select>
```

with:

```tsx
        <Select value={effect} onChange={(v) => setEffect(v as ToolPolicy["effect"])}>
          <option value="allow">Autoriser</option><option value="require_approval">Exiger une approbation</option><option value="deny">Refuser</option>
        </Select>
```

Replace (line 102, target-tool picker):

```tsx
        <select value={targetTool} onChange={(event) => setTargetTool(event.target.value)} className={selectClass}>
          <option value="">Tous les outils</option>{tools.map((tool) => <option key={tool.id} value={tool.id}>{tool.name}</option>)}
        </select>
```

with:

```tsx
        <Select value={targetTool} onChange={setTargetTool}>
          <option value="">Tous les outils</option>{tools.map((tool) => <option key={tool.id} value={tool.id}>{tool.name}</option>)}
        </Select>
```

- [ ] **Step 4: Loading skeletons for the four lists (MCP servers, tools catalog, policies, approvals)**

Add `const [loaded, setLoaded] = useState(false);`, set it `true` at the end of `load`'s `.then` callback (after `setMcpServers(serverItems)`). For each of the four `{X.length === 0 ? <EmptyState>...</EmptyState> : <div ...>}` blocks (MCP servers ~line 76, tools catalog ~line 116, policies ~line 108, approvals ~line 124), prepend a `!loaded ? <Skeleton className="h-16" /> :` branch, e.g.:

```tsx
      {!loaded ? <Skeleton className="h-16" /> : mcpServers.length === 0 ? <EmptyState>Aucun serveur MCP.</EmptyState> : <div className="space-y-2">{mcpServers.map(...
```

Apply the same `!loaded ? <Skeleton className="h-16" /> :` prefix to the other three ternaries.

- [ ] **Step 5: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add web/src/app/chat/page.tsx web/src/app/rag/page.tsx web/src/app/providers/page.tsx web/src/app/tools/page.tsx
git commit -m "feat(web): apply useAction/ConfirmDialog/Skeleton to chat, rag, providers, tools"
```

---

## Task 7: Pages `opportunities` (liste, fiche, dashboard), `enterprise`, `project-switcher`

**Files:**
- Modify: `web/src/app/opportunities/page.tsx`
- Modify: `web/src/app/opportunities/[id]/page.tsx`
- Modify: `web/src/app/opportunities/dashboard/page.tsx`
- Modify: `web/src/app/enterprise/page.tsx`
- Modify: `web/src/components/project-switcher.tsx`

### `opportunities/page.tsx`

- [ ] **Step 1: Update imports**

Replace:

```tsx
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, Opportunity, SCORE_LABELS } from "@/lib/api";
import { Button, Card, EmptyState, Input, PageHeader, StatusBadge } from "@/components/ui";
```

with:

```tsx
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, Opportunity, SCORE_LABELS } from "@/lib/api";
import { Button, Card, EmptyState, Input, PageHeader, Skeleton, StatusBadge } from "@/components/ui";
import { useAction } from "@/lib/use-action";
```

- [ ] **Step 2: Replace `error`/`busy`/`create` (lines 12-13, 25-32) with `useAction` and a `loaded` flag for the skeleton**

Replace:

```tsx
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setOpportunities(await api.opportunities.list());
  }, []);

  useEffect(() => {
    let active = true;
    refresh().catch((e) => { if (active) setError(String(e)); });
    return () => { active = false; };
  }, [refresh]);

  const create = async () => {
    setBusy(true); setError(null);
    try {
      await api.opportunities.create({ name: name.trim() });
      setName("");
      await refresh();
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  };
```

with:

```tsx
  const [name, setName] = useState("");
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    const next = await api.opportunities.list();
    setOpportunities(next);
    setLoaded(true);
  }, []);

  useEffect(() => {
    refresh().catch(() => setLoaded(true));
  }, [refresh]);

  const createAction = useAction((name: string) => api.opportunities.create({ name }), {
    success: (item) => `${item.name} créée.`,
  });
  const create = async () => {
    const created = await createAction.run(name.trim());
    if (created) {
      setName("");
      await refresh();
    }
  };
```

- [ ] **Step 3: Update JSX (lines 37-42)**

Replace:

```tsx
    {error ? <Card className="border-error/30 bg-error-soft text-error text-sm">{error}</Card> : null}
    <Card className="flex flex-wrap gap-2">
      <Input value={name} onChange={setName} placeholder="Nom de la nouvelle opportunité" className="flex-1 min-w-56" />
      <Button variant="accent" disabled={busy || !name.trim()} onClick={create}>Créer</Button>
    </Card>
    {opportunities.length === 0 ? <EmptyState>Aucune opportunité pour l'instant.</EmptyState> : <div className="grid gap-3 md:grid-cols-2">
```

with:

```tsx
    {createAction.error ? <Card className="border-error/30 bg-error-soft text-error text-sm">{createAction.error}</Card> : null}
    <Card className="flex flex-wrap gap-2">
      <Input value={name} onChange={setName} placeholder="Nom de la nouvelle opportunité" className="flex-1 min-w-56" />
      <Button variant="accent" disabled={createAction.busy || !name.trim()} onClick={create}>Créer</Button>
    </Card>
    {!loaded ? <div className="grid gap-3 md:grid-cols-2"><Skeleton className="h-28" /><Skeleton className="h-28" /></div> : opportunities.length === 0 ? <EmptyState>Aucune opportunité pour l'instant.</EmptyState> : <div className="grid gap-3 md:grid-cols-2">
```

- [ ] **Step 4: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors.

### `opportunities/[id]/page.tsx`

- [ ] **Step 1: Update imports**

Replace:

```tsx
import { api, Opportunity, OpportunityAnalysis, OpportunityFields, OpportunityKpi, OpportunityScores, Project, Provider, SCORE_LABELS } from "@/lib/api";
import { simulate, SimulatorInput } from "@/lib/simulator";
import { Button, Card, EmptyState, PageHeader, Pill, SectionTitle } from "@/components/ui";
```

with:

```tsx
import { api, Opportunity, OpportunityAnalysis, OpportunityFields, OpportunityKpi, OpportunityScores, Project, Provider, SCORE_LABELS } from "@/lib/api";
import { simulate, SimulatorInput } from "@/lib/simulator";
import { Button, Card, EmptyState, PageHeader, Pill, SectionTitle, Select, Skeleton } from "@/components/ui";
import { useAction } from "@/lib/use-action";
```

- [ ] **Step 2: Convert `act`/`busy`/`error` to `useAction`-backed named actions**

This page's generic `act` helper wraps five distinct mutations (status change, save fields, save scores, upsert KPI, run analysis). Replace the generic `act`/`busy`/`error` trio with one `useAction` per mutation, each with its own success message:

```tsx
  const updateStatusAction = useAction((next: Opportunity["status"]) => api.opportunities.updateStatus(id, next), { success: "Statut mis à jour." });
  const saveFieldsAction = useAction((value: OpportunityFields) => api.opportunities.update(id, value), { success: "Fiche enregistrée." });
  const saveScoresAction = useAction((value: OpportunityScores) => api.opportunities.updateScores(id, value), { success: "Score enregistré." });
  const upsertKpiAction = useAction(
    (kpi: Parameters<typeof api.opportunities.upsertKpi>[1]) => api.opportunities.upsertKpi(id, kpi),
    { success: "KPI mesuré." },
  );
  const analyzeAction = useAction(
    (projectId: string, providerId: string) => api.opportunities.analyze(id, projectId, providerId),
    { success: "Analyse IA générée." },
  );
  const busy = updateStatusAction.busy || saveFieldsAction.busy || saveScoresAction.busy || upsertKpiAction.busy || analyzeAction.busy;
```

Keep the top-level `error`/`refresh` pattern (`useState`/`useCallback` at the top, lines ~46-65) as-is except `setError(String(e))` → `setError(humanError(e))` (add `import { humanError } from "@/lib/errors";`) — this one stays manual because it covers the page's *initial load* (four parallel `Promise.all` calls), not a single user-triggered mutation, and its failure already renders as the page's only content (`if (error && (!fields || !scores)) return <Card>...`), so `useAction` would add no capability here.

- [ ] **Step 3: Replace the five call sites**

Replace the status `<select>` in `PageHeader`'s `action` (lines 88-92):

```tsx
      action={<select value={status} disabled={busy}
        onChange={(e) => act(() => api.opportunities.updateStatus(id, e.target.value as Opportunity["status"]))}
        className="bg-bg border border-border rounded-md px-2 py-1 text-xs">
        {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>} />
```

with:

```tsx
      action={<Select value={status} disabled={busy} className="text-xs"
        onChange={(v) => updateStatusAction.run(v as Opportunity["status"]).then((r) => r && setStatus(v as Opportunity["status"]))}>
        {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
      </Select>} />
```

Replace the "Enregistrer la fiche" button (line 110):

```tsx
        <div className="md:col-span-2"><Button variant="accent" disabled={busy} onClick={() => act(() => api.opportunities.update(id, fields))}>Enregistrer la fiche</Button></div>
```

with:

```tsx
        <div className="md:col-span-2"><Button variant="accent" disabled={busy} onClick={() => saveFieldsAction.run(fields)}>Enregistrer la fiche</Button></div>
```

Replace the "Enregistrer le score" button (line 123):

```tsx
        <div className="lg:col-span-4"><Button variant="accent" disabled={busy} onClick={() => act(() => api.opportunities.updateScores(id, scores))}>Enregistrer le score</Button></div>
```

with:

```tsx
        <div className="lg:col-span-4"><Button variant="accent" disabled={busy} onClick={() => saveScoresAction.run(scores)}>Enregistrer le score</Button></div>
```

Replace the `KpiRow` `onSave` wiring (lines 130-134):

```tsx
        {kpis.map((kpi) => <KpiRow key={kpi.id} kpi={kpi} busy={busy}
          onSave={(current, target) => act(() => api.opportunities.upsertKpi(id, {
            name: kpi.name, category: kpi.category, unit: kpi.unit,
            current_value: current, target_value: target, higher_is_better: !!kpi.higher_is_better,
          }))} />)}
```

with:

```tsx
        {kpis.map((kpi) => <KpiRow key={kpi.id} kpi={kpi} busy={busy}
          onSave={(current, target) => upsertKpiAction.run({
            name: kpi.name, category: kpi.category, unit: kpi.unit,
            current_value: current, target_value: target, higher_is_better: !!kpi.higher_is_better,
          })} />)}
```

Replace the "Analyser avec l'IA" button (lines 160-163):

```tsx
        <Button variant="accent" disabled={busy || !analysisProjectId || !analysisProviderId}
          onClick={() => act(() => api.opportunities.analyze(id, analysisProjectId, analysisProviderId))}>
          Analyser avec l’IA
        </Button>
```

with:

```tsx
        <Button variant="accent" disabled={busy || !analysisProjectId || !analysisProviderId}
          onClick={() => analyzeAction.run(analysisProjectId, analysisProviderId).then((a) => a && refresh())}>
          Analyser avec l’IA
        </Button>
```

(The original `act` always called `refresh()` after every mutation. `updateStatus`, `saveFields`, `saveScores`, `upsertKpi` mutate local state that's already reflected on screen via the controlled inputs, so skipping `refresh()` after them avoids an unnecessary round-trip; `analyze` is the one action whose result — a new `OpportunityAnalysis` — isn't otherwise in local state, so it keeps the `refresh()` call.)

- [ ] **Step 4: Replace the two remaining raw `<select>` elements (lines 88-92 done above; also lines 147-151 and 154-158)**

Replace:

```tsx
        <label className="text-xs text-text-muted">Projet
          <select value={analysisProjectId} onChange={(e) => setAnalysisProjectId(e.target.value)}
            className="mt-1 block bg-bg border border-border rounded-md px-2 py-1.5 text-sm">
            <option value="">—</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
        </label>
        <label className="text-xs text-text-muted">Fournisseur
          <select value={analysisProviderId} onChange={(e) => setAnalysisProviderId(e.target.value)}
            className="mt-1 block bg-bg border border-border rounded-md px-2 py-1.5 text-sm">
            <option value="">—</option>
            {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
```

with:

```tsx
        <label className="text-xs text-text-muted">Projet
          <Select value={analysisProjectId} onChange={setAnalysisProjectId} className="mt-1 block">
            <option value="">—</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </Select>
        </label>
        <label className="text-xs text-text-muted">Fournisseur
          <Select value={analysisProviderId} onChange={setAnalysisProviderId} className="mt-1 block">
            <option value="">—</option>
            {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
        </label>
```

- [ ] **Step 5: Loading skeleton (line 81, `if (!fields || !scores) return <p>Chargement…</p>;`)**

Replace:

```tsx
  if (!fields || !scores) return <p>Chargement…</p>;
```

with:

```tsx
  if (!fields || !scores) return <div className="space-y-4"><Skeleton className="h-8 w-1/3" /><Skeleton className="h-48" /><Skeleton className="h-32" /></div>;
```

- [ ] **Step 6: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors.

### `opportunities/dashboard/page.tsx`

Per the spec's table, this page's `useAction`/`Skeleton` needs are minimal: it has no mutation (read-only comparison table), so no `useAction` applies; it already replaces its own "Chargement…" text at line 21 — no change needed there either. Its only gap is the raw `setError(String(e))` at line 17.

- [ ] **Step 1: `setError(String(e))` → `setError(humanError(e))`**

Add `import { humanError } from "@/lib/errors";` to the imports.

Replace line 17:

```tsx
    api.opportunities.dashboard().then(setOpportunities).catch((e) => setError(String(e)));
```

with:

```tsx
    api.opportunities.dashboard().then(setOpportunities).catch((e) => setError(humanError(e)));
```

- [ ] **Step 2: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors.

### `enterprise/page.tsx`

- [ ] **Step 1: Update imports**

Replace:

```tsx
import { api, AuditEvent, EnterpriseContext, EnterpriseMetrics, ModelVersion, ProjectMember, ProjectQuota } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { Button, Card, EmptyState, Input, PageHeader, Pill, SectionTitle, StatusBadge } from "@/components/ui";
```

with:

```tsx
import { api, AuditEvent, EnterpriseContext, EnterpriseMetrics, ModelVersion, ProjectMember, ProjectQuota } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { Button, Card, EmptyState, Input, PageHeader, Pill, Select, SectionTitle, Skeleton, StatusBadge } from "@/components/ui";
import { humanError } from "@/lib/errors";
```

- [ ] **Step 2: `setError(String(e))` → `setError(humanError(e))` (lines 41, 47)**

Keep this page's own `act`/`busy`/`error` helper — like `tools/page.tsx`, it already centralizes busy/try/catch/finally across six different mutations (add member, create version, transition, update quota, and the role-change `<select>`), and each call site already re-runs `refresh()` (equivalent to `useAction` without a `success` message, since every mutation here immediately reflects in the re-fetched lists below). Converting it to six separate `useAction` hooks would add six success toasts for actions whose result is already visible in the re-rendered list one line below — skipped per this task's stated convention. Only the two raw `String(e)` sites become `humanError(e)`.

- [ ] **Step 3: Loading skeleton for the four metric cards (lines 54-59)**

Add `const [loaded, setLoaded] = useState(false);`, set `true` at the end of `refresh` (after `setError(null)`). Replace the `<div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">...</div>` block:

```tsx
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {!loaded ? <><Skeleton className="h-20" /><Skeleton className="h-20" /><Skeleton className="h-20" /><Skeleton className="h-20" /></> : <>
        <Metric label="Identité" value={context ? `${context.actor.name} · ${context.actor.role}` : "…"} />
        <Metric label="Authentification" value={context?.auth_mode === "proxy" ? "SSO via proxy" : "Mode local"} />
        <Metric label="Requêtes · p95" value={metrics ? `${metrics.requests_total ?? 0} · ${metrics.latency_p95_ms} ms` : "…"} />
        <Metric label="Jobs" value={metrics ? `${metrics.jobs_running} actif · ${metrics.jobs_failed} échoué` : "…"} />
      </>}
    </div>
```

- [ ] **Step 4: Replace the role `<select>` (line 75) with `Select`**

Replace:

```tsx
        <select value={member.role} disabled={busy} onChange={(e) => act(() => api.enterprise.updateMember(projectId, { actor_id: member.actor_id, email: member.email, name: member.name, role: e.target.value as ProjectMember["role"] }))} className="bg-bg border border-border rounded-md px-2 py-1 text-xs">
          {(["viewer", "operator", "reviewer", "admin"] as const).map((role) => <option key={role}>{role}</option>)}
        </select>
```

with:

```tsx
        <Select value={member.role} disabled={busy} className="text-xs" onChange={(v) => act(() => api.enterprise.updateMember(projectId, { actor_id: member.actor_id, email: member.email, name: member.name, role: v as ProjectMember["role"] }))}>
          {(["viewer", "operator", "reviewer", "admin"] as const).map((role) => <option key={role}>{role}</option>)}
        </Select>
```

- [ ] **Step 5: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors.

### `project-switcher.tsx`

- [ ] **Step 1: Update imports**

Replace:

```tsx
"use client";

import { useState } from "react";
import { useProject } from "@/lib/project-context";
import { api, Project } from "@/lib/api";
```

with:

```tsx
"use client";

import { useState } from "react";
import { useProject } from "@/lib/project-context";
import { api, Project } from "@/lib/api";
import { Input, Select, Textarea } from "@/components/ui";
import { useAction } from "@/lib/use-action";
```

- [ ] **Step 2: Replace `error`/`create` (lines 24-49) with `useAction`**

Replace:

```tsx
  const [error, setError] = useState<string | null>(null);
  const create = async () => {
    setError(null);
    if (!newId.trim() || !newBaseModel.trim() || !purpose.trim()) return;
    try {
      const created = await api.projects.create({
        id: newId.trim(),
        label: newLabel.trim() || undefined,
        base_model: newBaseModel.trim(),
        project_type: projectType,
        purpose: purpose.trim(),
        output_mode: outputMode,
        system_prompt: systemPrompt.trim() || undefined,
      });
      setNewId("");
      setNewLabel("");
      setNewBaseModel("");
      setPurpose("");
      setSystemPrompt("");
      setOpen(false);
      refresh();
      setProjectId(created.id);
    } catch (e) {
      setError(String(e));
    }
  };
```

with:

```tsx
  const createAction = useAction((params: Parameters<typeof api.projects.create>[0]) => api.projects.create(params), {
    success: (created) => `Projet « ${created.label} » créé.`,
  });
  const create = async () => {
    if (!newId.trim() || !newBaseModel.trim() || !purpose.trim()) return;
    const created = await createAction.run({
      id: newId.trim(),
      label: newLabel.trim() || undefined,
      base_model: newBaseModel.trim(),
      project_type: projectType,
      purpose: purpose.trim(),
      output_mode: outputMode,
      system_prompt: systemPrompt.trim() || undefined,
    });
    if (created) {
      setNewId("");
      setNewLabel("");
      setNewBaseModel("");
      setPurpose("");
      setSystemPrompt("");
      setOpen(false);
      refresh();
      setProjectId(created.id);
    }
  };
```

- [ ] **Step 3: Replace the project `<select>` (lines 53-66)**

Replace:

```tsx
      <select
        value={projectId ?? ""}
        onChange={(e) => setProjectId(e.target.value)}
        className="bg-surface border border-border rounded-md px-2.5 py-1 text-sm text-text-primary focus:outline-none focus:border-accent transition-colors max-w-[220px]"
        disabled={loading}
        title={projectError ? `API indisponible : ${projectError}` : "Projet actif — dataset, RAG, configs et expériences isolés par projet"}
      >
        {projects.length === 0 && <option value="">aucun projet</option>}
        {projects.map((proj) => (
          <option key={proj.id} value={proj.id}>
            {proj.label}
          </option>
        ))}
      </select>
```

with:

```tsx
      <Select
        value={projectId ?? ""}
        onChange={setProjectId}
        className="max-w-[220px]"
        disabled={loading}
      >
        {projects.length === 0 && <option value="">aucun projet</option>}
        {projects.map((proj) => (
          <option key={proj.id} value={proj.id}>
            {proj.label}
          </option>
        ))}
      </Select>
```

(The `title` attribute — a tooltip on API failure — is dropped because `Select`'s props don't expose `title`; the same information is already surfaced by the adjacent "API indisponible — réessayer" button, lines 67-71, unchanged.)

- [ ] **Step 4: Replace the "Type de modèle" `<select>` (lines 85-94)**

Replace:

```tsx
          <label className="block text-xs text-text-muted space-y-1">
            Type de modèle
            <select
              value={projectType}
              onChange={(e) => setProjectType(e.target.value as Project["project_type"])}
              className="w-full bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent"
            >
              {PROJECT_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
            </select>
          </label>
```

with:

```tsx
          <label className="block text-xs text-text-muted space-y-1">
            Type de modèle
            <Select value={projectType} onChange={(v) => setProjectType(v as Project["project_type"])} className="w-full">
              {PROJECT_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
            </Select>
          </label>
```

- [ ] **Step 5: Replace the "Format de réponse" `<select>` (lines 122-133)**

Replace:

```tsx
          <label className="block text-xs text-text-muted space-y-1">
            Format de réponse
            <select
              value={outputMode}
              onChange={(e) => setOutputMode(e.target.value as Project["output_mode"])}
              className="w-full bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent"
            >
              <option value="natural">Texte naturel</option>
              <option value="json">JSON pour une application ou un agent</option>
              <option value="flexible">Flexible selon la demande</option>
            </select>
          </label>
```

with:

```tsx
          <label className="block text-xs text-text-muted space-y-1">
            Format de réponse
            <Select value={outputMode} onChange={(v) => setOutputMode(v as Project["output_mode"])} className="w-full">
              <option value="natural">Texte naturel</option>
              <option value="json">JSON pour une application ou un agent</option>
              <option value="flexible">Flexible selon la demande</option>
            </Select>
          </label>
```

- [ ] **Step 6: Replace the three raw `<input>` elements (newLabel line 104-109, newId line 110-115, newBaseModel line 116-121) with `Input`**

Replace:

```tsx
          <input
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            placeholder="Nom affiché (ex. Assistant support)"
            className="w-full bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors"
          />
```

with:

```tsx
          <Input value={newLabel} onChange={setNewLabel} placeholder="Nom affiché (ex. Assistant support)" className="w-full" />
```

Replace:

```tsx
          <input
            value={newId}
            onChange={(e) => setNewId(e.target.value)}
            placeholder="id-du-projet (minuscules, tirets)"
            className="w-full bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors"
          />
```

with:

```tsx
          <Input value={newId} onChange={setNewId} placeholder="id-du-projet (minuscules, tirets)" className="w-full" />
```

Replace:

```tsx
          <input
            value={newBaseModel}
            onChange={(e) => setNewBaseModel(e.target.value)}
            placeholder="org/nom-du-modele (HF)"
            className="w-full bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors"
          />
```

with:

```tsx
          <Input value={newBaseModel} onChange={setNewBaseModel} placeholder="org/nom-du-modele (HF)" className="w-full" />
```

- [ ] **Step 7: Replace the two `<textarea>` elements (purpose, lines 95-103; system prompt, lines 136-143)**

Replace:

```tsx
          <textarea
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            rows={3}
            maxLength={2000}
            placeholder={PROJECT_TYPES.find((type) => type.value === projectType)?.example}
            aria-label="Mission du modèle"
            className="w-full bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors resize-y"
          />
```

with:

```tsx
          <Textarea
            value={purpose}
            onChange={setPurpose}
            rows={3}
            maxLength={2000}
            placeholder={PROJECT_TYPES.find((type) => type.value === projectType)?.example}
          />
```

Replace:

```tsx
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={5}
              maxLength={12000}
              placeholder="Laisse vide pour générer les instructions depuis la mission."
              className="w-full mt-2 bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors resize-y"
            />
```

with:

```tsx
            <Textarea
              value={systemPrompt}
              onChange={setSystemPrompt}
              rows={5}
              maxLength={12000}
              placeholder="Laisse vide pour générer les instructions depuis la mission."
              className="mt-2"
            />
```

(`aria-label="Mission du modèle"` on the purpose textarea is dropped: `Textarea` doesn't expose an `aria-label` prop, and the field's own `<p>` above it already announces "Crée un modèle pour n'importe quel usage…" — this is a minor accessibility regression accepted for this task; if it matters later, add an `aria-label` prop to `Textarea` in `ui.tsx`.)

- [ ] **Step 8: Update the error display and submit button**

Replace:

```tsx
          {error && <p className="text-error text-xs">{error}</p>}
```

with:

```tsx
          {createAction.error && <p className="text-error text-xs">{createAction.error}</p>}
```

Replace:

```tsx
            <button
              onClick={create}
              disabled={!newId.trim() || !newBaseModel.trim() || !purpose.trim()}
              className="flex-1 bg-accent text-white hover:bg-accent-strong disabled:opacity-40 px-3 py-1.5 text-sm rounded-md font-medium transition-colors"
            >
              Créer
            </button>
```

with:

```tsx
            <button
              onClick={create}
              disabled={createAction.busy || !newId.trim() || !newBaseModel.trim() || !purpose.trim()}
              className="flex-1 bg-accent text-white hover:bg-accent-strong disabled:opacity-40 px-3 py-1.5 text-sm rounded-md font-medium transition-colors"
            >
              {createAction.busy ? "Création…" : "Créer"}
            </button>
```

- [ ] **Step 9: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors.

- [ ] **Step 10: Commit**

```bash
git add web/src/app/opportunities/page.tsx web/src/app/opportunities/\[id\]/page.tsx web/src/app/opportunities/dashboard/page.tsx web/src/app/enterprise/page.tsx web/src/components/project-switcher.tsx
git commit -m "feat(web): apply useAction/Select/Textarea/Skeleton to opportunities, enterprise, project-switcher"
```

---

## Task 8: Pages `/`, `executions`, `system`, `settings` + full browser walkthrough

**Files:**
- Modify: `web/src/app/page.tsx`
- Modify: `web/src/app/executions/page.tsx`
- Modify: `web/src/app/system/page.tsx`
- Modify: `web/src/app/settings/page.tsx`

### `page.tsx` (dashboard `/`)

- [ ] **Step 1: Update imports**

Replace:

```tsx
import { Button, Card, EmptyState, PageHeader, Pill, SectionTitle, StatusBadge } from "@/components/ui";
```

with:

```tsx
import { Button, Card, EmptyState, PageHeader, Pill, SectionTitle, Skeleton, StatusBadge } from "@/components/ui";
import { useAction } from "@/lib/use-action";
import { humanError } from "@/lib/errors";
```

- [ ] **Step 2: `setError(String(e))` → `humanError` (line 39), `trainCurrentVersion` → `useAction` (lines 30-31, 71-83)**

Replace line 39:

```tsx
      .catch((e) => setError(String(e)));
```

with:

```tsx
      .catch((e) => setError(humanError(e)));
```

Remove `const [trainingBusy, setTrainingBusy] = useState(false);` and `const [trainingError, setTrainingError] = useState<string | null>(null);` (lines 30-31).

Replace `trainCurrentVersion` (lines 71-83):

```tsx
  const trainCurrentVersion = async () => {
    if (!currentVersion?.version || !projectId) return;
    setTrainingBusy(true);
    setTrainingError(null);
    try {
      await api.training.sweep(projectId, currentVersion.version, true);
      refreshAll();
    } catch (e) {
      setTrainingError(String(e));
    } finally {
      setTrainingBusy(false);
    }
  };
```

with:

```tsx
  const trainAction = useAction((version: string) => api.training.sweep(projectId, version, true), {
    success: "Sweep lancé — suis-le dans Training.",
  });
  const trainCurrentVersion = async () => {
    if (!currentVersion?.version) return;
    const result = await trainAction.run(currentVersion.version);
    if (result) refreshAll();
  };
```

- [ ] **Step 3: Update the two JSX sites using `trainingBusy`/`trainingError` (lines 314-327)**

Replace:

```tsx
            {currentVersion?.version && (
              <Button variant="accent" onClick={trainCurrentVersion} disabled={trainingBusy}>
                Entraîner {currentVersion.version} (sweep r=8/16/32)
              </Button>
            )}
          </div>
```

with:

```tsx
            {currentVersion?.version && (
              <Button variant="accent" onClick={trainCurrentVersion} disabled={trainAction.busy}>
                {trainAction.busy ? "Lancement…" : `Entraîner ${currentVersion.version} (sweep r=8/16/32)`}
              </Button>
            )}
          </div>
```

Replace:

```tsx
          {trainingError && <Card className="border-error/30 bg-error-soft text-error text-sm mb-3">{trainingError}</Card>}
```

with:

```tsx
          {trainAction.error && <Card className="border-error/30 bg-error-soft text-error text-sm mb-3">{trainAction.error}</Card>}
```

- [ ] **Step 4: Replace the three "Chargement…" text spots with `Skeleton` (lines 136-137, 157-158, 225-226)**

Replace:

```tsx
            {!datasetCategories ? (
              <p className="text-text-muted text-sm">Chargement…</p>
            ) : datasetCategories.length === 0 ? (
```

with:

```tsx
            {!datasetCategories ? (
              <Skeleton className="h-24" />
            ) : datasetCategories.length === 0 ? (
```

Replace:

```tsx
            {!ragDocuments ? (
              <p className="text-text-muted text-sm">Chargement…</p>
            ) : ragDocuments.length === 0 ? (
```

with:

```tsx
            {!ragDocuments ? (
              <Skeleton className="h-24" />
            ) : ragDocuments.length === 0 ? (
```

Replace:

```tsx
        {!experiments ? (
          <p className="text-text-muted text-sm">Chargement…</p>
        ) : experiments.length === 0 ? (
```

with:

```tsx
        {!experiments ? (
          <Skeleton className="h-40" />
        ) : experiments.length === 0 ? (
```

- [ ] **Step 5: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors.

### `executions/page.tsx`

- [ ] **Step 1: `setError(String(e))` → `humanError` (lines 27, 33), loading skeleton**

Add `import { humanError } from "@/lib/errors";` and `Skeleton` to the `components/ui` import.

Replace:

```tsx
  const load = useCallback(() => api.enterprise.executions(projectId).then(setItems), [projectId]);
  useEffect(() => { Promise.resolve().then(load).catch((e) => setError(String(e))); }, [load]);
```

with:

```tsx
  const [loaded, setLoaded] = useState(false);
  const load = useCallback(() => api.enterprise.executions(projectId).then((next) => { setItems(next); setLoaded(true); }), [projectId]);
  useEffect(() => { load().catch((e) => { setError(humanError(e)); setLoaded(true); }); }, [load]);
```

(Add `useState` to this file's `"react"` import if not already present — it is, for `selected`/`loadingDetail`/`error`.)

Replace:

```tsx
    try { setSelected(await api.enterprise.execution(projectId, item.id)); }
    catch (cause) { setError(String(cause)); }
```

with:

```tsx
    try { setSelected(await api.enterprise.execution(projectId, item.id)); }
    catch (cause) { setError(humanError(cause)); }
```

- [ ] **Step 2: Wrap the history list with the skeleton**

Replace:

```tsx
    <section><SectionTitle>Historique ({items.length})</SectionTitle>
      {items.length === 0 ? <EmptyState>Aucune exécution. Lance une conversation dans Chat.</EmptyState> : <div className="space-y-3">{items.map((item) =>
```

with:

```tsx
    <section><SectionTitle>Historique ({items.length})</SectionTitle>
      {!loaded ? <Skeleton className="h-24" /> : items.length === 0 ? <EmptyState>Aucune exécution. Lance une conversation dans Chat.</EmptyState> : <div className="space-y-3">{items.map((item) =>
```

- [ ] **Step 3: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors.

### `system/page.tsx`

- [ ] **Step 1: `setError(String(e))` → `humanError`, replace the text loading state with `Skeleton`**

Add `import { humanError } from "@/lib/errors";` and `Skeleton` to the `components/ui` import.

Replace line 22:

```tsx
      .catch((e) => setError(String(e)))
```

with:

```tsx
      .catch((e) => setError(humanError(e)))
```

Replace (lines 39-41):

```tsx
      {!health ? (
        <p className="text-text-muted text-sm">{loading ? "Chargement…" : "—"}</p>
      ) : (
```

with:

```tsx
      {!health ? (
        loading ? (
          <div className="space-y-4">
            <Skeleton className="h-12" />
            <Skeleton className="h-32" />
            <Skeleton className="h-40" />
          </div>
        ) : (
          <p className="text-text-muted text-sm">—</p>
        )
      ) : (
```

- [ ] **Step 2: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors.

### `settings/page.tsx`

- [ ] **Step 1: Update imports**

Replace:

```tsx
import { api, Project, ProjectSettings } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { Button, Card, PageHeader, SectionTitle } from "@/components/ui";
```

with:

```tsx
import { api, Project, ProjectSettings } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { Button, Card, PageHeader, Select, SectionTitle, Skeleton, Textarea } from "@/components/ui";
import { useAction } from "@/lib/use-action";
import { humanError } from "@/lib/errors";
```

- [ ] **Step 2: `load`'s `setError(String(e))` (line 29) → `humanError`; `save` → `useAction` (lines 21-22, 31-38)**

Replace:

```tsx
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    const value = await api.projects.settings(projectId);
    setSettings(value); setSaved(value); setError(null);
  }, [projectId]);

  useEffect(() => { Promise.resolve().then(load).catch((e) => setError(String(e))); }, [load]);

  const save = async () => {
    if (!settings) return;
    setSaving(true); setError(null);
    try {
      const value = await api.projects.updateSettings(projectId, settings);
      setSettings(value); setSaved(value); refreshProjects();
    } catch (e) { setError(String(e)); } finally { setSaving(false); }
  };
```

with:

```tsx
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const value = await api.projects.settings(projectId);
    setSettings(value); setSaved(value); setLoadError(null);
  }, [projectId]);

  useEffect(() => { load().catch((e) => setLoadError(humanError(e))); }, [load]);

  const saveAction = useAction((value: ProjectSettings) => api.projects.updateSettings(projectId, value), {
    success: "Réglages enregistrés.",
  });
  const save = async () => {
    if (!settings) return;
    const value = await saveAction.run(settings);
    if (value) {
      setSettings(value);
      setSaved(value);
      refreshProjects();
    }
  };
```

- [ ] **Step 3: Update the JSX (lines 42-44, 58)**

Replace:

```tsx
    <PageHeader title="Settings" description="Configuration du projet actif. Les changements de modèle, prompt, mission ou format rendent les anciens benchmarks obsolètes." action={<div className="flex gap-2"><Button disabled={!changed || saving} onClick={() => saved && setSettings(saved)}>Annuler</Button><Button variant="accent" disabled={!changed || saving} onClick={save}>{saving ? "Enregistrement…" : "Enregistrer"}</Button></div>} />
    {error ? <Card className="border-error/30 bg-error-soft text-error text-sm">{error}</Card> : null}
    {!settings ? <p className="text-sm text-text-muted">Chargement…</p> : <>
```

with:

```tsx
    <PageHeader title="Settings" description="Configuration du projet actif. Les changements de modèle, prompt, mission ou format rendent les anciens benchmarks obsolètes." action={<div className="flex gap-2"><Button disabled={!changed || saveAction.busy} onClick={() => saved && setSettings(saved)}>Annuler</Button><Button variant="accent" disabled={!changed || saveAction.busy} onClick={save}>{saveAction.busy ? "Enregistrement…" : "Enregistrer"}</Button></div>} />
    {loadError ? <Card className="border-error/30 bg-error-soft text-error text-sm">{loadError}</Card> : null}
    {saveAction.error ? <Card className="border-error/30 bg-error-soft text-error text-sm">{saveAction.error}</Card> : null}
    {!settings ? <div className="space-y-4"><Skeleton className="h-8 w-1/3" /><Skeleton className="h-48" /><Skeleton className="h-32" /></div> : <>
```

- [ ] **Step 4: Replace the two raw `<select>` and two raw `<textarea>` elements (lines 48, 49, 54, 57), plus delete the local `Field` (line 63)**

Replace:

```tsx
        <Field label="Type de projet"><select value={settings.project_type} onChange={(e) => setSettings({ ...settings, project_type: e.target.value as Project["project_type"] })} className="field">{TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}</select></Field>
        <Field label="Mission"><textarea value={settings.purpose} rows={4} maxLength={2000} onChange={(e) => setSettings({ ...settings, purpose: e.target.value })} className="field" /></Field>
```

with:

```tsx
        <Field label="Type de projet"><Select value={settings.project_type} onChange={(v) => setSettings({ ...settings, project_type: v as Project["project_type"] })}>{TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}</Select></Field>
        <Field label="Mission"><Textarea value={settings.purpose} rows={4} maxLength={2000} onChange={(v) => setSettings({ ...settings, purpose: v })} /></Field>
```

Replace:

```tsx
        <Field label="Format de réponse"><select value={settings.output_mode} onChange={(e) => setSettings({ ...settings, output_mode: e.target.value as Project["output_mode"] })} className="field"><option value="natural">Texte naturel</option><option value="json">JSON</option><option value="flexible">Flexible</option></select></Field>
```

with:

```tsx
        <Field label="Format de réponse"><Select value={settings.output_mode} onChange={(v) => setSettings({ ...settings, output_mode: v as Project["output_mode"] })}><option value="natural">Texte naturel</option><option value="json">JSON</option><option value="flexible">Flexible</option></Select></Field>
```

Replace:

```tsx
      <section><SectionTitle>Instructions système</SectionTitle><Card><textarea value={settings.system_prompt} rows={12} maxLength={12000} onChange={(e) => setSettings({ ...settings, system_prompt: e.target.value })} className="field font-mono leading-relaxed" /><p className="text-xs text-text-muted mt-2">{settings.system_prompt.length} / 12 000 caractères</p></Card></section>
```

with:

```tsx
      <section><SectionTitle>Instructions système</SectionTitle><Card><Textarea value={settings.system_prompt} rows={12} maxLength={12000} onChange={(v) => setSettings({ ...settings, system_prompt: v })} className="font-mono leading-relaxed" /><p className="text-xs text-text-muted mt-2">{settings.system_prompt.length} / 12 000 caractères</p></Card></section>
```

Import `Field` from `@/components/ui` instead of keeping the local one — replace:

```tsx
import { Button, Card, PageHeader, Select, SectionTitle, Skeleton, Textarea } from "@/components/ui";
```

with:

```tsx
import { Button, Card, Field, PageHeader, Select, SectionTitle, Skeleton, Textarea } from "@/components/ui";
```

(this supersedes the import line from Step 1 above — apply the two edits together) and delete the local `Field` function at the bottom of the file (line 63):

```tsx
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="block text-xs text-text-muted space-y-1.5">{label}{children}</label>; }
```

Two `<input>` elements stay raw (`Identifiant technique`, `Modèle de base`, `Modèle d'inférence Hugging Face`, `Longueur maximale`) — they use the page-local `.field` CSS class via `<style jsx>` (line 59) for disabled/font-mono/number variants the shared `Input` primitive doesn't cover (a `disabled` prop, `type="number"`); converting them isn't in this task's scope (the spec's page table lists only "2 select, 2 textarea" for `/settings`, matching exactly the four replaced above). Leave the `<style jsx>` block as-is.

- [ ] **Step 5: Verify**

Run: `cd web && npx tsc --noEmit` — expected: no errors.

- [ ] **Step 6: Commit the four pages**

```bash
git add web/src/app/page.tsx web/src/app/executions/page.tsx web/src/app/system/page.tsx web/src/app/settings/page.tsx
git commit -m "feat(web): apply useAction/Skeleton/Select/Textarea to dashboard, executions, system, settings"
```

### Full browser walkthrough (manual, no code changes)

- [ ] **Step 1: Start the stack**

Run: `cd web && npm run dev` (frontend) and, in another terminal, start the FastAPI backend per its existing run instructions. Confirm `/` loads without a console error.

- [ ] **Step 2: Error/success/toast pass**

On any project, trigger one failing action (e.g. create an opportunity with a name that already exists, if the backend rejects duplicates — otherwise stop a non-existent job by editing the URL, or disconnect the backend briefly) and confirm: the error toast appears bottom-right in French, and the inline error near the form (where one exists) also shows the same message. Then trigger one succeeding action (e.g. create a dataset example, save opportunity fields) and confirm a success toast appears and auto-dismisses after ~4s.

- [ ] **Step 3: Keyboard and focus pass**

Press Tab repeatedly from the top of any page and confirm every interactive element (nav links, inputs, buttons, selects) shows a visible accent-colored ring, not the browser's default (or no) outline.

- [ ] **Step 4: Confirm dialogs**

On `/rag`, delete a document and confirm the `ConfirmDialog` (not a native `confirm()` popup) appears, blocks background interaction, and both Escape-via-click-outside and the Annuler button close it without deleting. Repeat on `/dataset` (delete an example) and `/providers` (delete a provider).

- [ ] **Step 5: Command palette**

Press ⌘K (or Ctrl+K) from any page. Confirm the input is focused immediately, typing "executions" (no accent) surfaces "Exécutions", arrow keys move the selection, Enter navigates and closes the palette, and focus returns to a sensible element afterward.

- [ ] **Step 6: Chat send-on-Entrée**

On `/chat`, type a short message and press Enter — confirm it sends (the message field is a single-line `<input>`, so there is no Shift+Enter newline behavior to check — see the spec's revised risk note).

- [ ] **Step 7: Loading skeletons**

Reload `/`, `/dataset`, `/training`, `/rag`, and `/opportunities` with the network throttled (browser dev tools → Network → Slow 3G) and confirm each shows pulsing skeleton placeholders instead of blank space or raw "Chargement…" text during the fetch.

- [ ] **Step 8: Backend regression guard**

Run: `python -m pytest` from the repo root (or the project's existing pytest invocation).
Expected: 89 tests passing, confirming the backend was not touched by this plan.

- [ ] **Step 9: Final commit**

If Step 7's manual pass surfaces no code changes, there is nothing to commit for this final task beyond what Task 8's Step 6 already committed. If any walkthrough step above required a fix, apply it, re-run `npx tsc --noEmit`, and commit with a message describing the specific fix (e.g. `fix(web): restore focus after closing ConfirmDialog on /rag`).
