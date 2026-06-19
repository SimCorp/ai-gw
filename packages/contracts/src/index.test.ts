import { describe, expect, it } from "vitest";
import { IDSchema, MoneySchema, SeveritySchema, StatusSchema } from "./index";

describe("MoneySchema", () => {
  it("accepts integer cents with a known currency", () => {
    expect(MoneySchema.parse({ cents: 1500, currency: "USD" })).toEqual({
      cents: 1500,
      currency: "USD",
    });
  });

  it("rejects non-integer cents", () => {
    expect(MoneySchema.safeParse({ cents: 1.5, currency: "USD" }).success).toBe(false);
  });

  it("rejects an unknown currency", () => {
    expect(MoneySchema.safeParse({ cents: 100, currency: "GBP" }).success).toBe(false);
  });
});

describe("enum schemas", () => {
  it("StatusSchema accepts its members and rejects others", () => {
    expect(StatusSchema.safeParse("good").success).toBe(true);
    expect(StatusSchema.safeParse("unknown").success).toBe(false);
  });

  it("SeveritySchema accepts P1..P3 only", () => {
    expect(SeveritySchema.safeParse("P1").success).toBe(true);
    expect(SeveritySchema.safeParse("P4").success).toBe(false);
  });
});

describe("IDSchema", () => {
  it("accepts a uuid and rejects a plain string", () => {
    expect(IDSchema.safeParse("3f8c4d2e-1a6b-4c9d-8e7f-0a1b2c3d4e5f").success).toBe(true);
    expect(IDSchema.safeParse("not-a-uuid").success).toBe(false);
  });
});
