import type { Meta, StoryObj } from "@storybook/react";
import { Pill } from "./Pill";

const meta: Meta<typeof Pill> = {
  title: "Data Display/Pill",
  component: Pill,
  parameters: { layout: "centered" },
};
export default meta;

type Story = StoryObj<typeof Pill>;

export const Default: Story = {
  render: () => (
    <div data-surface="admin" data-theme="dark" style={{ display: "flex", gap: 8, padding: 16 }}>
      <Pill variant="default">Default</Pill>
      <Pill variant="info">Info</Pill>
      <Pill variant="good">Good</Pill>
      <Pill variant="warn">Warning</Pill>
      <Pill variant="bad">Bad</Pill>
    </div>
  ),
};

export const WithDots: Story = {
  render: () => (
    <div data-surface="admin" data-theme="dark" style={{ display: "flex", gap: 8, padding: 16 }}>
      <Pill variant="good" dot>Active</Pill>
      <Pill variant="warn" dot>Degraded</Pill>
      <Pill variant="bad" dot>Down</Pill>
      <Pill variant="info" dot>Preview</Pill>
    </div>
  ),
};

export const Portal: Story = {
  render: () => (
    <div data-surface="portal" data-theme="dark" style={{ display: "flex", gap: 8, padding: 16, background: "var(--bg)" }}>
      <Pill variant="default">Default</Pill>
      <Pill variant="info">Info</Pill>
      <Pill variant="good">Good</Pill>
      <Pill variant="warn">Warning</Pill>
      <Pill variant="bad">Bad</Pill>
    </div>
  ),
};
