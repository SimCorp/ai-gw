import * as React from "react";

export interface TeamLinkProps {
  id: string;
  name: string;
}

export function TeamLink({ id, name }: TeamLinkProps) {
  return (
    <a
      href={`/admin/teams/${id}`}
      className="pill"
      style={{ display: "inline-flex", alignItems: "center", gap: 5 }}
    >
      {name}
    </a>
  );
}
