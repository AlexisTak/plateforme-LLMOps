"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, type RoleName, type User, type UserUpdate } from "@/lib/api";
import { hasRole, ROLE_DESCRIPTIONS, ROLE_LABELS, useAuth } from "@/lib/auth-context";
import { humanError } from "@/lib/errors";
import { useAction } from "@/lib/use-action";
import { Button, Card, ConfirmDialog, EmptyState, Field, Input, PageHeader, Pill, SectionTitle, Select, Skeleton } from "@/components/ui";

const ROLES: RoleName[] = ["viewer", "operator", "reviewer", "admin"];
const MIN_PASSWORD = 10;

export default function UsersPage() {
  const { state, actor } = useAuth();

  if (state?.auth_mode !== "login") {
    return (
      <div className="space-y-6">
        <PageHeader title="Utilisateurs" />
        <Card className="text-sm text-text-secondary space-y-2">
          <p>
            Les comptes sont gérés ici en mode <code>login</code>. Mode actuel : <code>{state?.auth_mode}</code>
            {state?.auth_mode === "proxy" ? " — les identités viennent de la passerelle SSO." : " — aucun compte, tout appelant est administrateur."}
          </p>
          <p>Pour l’activer : <code>BISCUITS_AUTH_MODE=login</code> dans <code>.env</code>, puis redémarrer l’API.</p>
        </Card>
      </div>
    );
  }
  if (!hasRole(actor, "admin")) {
    return (
      <div className="space-y-6">
        <PageHeader title="Utilisateurs" />
        <EmptyState>Réservé aux administrateurs.</EmptyState>
      </div>
    );
  }
  return <UsersAdmin currentUserId={actor!.id} />;
}

