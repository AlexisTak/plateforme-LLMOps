import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/" }));

import { LINKS } from "@/components/nav-menu";
import { filterLinks, normalizeForSearch } from "@/components/command-palette";

describe("command palette search", () => {
  it("strips accents when normalizing", () => {
    expect(normalizeForSearch("Exécutions")).toBe("executions");
  });

  it("matches accented labels from an unaccented query", () => {
    expect(filterLinks("executions").some((l) => l.label === "Exécutions")).toBe(true);
  });

  it("returns every link for an empty query", () => {
    expect(filterLinks("")).toHaveLength(LINKS.length);
    expect(filterLinks("   ")).toHaveLength(LINKS.length);
  });

  it("returns nothing for a query that matches no label", () => {
    expect(filterLinks("zzz-inexistant")).toHaveLength(0);
  });

  it("lists the Decision Models entry", () => {
    expect(LINKS.some((l) => l.href === "/decision-models")).toBe(true);
  });
});
