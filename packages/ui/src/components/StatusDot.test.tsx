import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusDot } from "./StatusDot";

describe("StatusDot", () => {
  it("applies the status modifier class", () => {
    const { container } = render(<StatusDot status="warn" />);
    const el = container.querySelector("span");
    expect(el).toHaveClass("statusdot", "statusdot--warn");
  });

  it("merges a caller-provided className", () => {
    const { container } = render(<StatusDot status="good" className="extra" />);
    expect(container.querySelector("span")).toHaveClass("statusdot--good", "extra");
  });
});
