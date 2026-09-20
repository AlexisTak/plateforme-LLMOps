import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api";
import { humanError } from "@/lib/errors";

describe("humanError", () => {
  it("returns the structured detail as-is", () => {
    expect(humanError(new ApiError(404, "/api/x", "Opportunité introuvable"))).toBe("Opportunité introuvable");
  });

  it("falls back to a generic message when detail is empty", () => {
    expect(humanError(new ApiError(500, "/api/x", ""))).toBe("Erreur 500 — le serveur n'a pas pu traiter la demande.");
  });

  it("detects a network failure (fetch TypeError)", () => {
    expect(humanError(new TypeError("Failed to fetch"))).toMatch(/^API injoignable/);
  });

  it("falls back to Error.message", () => {
    expect(humanError(new Error("boom"))).toBe("boom");
  });

  it("stringifies non-Error values", () => {
    expect(humanError("raw")).toBe("raw");
  });
});
