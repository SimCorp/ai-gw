'use client';

import { useState, useEffect } from 'react';

const BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? 'http://localhost:8005';

interface Plugin {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  version: string;
  author: string;
  category: 'tool' | 'integration' | 'data' | 'security' | 'workflow';
  scopes: string[];
  homepage_url: string | null;
  enabled: boolean;
  override_count: number;
  created_at: string;
}

interface PluginTeamOverride {
  team_id: string;
  team_name: string;
  enabled: boolean;
  granted_at: string;
}

interface PluginDetail {
  plugin: Plugin;
  overrides: PluginTeamOverride[];
}

const CATEGORY_COLORS: Record<Plugin['category'], string> = {
  tool: '#1a6bbf',
  integration: '#6b3fa0',
  data: '#b85c00',
  security: '#b81c1c',
  workflow: '#1a7a40',
};

const CATEGORY_BG: Record<Plugin['category'], string> = {
  tool: '#dbeafe',
  integration: '#ede9fe',
  data: '#fed7aa',
  security: '#fee2e2',
  workflow: '#d1fae5',
};

const ALL_CATEGORIES: Array<Plugin['category'] | 'all'> = [
  'all', 'tool', 'integration', 'data', 'security', 'workflow',
];

const SCOPE_ICONS: Record<string, string> = {
  internet: '\u{1F310}',
  compute: '\u{1F4BB}',
  files: '\u{1F4C1}',
  github: '\u{1F527}',
  jira: '\u{1F527}',
  confluence: '\u{1F527}',
  slack: '\u{1F527}',
  database: '\u{1F5C4}\u{FE0F}',
};

function scopeIcon(scope: string): string {
  const lower = scope.toLowerCase();
  for (const [key, icon] of Object.entries(SCOPE_ICONS)) {
    if (lower.includes(key)) return icon;
  }
  return '\u{1F511}';
}

// Detect first-party authors: ends with "SimCorp" or "simcorp.com", or is "internal"
function isFirstParty(author: string): boolean {
  const lower = author.toLowerCase();
  return lower.includes('simcorp') || lower === 'internal';
}

