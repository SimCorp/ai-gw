import type { Meta, StoryObj } from "@storybook/react";
import { KpiCard } from "./KpiCard";
import { KpiGrid } from "./KpiGrid";

const meta: Meta<typeof KpiCard> = {
  title: "Data Display/KpiCard",
  component: KpiCard,
  parameters: {
    layout: "padded",
  },
};
export default meta;

type Story = StoryObj<typeof KpiCard>;

export const WithDeltaUp: Story = {
  render: () => (
    <div data-surface="admin" data-theme="dark">
      <KpiCard
        label="Total spend"
        value="$3,847"
        unit=".21"
        delta={{ label: "12.4% vs prev 24h", direction: "up" }}
        sparkline={
          <svg viewBox="0 0 100 28" preserveAspectRatio="none" style={{ display: "block", width: "100%", height: 28 }}>
            <path d="M0,18 L10,16 L20,20 L30,12 L40,15 L50,9 L60,13 L70,8 L80,11 L90,6 L100,9" fill="none" stroke="var(--sc-blue)" strokeWidth="1.5" />
            <path d="M0,18 L10,16 L20,20 L30,12 L40,15 L50,9 L60,13 L70,8 L80,11 L90,6 L100,9 L100,28 L0,28 Z" fill="var(--sc-blue)" opacity="0.08" />
          </svg>
        }
      />
    </div>
  ),
};

export const WithDeltaDown: Story = {
  render: () => (
    <div data-surface="admin" data-theme="dark">
      <KpiCard
        label="Error rate"
        value="2.41"
        unit="%"
        delta={{ label: "0.8 pp vs prev 24h", direction: "down" }}
      />
    </div>
  ),
};

export const WithDeltaFlat: Story = {
  render: () => (
    <div data-surface="admin" data-theme="dark">
      <KpiCard
        label="p99 gateway latency"
        value="38"
        unit="ms"
        delta={{ label: "within SLO (50ms)", direction: "flat" }}
      />
    </div>
  ),
};

export const NoDelta: Story = {
  render: () => (
    <div data-surface="admin" data-theme="dark">
      <KpiCard label="Active API keys" value="487" />
    </div>
  ),
};

export const AllFour: Story = {
  render: () => (
    <div data-surface="admin" data-theme="dark" style={{ padding: 16, background: "var(--bg)" }}>
      <KpiGrid>
        <KpiCard
          label="Total spend"
          value="$3,847"
          unit=".21"
          delta={{ label: "12.4% vs prev 24h", direction: "down" }}
        />
        <KpiCard
          label="Cache savings"
          value="$1,209"
          unit=".45"
          delta={{ label: "8.1% vs prev 24h", direction: "up" }}
        />
        <KpiCard
          label="Requests"
          value="2.41"
          unit="M"
          delta={{ label: "3.2% · 27.8 req/s avg", direction: "up" }}
        />
        <KpiCard
          label="p99 gateway latency"
          value="38"
          unit="ms"
          delta={{ label: "within SLO (50ms)", direction: "flat" }}
        />
      </KpiGrid>
    </div>
  ),
};
