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
