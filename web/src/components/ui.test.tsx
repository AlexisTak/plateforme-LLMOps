import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ConfirmDialog, StatusBadge } from "@/components/ui";
import { ConfusionMatrix } from "@/components/confusion-matrix";

describe("ConfirmDialog", () => {
  it("renders nothing when closed", () => {
    const { container } = render(<ConfirmDialog open={false} title="x" onConfirm={() => {}} onCancel={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("is an accessible dialog that closes on Escape", () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog open title="Supprimer ?" onConfirm={() => {}} onCancel={onCancel} />);
    const dialog = screen.getByRole("dialog", { name: "Supprimer ?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("calls onConfirm from the confirm button", () => {
    const onConfirm = vi.fn();
    render(<ConfirmDialog open title="Go" confirmLabel="Oui" onConfirm={onConfirm} onCancel={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Oui" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});

describe("StatusBadge", () => {
  it("translates known statuses and echoes unknown ones", () => {
    render(<StatusBadge status="production" />);
    expect(screen.getByText("production")).toBeInTheDocument();
    render(<StatusBadge status="weird-status" />);
    expect(screen.getByText("weird-status")).toBeInTheDocument();
  });
});

describe("ConfusionMatrix", () => {
  it("renders one row per actual class plus an invalid column", () => {
    render(
      <ConfusionMatrix
        labels={["billing", "technical"]}
        rows={[
          { actual: "billing", predicted: { billing: 9, technical: 1, __invalid__: 0 } },
          { actual: "technical", predicted: { billing: 0, technical: 7, __invalid__: 2 } },
        ]}
      />,
    );
    expect(screen.getAllByRole("row")).toHaveLength(3); // header + 2 classes
    expect(screen.getByText("invalide")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
  });

  it("renders nothing without rows", () => {
    const { container } = render(<ConfusionMatrix labels={["a", "b"]} rows={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
