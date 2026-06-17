import * as React from "react";

export interface JsonViewerProps {
  value: unknown;
  collapsed?: number;
}

interface JsonNodeProps {
  value: unknown;
  depth: number;
  collapsed: number;
  label?: string;
}

function isPrimitive(val: unknown): val is string | number | boolean | null | undefined {
  return val === null || val === undefined || typeof val !== "object";
}

function formatPrimitive(val: unknown): React.ReactNode {
  if (val === null) return <span style={{ color: "var(--fg-3)" }}>null</span>;
  if (val === undefined) return <span style={{ color: "var(--fg-3)" }}>undefined</span>;
  if (typeof val === "string")
    return <span style={{ color: "var(--cat-teal)" }}>&quot;{val}&quot;</span>;
  if (typeof val === "number")
    return <span style={{ color: "var(--cat-orange)" }}>{String(val)}</span>;
  if (typeof val === "boolean")
    return <span style={{ color: "var(--accent)" }}>{String(val)}</span>;
  return <span>{String(val)}</span>;
}

function JsonNode({ value, depth, collapsed, label }: JsonNodeProps) {
  const [open, setOpen] = React.useState(depth < collapsed);

  const indent = depth * 16;

  if (isPrimitive(value)) {
    return (
      <div style={{ paddingLeft: indent, fontFamily: "var(--font-mono)", fontSize: 12, lineHeight: 1.6 }}>
        {label !== undefined && (
          <span style={{ color: "var(--fg-2)" }}>{label}: </span>
        )}
        {formatPrimitive(value)}
      </div>
    );
  }

  const isArray = Array.isArray(value);
  const entries = isArray
    ? (value as unknown[]).map((v, i) => [String(i), v] as [string, unknown])
    : Object.entries(value as Record<string, unknown>);

  const openBrace = isArray ? "[" : "{";
  const closeBrace = isArray ? "]" : "}";
  const count = entries.length;

  return (
    <div style={{ paddingLeft: label !== undefined ? indent : 0, fontFamily: "var(--font-mono)", fontSize: 12, lineHeight: 1.6 }}>
      <span
        style={{ cursor: count > 0 ? "pointer" : "default", userSelect: "none" }}
        onClick={() => count > 0 && setOpen((v) => !v)}
        role={count > 0 ? "button" : undefined}
        aria-expanded={count > 0 ? open : undefined}
        tabIndex={count > 0 ? 0 : undefined}
        onKeyDown={(e) => {
          if (count > 0 && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            setOpen((v) => !v);
          }
        }}
      >
        {label !== undefined && (
          <span style={{ color: "var(--fg-2)" }}>{label}: </span>
        )}
        {count > 0 ? (
          <span style={{ color: "var(--fg-3)", fontSize: 10, marginRight: 4 }}>
            {open ? "▼" : "▶"}
          </span>
        ) : null}
        <span style={{ color: "var(--fg-3)" }}>{openBrace}</span>
        {!open && (
          <span style={{ color: "var(--fg-3)" }}>
            {isArray ? ` ${count} items ` : ` ${count} keys `}
          </span>
        )}
        {!open && <span style={{ color: "var(--fg-3)" }}>{closeBrace}</span>}
      </span>

      {open && (
        <>
          {entries.map(([k, v]) => (
            <JsonNode
              key={k}
              value={v}
              depth={depth + 1}
              collapsed={collapsed}
              label={isArray ? undefined : k}
            />
          ))}
          <div style={{ paddingLeft: indent }}>
            <span style={{ color: "var(--fg-3)" }}>{closeBrace}</span>
          </div>
        </>
      )}
    </div>
  );
}

export function JsonViewer({ value, collapsed = 2 }: JsonViewerProps) {
  return (
    <div
      style={{
        background: "var(--surface-soft)",
        border: "1px solid var(--rule)",
        borderRadius: "var(--radius-2)",
        padding: "10px 12px",
        overflowX: "auto",
      }}
    >
      <JsonNode value={value} depth={0} collapsed={collapsed} />
    </div>
  );
}
