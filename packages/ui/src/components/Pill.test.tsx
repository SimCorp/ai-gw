import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Pill } from "./Pill";

describe("Pill", () => {
  it("renders its children", () => {
    render(<Pill>active</Pill>);
    expect(screen.getByText("active")).toBeInTheDocument();
  });

  it("applies the base class and no variant modifier by default", () => {
    render(<Pill>plain</Pill>);
    const el = screen.getByText("plain");
    expect(el).toHaveClass("pill");
    expect(el.className).not.toMatch(/pill--/);
  });

  it("applies the variant modifier class", () => {
    render(<Pill variant="good">ok</Pill>);
    expect(screen.getByText("ok")).toHaveClass("pill", "pill--good");
  });

  it("renders a dot when dot=true", () => {
    const { container } = render(<Pill dot>with dot</Pill>);
    expect(container.querySelector("span.dot")).not.toBeNull();
  });
});
