// Shared OrgNode type and helpers used across the org-node frontend.

export interface OrgNode {
  id: string;
  name: string;
  slug: string;
  type: string; // free-form: area|unit|team|squad|root|etc
  parent_id: string | null;
  path: string;
  color: string | null;
  description: string | null;
  location: string | null;
  monthly_budget_usd: number | null;
  budget_alert_threshold: number | null;
  created_at: string;
  // Present on GET /nodes/{id} and tree responses
  children?: OrgNode[];
  member_count?: number;
  spend_mtd?: number;
  direct_admins?: { id: string; email: string; display_name: string; role: string }[];
  parent_direct_admins?: { id: string; email: string; display_name: string; role: string; source_node_name: string }[];
}

// Color for type badge backgrounds
const TYPE_COLORS: Record<string, string> = {
  area: '#3B82F6',
  unit: '#8B5CF6',
  team: '#10B981',
  root: 'hidden',
};

export function typeBadgeColor(type: string): string {
  return TYPE_COLORS[type] ?? '#667';
}

export function TypeBadge({ type }: { type: string }) {
  if (type === 'root') return null;
  const color = typeBadgeColor(type);
  return (
    <span style={{
      display: 'inline-block',
      padding: '1px 6px',
      borderRadius: 8,
      fontSize: 10,
      fontWeight: 600,
      letterSpacing: '0.04em',
      textTransform: 'uppercase' as const,
      background: color + '22',
      color: color,
      border: `1px solid ${color}44`,
    }}>
      {type}
    </span>
  );
}
