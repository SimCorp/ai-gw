import type { NavDomain } from "@aigw/ui";
import {
  Home,
  Play,
  KeyRound,
  Boxes,
  BarChart3,
  Sparkles,
  Trophy,
  Settings,
} from "lucide-react";

export const PORTAL_NAV: NavDomain[] = [
  {
    id: "home",
    label: "Home",
    icon: <Home />,
    href: "/portal",
    pages: [
      { href: "/portal", label: "Home" },
      { href: "/portal/docs", label: "Quickstart" },
    ],
  },
  {
    id: "build",
    label: "Build",
    icon: <Play />,
    href: "/portal/playground",
    pages: [
      { href: "/portal/playground", label: "Playground" },
      { href: "/portal/agents", label: "Agents" },
      { href: "/portal/workflows", label: "Workflows" },
      { href: "/portal/prompts", label: "Prompts" },
    ],
  },
  {
    id: "access",
    label: "Access",
    icon: <KeyRound />,
    href: "/portal/keys",
    pages: [
      { href: "/portal/models", label: "Models" },
      { href: "/portal/keys", label: "API keys" },
    ],
  },
  {
    id: "catalog",
    label: "Catalog",
    icon: <Boxes />,
    href: "/portal/library",
    pages: [
      { href: "/portal/library", label: "Library" },
      { href: "/portal/mcp", label: "MCP servers" },
      { href: "/portal/plugins", label: "Plugins" },
      { href: "/portal/skills", label: "Skills" },
      { href: "/portal/tools", label: "Tools" },
    ],
  },
  {
    id: "monitor",
    label: "Monitor",
    icon: <BarChart3 />,
    href: "/portal/usage",
    pages: [
      { href: "/portal/usage", label: "Usage & spend" },
      { href: "/portal/security", label: "Security" },
    ],
  },
  {
    id: "grow",
    label: "Grow",
    icon: <Sparkles />,
    href: "/portal/transformation",
    pages: [
      { href: "/portal/transformation", label: "AI Transformation" },
      { href: "/portal/champions", label: "Champions" },
      { href: "/portal/champions/bookings", label: "Bookings" },
    ],
  },
  {
    id: "league",
    label: "League",
    icon: <Trophy />,
    href: "/portal/league",
    pages: [
      { href: "/portal/league", label: "Challenges" },
      { href: "/portal/league/leaderboard", label: "Leaderboard" },
      { href: "/portal/league/results", label: "My Results" },
      { href: "/portal/league/store", label: "Store" },
    ],
  },
  {
    id: "account",
    label: "Account",
    icon: <Settings />,
    href: "/portal/settings",
    pages: [{ href: "/portal/settings", label: "Settings" }],
  },
];
