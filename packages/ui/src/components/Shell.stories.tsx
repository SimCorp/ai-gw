import type { Meta, StoryObj } from "@storybook/react";
import { AdminShell, PortalShell } from "./Shell";

const mockUser = {
  name: "Mira Rasmussen",
  email: "mira.rasmussen@simcorp.com",
  role: "Platform admin",
};

const portalUser = {
  name: "Maja Jensen",
  email: "maja.jensen@simcorp.com",
  role: "engineer",
};

const meta: Meta = {
  title: "Layout/Shell",
  parameters: {
    layout: "fullscreen",
  },
};
export default meta;

export const Admin: StoryObj = {
  render: () => (
    <div data-surface="admin" data-theme="dark" style={{ fontFamily: "var(--font-sans)" }}>
      <AdminShell
        activeId="dashboard"
        user={mockUser}
        crumbs={[{ label: "AI Gateway", href: "/admin/dashboard" }, { label: "Dashboard" }]}
      >
        <div style={{ padding: "40px", color: "var(--fg-1)" }}>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Page content goes here</h2>
          <p style={{ color: "var(--fg-2)", marginTop: 8 }}>
            This is the admin shell with the dark saturated theme.
          </p>
        </div>
      </AdminShell>
    </div>
  ),
};

export const Portal: StoryObj = {
  render: () => (
    <div data-surface="portal" data-theme="dark" style={{ fontFamily: "var(--font-sans)" }}>
      <PortalShell
        activeId="home"
        user={portalUser}
        crumbs={[{ label: "AI Portal" }, { label: "Home" }]}
      >
        <div style={{ color: "var(--fg-1)" }}>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Portal content goes here</h2>
          <p style={{ color: "var(--fg-2)", marginTop: 8 }}>
            This is the portal shell with the indigo/fuchsia theme.
          </p>
        </div>
      </PortalShell>
    </div>
  ),
};
