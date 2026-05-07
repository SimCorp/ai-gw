import * as React from "react";

export interface MoneyCellProps {
  cents: number;
  currency?: "USD" | "EUR" | "DKK";
}

const SYMBOLS: Record<NonNullable<MoneyCellProps["currency"]>, string> = {
  USD: "$",
  EUR: "€",
  DKK: "kr",
};

export function MoneyCell({ cents, currency = "USD" }: MoneyCellProps) {
  const amount = cents / 100;
  const symbol = SYMBOLS[currency];
  const formatted = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);

  return (
    <span
      className="mono"
      style={{ fontVariantNumeric: "tabular-nums", textAlign: "right", display: "block" }}
    >
      {symbol}{formatted}
    </span>
  );
}
