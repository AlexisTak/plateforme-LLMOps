"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { ROLE_LABELS, useAuth } from "@/lib/auth-context";
import { humanError } from "@/lib/errors";
import { useToast } from "@/components/toast";
import { Button, Field, Input } from "@/components/ui";

const MIN_PASSWORD = 10;

// Signed-in identity at the bottom of the sidebar, with password change and logout in
// "login" mode. "local" has no accounts and "proxy" delegates both to the SSO gateway.
export function UserMenu() {
  const { state, actor, logout } = useAuth();
  const [passwordOpen, setPasswordOpen] = useState(false);
  if (!state || !actor) return null;

  const loginMode = state.auth_mode === "login";
  return (
    <div className="pt-2 border-t border-border space-y-2">
      <div className="flex items-center gap-2 min-w-0">
        <span aria-hidden className="h-7 w-7 shrink-0 rounded-full bg-accent-soft text-accent-strong text-xs font-medium flex items-center justify-center">
          {(actor.name || actor.email).slice(0, 1).toUpperCase()}
        </span>
        <div className="min-w-0 leading-tight">
          <p className="text-sm text-text-primary truncate" title={actor.email}>{actor.name}</p>
          <p className="text-[10px] text-text-muted">
            {state.auth_mode === "local" ? "Mode local, sans authentification" : ROLE_LABELS[actor.role]}
          </p>
        </div>
      </div>
      {loginMode && (
        <div className="flex gap-1">
          <Button variant="ghost" className="flex-1 text-xs" onClick={() => setPasswordOpen(true)}>Mot de passe</Button>
          <Button variant="ghost" className="flex-1 text-xs" onClick={() => void logout()}>Déconnexion</Button>
        </div>
      )}
      {passwordOpen && <PasswordDialog onClose={() => setPasswordOpen(false)} />}
    </div>
  );
}

function PasswordDialog({ onClose }: { onClose: () => void }) {
  const { refresh } = useAuth();
  const toast = useToast();
  const dialogRef = useRef<HTMLFormElement>(null);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onEscape = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onEscape);
    return () => document.removeEventListener("keydown", onEscape);
  }, [onClose]);

  const valid = current && next.length >= MIN_PASSWORD && next === confirm;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      // The API revokes every session of the account, this one included.
      await api.auth.changePassword(current, next);
      toast("Mot de passe modifié — reconnecte-toi avec le nouveau", "success");
      await refresh();
    } catch (cause) {
      setError(humanError(cause));
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <form
        ref={dialogRef}
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="password-dialog-title"
        className="bg-surface border border-border rounded-lg p-5 max-w-sm w-full space-y-3"
      >
        <h2 id="password-dialog-title" className="font-display text-base text-text-primary">Changer mon mot de passe</h2>
        <p className="text-xs text-text-muted">Toutes tes sessions seront fermées, y compris celle-ci.</p>
        <Field label="Mot de passe actuel">
          <Input type="password" value={current} onChange={setCurrent} autoComplete="current-password" autoFocus className="w-full" />
        </Field>
        <Field label="Nouveau mot de passe" hint={`${MIN_PASSWORD} caractères minimum`}
               error={next.length > 0 && next.length < MIN_PASSWORD ? `${MIN_PASSWORD} caractères minimum` : undefined}>
          <Input type="password" value={next} onChange={setNext} autoComplete="new-password" className="w-full" />
        </Field>
        <Field label="Confirmer" error={confirm.length > 0 && confirm !== next ? "Les mots de passe ne correspondent pas" : undefined}>
          <Input type="password" value={confirm} onChange={setConfirm} autoComplete="new-password" className="w-full" />
        </Field>
        {error && <p role="alert" className="text-sm text-error">{error}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>Annuler</Button>
          <Button type="submit" variant="accent" disabled={busy || !valid}>{busy ? "Enregistrement…" : "Enregistrer"}</Button>
        </div>
      </form>
    </div>
  );
}
