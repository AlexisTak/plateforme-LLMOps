"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import Image from "next/image";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { humanError } from "@/lib/errors";
import { Button, Field, Input } from "@/components/ui";

const MIN_PASSWORD = 10;

// Renders the console only once the caller is authenticated. In "login" mode without a
// session it shows the login screen, or the first-run screen while no account exists;
// "local" and "proxy" modes always have an actor and pass straight through.
export function AuthGate({ children }: { children: ReactNode }) {
  const { state, error, refresh } = useAuth();

  if (state === null) {
    return (
      <Screen>
        {error ? (
          <div className="space-y-3 text-sm">
            <p className="text-error">API injoignable : {error}</p>
            <p className="text-text-secondary">Vérifie qu’elle tourne sur le port 8000 (.\start.ps1).</p>
            <Button onClick={() => void refresh()}>Réessayer</Button>
          </div>
        ) : (
          <p className="text-sm text-text-muted">Chargement…</p>
        )}
      </Screen>
    );
  }
  if (state.actor) return <>{children}</>;
  return state.setup_required ? <SetupScreen /> : <LoginScreen />;
}

function Screen({ title, subtitle, children }: { title?: string; subtitle?: string; children: ReactNode }) {
  return (
    <main className="min-h-screen w-full flex items-center justify-center p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="rounded-lg bg-white px-2 py-1 w-fit mx-auto shadow-[0_0_20px_rgba(79,140,255,0.16)] ring-1 ring-white/10">
          <Image src="/logo.png" alt="OpenModels" width={2172} height={790} priority className="h-10 w-auto" />
        </div>
        <div className="bg-surface border border-border rounded-lg p-6 space-y-4">
          {title && (
            <div>
              <h1 className="font-display text-xl text-text-primary tracking-tight">{title}</h1>
              {subtitle && <p className="text-sm text-text-secondary mt-1">{subtitle}</p>}
            </div>
          )}
          {children}
        </div>
      </div>
    </main>
  );
}

function LoginScreen() {
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.auth.login(email, password);
      await refresh();
    } catch (cause) {
      setError(humanError(cause));
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen title="Connexion" subtitle="Connecte-toi avec le compte créé par ton administrateur.">
      <form onSubmit={submit} className="space-y-3">
        <Field label="E-mail">
          <Input type="email" value={email} onChange={setEmail} autoComplete="username" autoFocus required className="w-full" />
        </Field>
        <Field label="Mot de passe">
          <Input type="password" value={password} onChange={setPassword} autoComplete="current-password" required className="w-full" />
        </Field>
        {error && <p role="alert" className="text-sm text-error">{error}</p>}
        <Button type="submit" variant="accent" disabled={busy || !email || !password} className="w-full">
          {busy ? "Connexion…" : "Se connecter"}
        </Button>
      </form>
    </Screen>
  );
}

function SetupScreen() {
  const { refresh } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tooShort = password.length > 0 && password.length < MIN_PASSWORD;
  const mismatch = confirm.length > 0 && confirm !== password;
  const valid = name.trim() && email.includes("@") && password.length >= MIN_PASSWORD && confirm === password;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      await api.auth.setup(email, name.trim(), password);
      await refresh();
    } catch (cause) {
      setError(humanError(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen
      title="Premier lancement"
      subtitle="Aucun compte n’existe encore. Crée le compte administrateur : il pourra ensuite créer les autres comptes et attribuer les rôles."
    >
      <form onSubmit={submit} className="space-y-3">
        <Field label="Nom">
          <Input value={name} onChange={setName} autoComplete="name" autoFocus required className="w-full" />
        </Field>
        <Field label="E-mail">
          <Input type="email" value={email} onChange={setEmail} autoComplete="username" required className="w-full" />
        </Field>
        <Field label="Mot de passe" hint={`${MIN_PASSWORD} caractères minimum`} error={tooShort ? `${MIN_PASSWORD} caractères minimum` : undefined}>
          <Input type="password" value={password} onChange={setPassword} autoComplete="new-password" required className="w-full" />
        </Field>
        <Field label="Confirmer le mot de passe" error={mismatch ? "Les mots de passe ne correspondent pas" : undefined}>
          <Input type="password" value={confirm} onChange={setConfirm} autoComplete="new-password" required className="w-full" />
        </Field>
        {error && <p role="alert" className="text-sm text-error">{error}</p>}
        <Button type="submit" variant="accent" disabled={busy || !valid} className="w-full">
          {busy ? "Création…" : "Créer l’administrateur"}
        </Button>
        <p className="text-xs text-text-muted">
          Possible uniquement depuis la machine qui héberge l’API.
        </p>
      </form>
    </Screen>
  );
}
