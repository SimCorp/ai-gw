import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MoneyCell } from "./MoneyCell";

describe("MoneyCell", () => {
  it("formats cents as USD by default", () => {
    render(<MoneyCell cents={12345} />);
    expect(screen.getByText("$123.45")).toBeInTheDocument();
  });

  it("uses the currency symbol for the given currency", () => {
    render(<MoneyCell cents={5000} currency="EUR" />);
    expect(screen.getByText("€50.00")).toBeInTheDocument();
  });

  it("always shows two fraction digits", () => {
    render(<MoneyCell cents={100} currency="DKK" />);
    expect(screen.getByText("kr1.00")).toBeInTheDocument();
  });
});
