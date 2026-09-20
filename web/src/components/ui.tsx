"use client";

import { useEffect, useRef, type ReactNode } from "react";

export function PageHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 className="font-display text-2xl text-text-primary tracking-tight">{title}</h1>
        {description && <p className="text-text-secondary text-sm mt-1 max-w-xl">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="font-display text-lg text-text-primary tracking-tight mb-3">{children}</h2>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`bg-surface border border-border rounded-lg p-4 ${className}`}>{children}</div>;
}

export function Button({
  children,
  onClick,
  disabled,
  variant = "default",
  className = "",
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "default" | "accent" | "danger" | "ghost";
  className?: string;
  type?: "button" | "submit";
}) {
  const base = "px-3 py-1.5 text-sm rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed font-medium";
  const variants: Record<string, string> = {
    default: "bg-surface-hover text-text-primary border border-border hover:border-border-strong",
    accent: "bg-accent text-white hover:bg-accent-strong shadow-sm shadow-accent/10",
    danger: "bg-error-soft text-error border border-error/30 hover:bg-error/20",
    ghost: "text-text-secondary hover:text-text-primary hover:bg-surface-hover",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`${base} ${variants[variant]} ${className}`}>
      {children}
    </button>
  );
}

export function Input({
  value,
  onChange,
  placeholder,
  className = "",
  onKeyDown,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  disabled?: boolean;
}) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      onKeyDown={onKeyDown}
      disabled={disabled}
      className={`bg-bg border border-border rounded-md px-3 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${className}`}
    />
  );
}

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

export function Pill({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full bg-surface-hover border border-border px-2 py-0.5 text-xs text-text-secondary font-mono">
      {children}
    </span>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="text-text-muted text-sm py-6 text-center border border-dashed border-border rounded-lg">{children}</p>;
}

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
  const dialogRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    dialogRef.current?.focus();
    const onEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", onEscape);
    return () => document.removeEventListener("keydown", onEscape);
  }, [open, onCancel]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onCancel}>
      <div
        ref={dialogRef}
        tabIndex={-1}
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
