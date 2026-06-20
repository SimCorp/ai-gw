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
    href: "/",
    pages: [
      { href: "/", label: "Home" },
      { href: "/docs", label: "Quickstart" },
    ],
  },
  {
    id: "build",
    label: "Build",
    icon: <Play />,
    href: "/playground",
    pages: [
      { href: "/playground", label: "Playground" },
      { href: "/agents", label: "Agents" },
      { href: "/workflows", label: "Workflows" },
      { href: "/prompts", label: "Prompts" },
    ],
  },
  {
    id: "access",
    label: "Access",
    icon: <KeyRound />,
    href: "/keys",
    pages: [
      { href: "/models", label: "Models" },
      { href: "/keys", label: "API keys" },
    ],
  },
  {
    id: "catalog",
    label: "Catalog",
    icon: <Boxes />,
    href: "/library",
    pages: [
      { href: "/library", label: "Library" },
      { href: "/mcp", label: "MCP servers" },
      { href: "/plugins", label: "Plugins" },
      { href: "/skills", label: "Skills" },
      { href: "/tools", label: "Tools" },
    ],
  },
  {
    id: "monitor",
    label: "Monitor",
    icon: <BarChart3 />,
    href: "/usage",
    pages: [
      { href: "/usage", label: "Usage & spend" },
      { href: "/security", label: "Security" },
    ],
  },
  {
    id: "grow",
    label: "Grow",
    icon: <Sparkles />,
    href: "/transformation",
    pages: [
      { href: "/transformation", label: "AI Transformation" },
      { href: "/champions", label: "Champions" },
      { href: "/champions/bookings", label: "Bookings" },
    ],
  },
  {
    id: "league",
    label: "League",
    icon: <Trophy />,
    href: "/league",
    pages: [
      { href: "/league", label: "Challenges" },
      { href: "/league/leaderboard", label: "Leaderboard" },
      { href: "/league/results", label: "My Results" },
      { href: "/league/store", label: "Store" },
    ],
  },
  {
    id: "account",
    label: "Account",
    icon: <Settings />,
    href: "/settings",
    pages: [{ href: "/settings", label: "Settings" }],
  },
];
