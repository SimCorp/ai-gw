import type { Meta, StoryObj } from "@storybook/react";
import { type ColumnDef } from "@tanstack/react-table";
import { DataTable } from "./DataTable";
import { Pill } from "./Pill";
import { MoneyCell } from "./MoneyCell";

interface Team {
  id: string;
  name: string;
  ownerEmail: string;
  members: number;
  keys: number;
  tier: "free" | "team" | "enterprise";
  usedCents: number;
  capCents: number;
  status: "good" | "warn" | "bad";
}

const MOCK_TEAMS: Team[] = [
  {
    id: "t1",
    name: "agent-platform",
    ownerEmail: "maja.jensen@simcorp.com",
    members: 12,
    keys: 8,
    tier: "enterprise",
    usedCents: 284110,
    capCents: 915000,
    status: "good",
  },
  {
    id: "t2",
    name: "risk-models",
    ownerEmail: "ahmed.hassan@simcorp.com",
    members: 6,
    keys: 4,
    tier: "team",
    usedCents: 812400,
    capCents: 850000,
    status: "warn",
  },
  {
    id: "t3",
    name: "data-eng",
    ownerEmail: "lena.bach@simcorp.com",
    members: 18,
    keys: 14,
    tier: "enterprise",
    usedCents: 1200000,
    capCents: 1000000,
    status: "bad",
  },
  {
    id: "t4",
    name: "frontend-guild",
    ownerEmail: "oscar.petrov@simcorp.com",
    members: 5,
    keys: 3,
    tier: "free",
    usedCents: 4200,
    capCents: 50000,
    status: "good",
  },
];

const COLUMNS: ColumnDef<Team>[] = [
  {
    accessorKey: "name",
    header: "Team",
    cell: (info) => (
      <span style={{ fontWeight: 500 }}>{info.getValue() as string}</span>
    ),
  },
  {
    accessorKey: "ownerEmail",
    header: "Owner",
    cell: (info) => (
      <span className="mono" style={{ fontSize: 12 }}>
        {info.getValue() as string}
      </span>
    ),
  },
  {
    accessorKey: "members",
    header: "Members",
    meta: { align: "right" },
  },
  {
    accessorKey: "keys",
    header: "Keys",
    meta: { align: "right" },
  },
  {
    accessorKey: "tier",
    header: "Tier",
    cell: (info) => {
      const tier = info.getValue() as string;
      return (
        <Pill variant={tier === "enterprise" ? "info" : tier === "team" ? "default" : "default"}>
          {tier}
        </Pill>
      );
    },
  },
  {
    accessorKey: "usedCents",
    header: "Spend MTD",
    meta: { align: "right" },
    cell: (info) => <MoneyCell cents={info.getValue() as number} />,
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: (info) => {
      const status = info.getValue() as "good" | "warn" | "bad";
      const labels = { good: "Healthy", warn: "Warning", bad: "Over budget" };
      return <Pill variant={status}>{labels[status]}</Pill>;
    },
  },
];

const meta: Meta = {
  title: "Data Display/DataTable",
  parameters: { layout: "padded" },
};
export default meta;

export const Teams: StoryObj = {
  render: () => (
    <div data-surface="admin" data-theme="dark" style={{ padding: 16, background: "var(--bg)" }}>
      <DataTable
        columns={COLUMNS}
        data={MOCK_TEAMS}
        getRowId={(row) => row.id}
        onRowClick={(row) => alert(`Clicked: ${row.name}`)}
      />
    </div>
  ),
};

export const Empty: StoryObj = {
  render: () => (
    <div data-surface="admin" data-theme="dark" style={{ padding: 16, background: "var(--bg)" }}>
      <DataTable
        columns={COLUMNS}
        data={[]}
        emptyState={<span>No teams found. Create one to get started.</span>}
      />
    </div>
  ),
};
