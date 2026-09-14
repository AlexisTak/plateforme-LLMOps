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