function UsersAdmin({ currentUserId }: { currentUserId: string }) {
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState<User | null>(null);
  const [toggling, setToggling] = useState<User | null>(null);

  const refresh = useCallback(() => {
    api.auth.users()
      .then((list) => {
        setUsers(list);
        setError(null);
      })
      .catch((cause) => setError(humanError(cause)));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const update = useAction(
    (id: string, changes: UserUpdate) => api.auth.updateUser(id, changes),
    { success: (user) => `Compte de ${user.name} mis à jour` },
  );

  const apply = async (user: User, changes: UserUpdate) => {
    if (await update.run(user.id, changes)) refresh();
  };

  return (
    <div className="space-y-8">
      <PageHeader
        title="Utilisateurs"
        description="Comptes locaux et rôles globaux. L’accès à chaque projet se règle ensuite dans Entreprise → Équipe."
      />
      {error && <Card className="border-error/30 bg-error-soft text-error text-sm">{error}</Card>}

      <section>
        <SectionTitle>Nouveau compte</SectionTitle>
        <CreateUserForm onCreated={refresh} />
      </section>

      <section>
        <SectionTitle>Comptes</SectionTitle>
        {users === null ? (
          <Skeleton className="h-24" />
        ) : users.length === 0 ? (
          <EmptyState>Aucun compte.</EmptyState>
        ) : (
          <div className="space-y-2">
            {users.map((user) => {
              const self = user.id === currentUserId;
              return (
                <Card key={user.id} className={`flex items-center justify-between gap-4 flex-wrap ${user.enabled ? "" : "opacity-60"}`}>
                  <div className="min-w-0">
                    <p className="text-sm text-text-primary flex items-center gap-2">
                      {user.name}
                      {self && <Pill>vous</Pill>}
                      {!user.enabled && <Pill>désactivé</Pill>}
                    </p>
                    <p className="text-xs text-text-muted">{user.email} · créé le {new Date(user.created_at).toLocaleDateString("fr-FR")}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Select
                      value={user.role}
                      onChange={(role) => void apply(user, { role: role as RoleName })}
                      disabled={self || update.busy}
                    >
                      {ROLES.map((role) => <option key={role} value={role}>{ROLE_LABELS[role]}</option>)}
                    </Select>
                    <Button variant="ghost" onClick={() => setResetting(user)} disabled={update.busy}>Réinitialiser le mot de passe</Button>
                    {!self && (
                      <Button variant={user.enabled ? "danger" : "default"} onClick={() => setToggling(user)} disabled={update.busy}>
                        {user.enabled ? "Désactiver" : "Réactiver"}
                      </Button>
                    )}
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </section>

      <section>
        <SectionTitle>Rôles</SectionTitle>
        <Card className="grid gap-3 sm:grid-cols-2 text-sm">
          {ROLES.map((role) => (
            <div key={role}>
              <p className="text-text-primary">{ROLE_LABELS[role]} <code className="text-xs text-text-muted">{role}</code></p>
              <p className="text-xs text-text-secondary">{ROLE_DESCRIPTIONS[role]}</p>
            </div>
          ))}
          <p className="sm:col-span-2 text-xs text-text-muted">
            Le rôle global est un plafond : hors administrateurs, il faut aussi être membre d’un projet pour y accéder,
            avec le rôle attribué dans ce projet.
          </p>
        </Card>
      </section>

      <ConfirmDialog
        open={toggling !== null}
        title={toggling?.enabled ? `Désactiver ${toggling?.name} ?` : `Réactiver ${toggling?.name} ?`}
        description={toggling?.enabled ? "Ses sessions sont fermées immédiatement et il ne peut plus se connecter." : "Il pourra de nouveau se connecter."}
        confirmLabel={toggling?.enabled ? "Désactiver" : "Réactiver"}
        danger={toggling?.enabled}
        onCancel={() => setToggling(null)}
        onConfirm={() => {
          const user = toggling!;
          setToggling(null);
          void apply(user, { enabled: !user.enabled });
        }}
      />
      {resetting && (
        <ResetPasswordDialog
          user={resetting}
          onClose={() => setResetting(null)}
          onSubmit={async (password) => {
            await apply(resetting, { password });
            setResetting(null);
          }}
        />
      )}
    </div>
  );
}

function CreateUserForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<RoleName>("viewer");
  const [password, setPassword] = useState("");
  const create = useAction(
    () => api.auth.createUser({ name: name.trim(), email: email.trim(), role, password }),
    { success: (user) => `Compte créé pour ${user.email}` },
  );
  const valid = name.trim() && email.includes("@") && password.length >= MIN_PASSWORD;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!valid) return;
    if (await create.run()) {
      setName("");
      setEmail("");
      setPassword("");
      setRole("viewer");
      onCreated();
    }
  };

  return (
    <Card>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 items-end">
        <Field label="Nom"><Input value={name} onChange={setName} className="w-full" /></Field>
        <Field label="E-mail"><Input type="email" value={email} onChange={setEmail} autoComplete="off" className="w-full" /></Field>
        <Field label="Rôle">
          <Select value={role} onChange={(value) => setRole(value as RoleName)} className="w-full">
            {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
          </Select>
        </Field>
        <Field label="Mot de passe initial" hint={`${MIN_PASSWORD} caractères min., à transmettre à la personne`}>
          <Input type="password" value={password} onChange={setPassword} autoComplete="new-password" className="w-full" />
        </Field>
        <div className="sm:col-span-2 lg:col-span-4 flex justify-end">
          <Button type="submit" variant="accent" disabled={!valid || create.busy}>{create.busy ? "Création…" : "Créer le compte"}</Button>
        </div>
      </form>
    </Card>
  );
}

function ResetPasswordDialog({ user, onClose, onSubmit }: { user: User; onClose: () => void; onSubmit: (password: string) => Promise<void> }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onEscape = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onEscape);
    return () => document.removeEventListener("keydown", onEscape);
  }, [onClose]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (password.length < MIN_PASSWORD) return;
    setBusy(true);
    await onSubmit(password);
    setBusy(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <form
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="reset-dialog-title"
        className="bg-surface border border-border rounded-lg p-5 max-w-sm w-full space-y-3"
      >
        <h2 id="reset-dialog-title" className="font-display text-base text-text-primary">Nouveau mot de passe pour {user.name}</h2>
        <p className="text-xs text-text-muted">Ses sessions en cours sont fermées. Transmets-lui ce mot de passe ; il pourra le changer ensuite.</p>
        <Field label="Nouveau mot de passe" hint={`${MIN_PASSWORD} caractères minimum`}>
          <Input type="password" value={password} onChange={setPassword} autoComplete="new-password" autoFocus className="w-full" />
        </Field>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>Annuler</Button>
          <Button type="submit" variant="accent" disabled={busy || password.length < MIN_PASSWORD}>Enregistrer</Button>
        </div>
      </form>
    </div>
  );
}
