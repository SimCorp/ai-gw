import type { Meta, StoryObj } from "@storybook/react";
import { Button } from "./Button";

const meta: Meta<typeof Button> = {
  title: "Inputs/Button",
  component: Button,
  parameters: { layout: "centered" },
};
export default meta;

type Story = StoryObj<typeof Button>;

export const AllVariants: Story = {
  render: () => (
    <div data-surface="admin" data-theme="dark" style={{ display: "flex", gap: 8, padding: 16, flexWrap: "wrap" }}>
      <Button variant="default">Default</Button>
      <Button variant="primary">Primary</Button>
      <Button variant="ghost">Ghost</Button>
      <Button variant="danger">Danger</Button>
    </div>
  ),
};

export const Sizes: Story = {
  render: () => (
    <div data-surface="admin" data-theme="dark" style={{ display: "flex", gap: 8, padding: 16, alignItems: "center" }}>
      <Button variant="primary" size="md">Medium (default)</Button>
      <Button variant="primary" size="sm">Small</Button>
      <Button variant="default" size="md">Default md</Button>
      <Button variant="default" size="sm">Default sm</Button>
    </div>
  ),
};

export const Portal: Story = {
  render: () => (
    <div data-surface="portal" data-theme="dark" style={{ display: "flex", gap: 8, padding: 16, background: "var(--bg)" }}>
      <Button variant="default">Default</Button>
      <Button variant="primary">Primary</Button>
      <Button variant="ghost">Ghost</Button>
      <Button variant="danger">Danger</Button>
    </div>
  ),
};
