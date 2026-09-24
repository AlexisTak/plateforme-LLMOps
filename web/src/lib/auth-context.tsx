"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api, AUTH_REQUIRED_EVENT, type Actor, type AuthState, type RoleName } from "@/lib/api";

const ROLE_RANK: Record<RoleName, number> = { viewer: 0, operator: 1, reviewer: 2, admin: 3 };

export const ROLE_LABELS: Record<RoleName, string> = {
  viewer: "Lecteur",
  operator: "Opérateur",
  reviewer: "Validateur",
  admin: "Administrateur",
};

export const ROLE_DESCRIPTIONS: Record<RoleName, string> = {
  viewer: "Consulte projets, benchmarks et chat",
  operator: "Lance entraînements, indexations et modifie les données",
  reviewer: "Opérateur + approuve les versions et les outils",
  admin: "Tous les droits : comptes, rôles, politiques, mode hors ligne",
};

export function hasRole(actor: Actor | null, minimum: RoleName): boolean {
  return actor !== null && ROLE_RANK[actor.role] >= ROLE_RANK[minimum];
}

type AuthContextValue = {
  state: AuthState | null;
  actor: Actor | null;
  // null while /api/auth/me hasn't answered (API down or starting)
  error: string | null;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setState(await api.auth.me());
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.auth.logout();
    } finally {
      await refresh();
    }
  }, [refresh]);

  useEffect(() => {
    // Initial load, then re-check whenever any API call reports an expired session.
    void Promise.resolve().then(refresh);
    const onAuthRequired = () => void refresh();
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
  }, [refresh]);

  return (
    <AuthContext.Provider value={{ state, actor: state?.actor ?? null, error, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth doit être utilisé dans <AuthProvider>");
  return value;
}