function PluginDetailPanel({ pluginId }: { pluginId: string }) {
  const [detail, setDetail] = useState<PluginDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`${BASE}/plugins/${pluginId}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<PluginDetail>;
      })
      .then(data => setDetail(data))
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [pluginId]);

  if (loading) {
    return (
      <div style={{ padding: '12px 0', color: 'var(--fg-3)', fontSize: 13 }}>
        Loading details…
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '12px 0', color: 'var(--bad)', fontSize: 13 }}>
        Failed to load details: {error}
      </div>
    );
  }

  if (!detail) return null;

  const plugin = detail.plugin;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {plugin.description && (
        <p style={{ margin: 0, fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.6 }}>
          {plugin.description}
        </p>
      )}

      {plugin.homepage_url && (
        <div>
          <a
            href={plugin.homepage_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: 13, color: 'var(--accent, #0A7BD7)', textDecoration: 'none' }}
          >
            Learn more →
          </a>
        </div>
      )}

      {plugin.scopes.length > 0 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-3)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Scopes
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {plugin.scopes.map(scope => (
              <div key={scope} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--fg-2)' }}>
                <span>{scopeIcon(scope)}</span>
                <span className="mono" style={{ fontSize: 12 }}>{scope}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function PluginsPage() {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loadedIds, setLoadedIds] = useState<Set<string>>(new Set());
  const [category, setCategory] = useState<Plugin['category'] | 'all'>('all');
  const [search, setSearch] = useState('');

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`${BASE}/plugins`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<Plugin[]>;
      })
      .then(data => setPlugins(Array.isArray(data) ? data : []))
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const handleExpand = (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
    } else {
      setExpandedId(id);
      setLoadedIds(prev => new Set(prev).add(id));
    }
  };

  const enabledPlugins = plugins.filter(p => p.enabled);

  const filtered = enabledPlugins.filter(p => {
    if (category !== 'all' && p.category !== category) return false;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      return (
        p.name.toLowerCase().includes(q) ||
        p.slug.toLowerCase().includes(q) ||
        (p.description ?? '').toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>Plugins</h1>
          <p>Browse first-party and community plugins available for your AI workflows.</p>
        </div>
      </div>

      {/* Filter bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {ALL_CATEGORIES.map(cat => (
            <button
              key={cat}
              onClick={() => setCategory(cat)}
              style={{
                padding: '4px 12px',
                borderRadius: 6,
                border: '1px solid var(--rule)',
                background: category === cat ? 'var(--fg-1)' : 'var(--surface)',
                color: category === cat ? 'var(--bg)' : 'var(--fg-2)',
                fontSize: 12.5,
                fontWeight: category === cat ? 600 : 400,
                cursor: 'pointer',
                textTransform: 'capitalize',
              }}
            >
              {cat === 'all' ? 'All' : cat}
            </button>
          ))}
        </div>
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search plugins…"
          style={{
            marginLeft: 'auto',
            padding: '5px 10px',
            borderRadius: 6,
            border: '1px solid var(--rule)',
            background: 'var(--surface)',
            color: 'var(--fg-1)',
            fontSize: 13,
            outline: 'none',
            minWidth: 180,
          }}
        />
      </div>

      {error && (
        <div className="card" style={{ borderColor: 'var(--bad)', marginBottom: 16 }}>
          <div className="card__body" style={{ color: 'var(--bad)', fontSize: 13 }}>
            Failed to load plugins: {error}
          </div>
        </div>
      )}

      {loading && (
        <div className="card">
          <div className="card__body" style={{ color: 'var(--fg-3)', fontSize: 13, padding: '24px 20px' }}>
            Loading plugins…
          </div>
        </div>
      )}

      {!loading && !error && filtered.length === 0 && (
        <div className="card">
          <div
            className="card__body"
            style={{ textAlign: 'center', padding: '48px 20px', color: 'var(--fg-3)' }}
          >
            <div style={{ fontSize: 13, color: 'var(--fg-2)', marginBottom: 6 }}>
              No plugins available
            </div>
            <div style={{ fontSize: 12.5 }}>
              Check back later or contact your admin.
            </div>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {filtered.map(plugin => {
          const isExpanded = expandedId === plugin.id;
          const firstParty = isFirstParty(plugin.author);
          return (
            <div
              key={plugin.id}
              className="card"
              style={{
                border: isExpanded ? '1px solid var(--sc-blue, #0A7BD7)' : undefined,
              }}
            >
              <div className="card__head" style={{ alignItems: 'flex-start' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {/* Row 1: name + slug + category badge */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <h3 className="card__title" style={{ margin: 0, fontWeight: 700 }}>
                      {plugin.name}
                    </h3>
                    <span
                      className="mono"
                      style={{ fontSize: 11.5, color: 'var(--fg-3)' }}
                    >
                      {plugin.slug}
                    </span>
                    <span
                      style={{
                        display: 'inline-block',
                        padding: '2px 8px',
                        borderRadius: 4,
                        fontSize: 11.5,
                        fontWeight: 600,
                        background: CATEGORY_BG[plugin.category],
                        color: CATEGORY_COLORS[plugin.category],
                        textTransform: 'capitalize',
                      }}
                    >
                      {plugin.category}
                    </span>
                  </div>

                  {/* Row 2: version + author + scopes */}
                  <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span
                      className="mono"
                      style={{ fontSize: 11.5, color: 'var(--fg-3)' }}
                    >
                      v{plugin.version}
                    </span>
                    <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>·</span>
                    <span style={{ fontSize: 12, color: firstParty ? 'var(--good, #1f8a5b)' : 'var(--fg-3)' }}>
                      {firstParty ? '✓ ' : ''}{plugin.author}
                    </span>
                    {plugin.scopes.length > 0 ? (
                      <>
                        <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>·</span>
                        {plugin.scopes.map(scope => (
                          <span
                            key={scope}
                            className="mono"
                            style={{
                              padding: '1px 7px',
                              borderRadius: 4,
                              fontSize: 11,
                              background: 'var(--surface-soft)',
                              color: 'var(--fg-3)',
                              border: '1px solid var(--rule)',
                            }}
                          >
                            {scope}
                          </span>
                        ))}
                      </>
                    ) : (
                      <>
                        <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>·</span>
                        <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>No special scopes</span>
                      </>
                    )}
                  </div>

                  {/* Row 3: description (truncated) */}
                  {plugin.description && (
                    <div
                      style={{
                        marginTop: 6,
                        fontSize: 12.5,
                        color: 'var(--fg-2)',
                        lineHeight: 1.5,
                        overflow: 'hidden',
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                      }}
                    >
                      {plugin.description}
                    </div>
                  )}
                </div>

                <div className="card__actions">
                  <button
                    className="btn btn--sm"
                    onClick={() => handleExpand(plugin.id)}
                  >
                    {isExpanded ? '▼ Hide details' : '▶ Show details'}
                  </button>
                </div>
              </div>

              {isExpanded && (
                <div className="card__body">
                  {loadedIds.has(plugin.id) && (
                    <PluginDetailPanel pluginId={plugin.id} />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </main>
  );
}
