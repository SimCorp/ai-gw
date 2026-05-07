import * as React from "react";
import * as Tooltip from "@radix-ui/react-tooltip";

export interface ModelCapabilities {
  context?: number;
  tools?: boolean;
  vision?: boolean;
}

export interface ModelChipProps {
  id: string;
  name?: string;
  capabilities?: ModelCapabilities;
}

type Provider = "anthropic" | "openai" | "azure" | "google" | "internal";

function detectProvider(id: string): Provider {
  const lower = id.toLowerCase();
  if (lower.startsWith("anthropic") || lower.includes("claude")) return "anthropic";
  if (lower.startsWith("azure")) return "azure";
  if (lower.startsWith("google") || lower.includes("gemini")) return "google";
  if (lower.startsWith("internal") || lower.startsWith("local")) return "internal";
  return "openai";
}

const PROVIDER_ICONS: Record<Provider, string> = {
  anthropic: "🔷",
  openai: "⬜",
  azure: "☁️",
  google: "🔴",
  internal: "⚙️",
};

export function ModelChip({ id, name, capabilities }: ModelChipProps) {
  const provider = detectProvider(id);
  const icon = PROVIDER_ICONS[provider];
  const displayName = name ?? id.split("/").pop() ?? id;

  const chip = (
    <span className="tag" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <span aria-hidden="true">{icon}</span>
      {displayName}
    </span>
  );

  if (!capabilities) return chip;

  const tooltipLines: string[] = [];
  if (capabilities.context) tooltipLines.push(`Context: ${capabilities.context.toLocaleString()} tokens`);
  if (capabilities.tools) tooltipLines.push("Tools: yes");
  if (capabilities.vision) tooltipLines.push("Vision: yes");

  // NOTE: Ideally the consuming app wraps its tree in a single <Tooltip.Provider>.
  // This per-chip Provider works but loses the shared delayDuration timer.
  return (
    <Tooltip.Provider delayDuration={300}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>{chip}</Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            style={{
              background: "var(--surface-2)",
              border: "1px solid var(--rule)",
              borderRadius: "var(--radius-2)",
              padding: "8px 12px",
              fontSize: 12,
              color: "var(--fg-1)",
              boxShadow: "var(--shadow-2)",
              maxWidth: 200,
            }}
            sideOffset={4}
          >
            <div style={{ fontFamily: "var(--font-mono)", lineHeight: 1.6 }}>
              {tooltipLines.map((line) => (
                <div key={line}>{line}</div>
              ))}
            </div>
            <Tooltip.Arrow style={{ fill: "var(--rule)" }} />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}
