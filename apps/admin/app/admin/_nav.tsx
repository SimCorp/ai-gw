import type { NavDomain } from '@aigw/ui';
import {
  Activity,
  Network,
  Sparkles,
  Scale,
  ShieldCheck,
  Boxes,
  SlidersHorizontal,
  Trophy,
  Settings,
} from 'lucide-react';

export const ADMIN_NAV: NavDomain[] = [
  {
    id: 'monitor',
    label: 'Monitor',
    icon: <Activity />,
    href: '/admin/dashboard',
    pages: [
      { href: '/admin/dashboard', label: 'Dashboard' },
      { href: '/admin/requests', label: 'Live requests' },
      { href: '/admin/reports', label: 'Cost reports' },
      { href: '/admin/alerts', label: 'Alerts' },
    ],
  },
  {
    id: 'org',
    label: 'Organisation',
    icon: <Network />,
    href: '/admin/org',
    pages: [
      { href: '/admin/org', label: 'Org tree' },
      { href: '/admin/users', label: 'Users' },
    ],
  },
  {
    id: 'transformation',
    label: 'AI Transformation',
    icon: <Sparkles />,
    href: '/admin/transformation',
    pages: [
      { href: '/admin/transformation', label: 'Overview' },
      { href: '/admin/genai-adoption', label: 'GenAI Adoption' },
      { href: '/admin/insights', label: 'AI Insights' },
      { href: '/admin/devops', label: 'DevOps Agent' },
      { href: '/admin/champions', label: 'Champions', group: 'Champions' },
      { href: '/admin/champions/activity', label: 'Activity', group: 'Champions' },
      { href: '/admin/champions/flags', label: 'Flags', group: 'Champions' },
    ],
  },
  {
    id: 'govern',
    label: 'Govern',
    icon: <Scale />,
    href: '/admin/guardrails',
    pages: [
      { href: '/admin/guardrails', label: 'Guardrails' },
      { href: '/admin/policies', label: 'Policies' },
      { href: '/admin/quotas', label: 'Quotas & budgets' },
      { href: '/admin/approvals', label: 'Approvals' },
      { href: '/admin/audit', label: 'Audit log' },
    ],
  },
  {
    id: 'security',
    label: 'Security',
    icon: <ShieldCheck />,
    href: '/admin/security/targets',
    pages: [
      { href: '/admin/security/targets', label: 'Targets' },
      { href: '/admin/security/jobs', label: 'Scan jobs' },
      { href: '/admin/security/quotas', label: 'Team quotas' },
    ],
  },
  {
    id: 'catalog',
    label: 'Catalog',
    icon: <Boxes />,
    href: '/admin/mcp',
    pages: [
      { href: '/admin/mcp', label: 'MCP servers' },
      { href: '/admin/memory', label: 'Memory' },
      { href: '/admin/skills', label: 'Skills' },
      { href: '/admin/plugins', label: 'Plugins' },
    ],
  },
  {
    id: 'configure',
    label: 'Configure',
    icon: <SlidersHorizontal />,
    href: '/admin/models',
    pages: [
      { href: '/admin/models', label: 'Model registry' },
      { href: '/admin/cache', label: 'Semantic cache' },
      { href: '/admin/providers', label: 'Providers' },
      { href: '/admin/providers#auto-drive', label: 'Auto-Drive' },
      { href: '/admin/tools', label: 'Developer tools' },
    ],
  },
  {
    id: 'league',
    label: 'League',
    icon: <Trophy />,
    href: '/admin/league/seasons',
    pages: [
      { href: '/admin/league/seasons', label: 'Seasons' },
      { href: '/admin/league/challenges', label: 'Challenges' },
      { href: '/admin/league/proposals', label: 'Proposals' },
      { href: '/admin/league/store', label: 'Store editor' },
    ],
  },
  {
    id: 'settings',
    label: 'Settings',
    icon: <Settings />,
    href: '/admin/settings/entra',
    pages: [
      { href: '/admin/settings/entra', label: 'Entra ID groups' },
      { href: '/admin/settings/sessions', label: 'Sessions' },
    ],
  },
];
