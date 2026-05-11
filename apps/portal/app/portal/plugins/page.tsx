'use client';

import { useState, useEffect, useCallback } from 'react';

const BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? 'http://localhost:8005';

// ---------------------------------------------------------------------------
// Plugins tab types
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Copilot Catalog tab types
// ---------------------------------------------------------------------------

type CopilotKind = 'agent' | 'instruction' | 'recipe';

interface CopilotItem {
  id: string;
  name: string;
  kind: CopilotKind;
  description: string | null;
  content_preview: string | null;
  github_url: string | null;
  tags: string[];
}

interface CopilotMeta {
  count: number;
  last_synced: string | null;
}

// ---------------------------------------------------------------------------
// Shared style constants
// ---------------------------------------------------------------------------

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

const KIND_COLORS: Record<CopilotKind, string> = {
  agent:       '#1a6bbf',
  instruction: '#6b3fa0',
  recipe:      '#b85c00',
};

const KIND_BG: Record<CopilotKind, string> = {
  agent:       '#dbeafe',
  instruction: '#ede9fe',
  recipe:      '#fed7aa',
};

const ALL_CATEGORIES: Array<Plugin['category'] | 'all'> = [
  'all', 'tool', 'integration', 'data', 'security', 'workflow',
];

const ALL_KINDS: Array<CopilotKind | 'all'> = ['all', 'agent', 'instruction', 'recipe'];

const SCOPE_ICONS: Record<string, string> = {
  internet:   '\u{1F310}',
  compute:    '\u{1F4BB}',
  files:      '\u{1F4C1}',
  github:     '\u{1F527}',
  jira:       '\u{1F527}',
  confluence: '\u{1F527}',
  slack:      '\u{1F527}',
  database:   '\u{1F5C4}\u{FE0F}',
};

function scopeIcon(scope: string): string {
  const lower = scope.toLowerCase();
  for (const [key, icon] of Object.entries(SCOPE_ICONS)) {
    if (lower.includes(key)) return icon;
  }
  return '\u{1F511}';
}

function isFirstParty(author: string): boolean {
  const lower = author.toLowerCase();
  return lower.includes('simcorp') || lower === 'internal';
}

function relativeTime(isoString: string | null): string {
  if (!isoString) return 'never';
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH}h ago`;
  const diffD = Math.floor(diffH / 24);
  return `${diffD}d ago`;
}

// ---------------------------------------------------------------------------
// Plugin detail panel
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Plugins tab content
// ---------------------------------------------------------------------------

function PluginsTab() {
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
    <>
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
    </>
  );
}

// ---------------------------------------------------------------------------
// Copilot Catalog tab content
// ---------------------------------------------------------------------------

function CopilotCatalogTab() {
  const [items, setItems] = useState<CopilotItem[]>([]);
  const [meta, setMeta] = useState<CopilotMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [searchPending, setSearchPending] = useState('');
  const [kind, setKind] = useState<CopilotKind | 'all'>('all');
  const [copied, setCopied] = useState<string | null>(null);

  const fetchItems = useCallback((q: string, k: CopilotKind | 'all') => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (q.trim()) {
      params.set('q', q.trim());
      params.set('limit', '20');
    } else {
      params.set('limit', '50');
    }
    if (k !== 'all') params.set('kind', k);

    fetch(`${BASE}/mcp/copilot-catalog/items?${params.toString()}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<{ items: CopilotItem[] }>;
      })
      .then(data => setItems(Array.isArray(data.items) ? data.items : []))
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  // Initial load: fetch items + meta
  useEffect(() => {
    fetchItems('', 'all');
    fetch(`${BASE}/mcp/copilot-catalog/meta`)
      .then(r => r.ok ? r.json() as Promise<CopilotMeta> : Promise.reject(`HTTP ${r.status}`))
      .then(data => setMeta(data))
      .catch(() => setMeta(null));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounced search: fire 400ms after user stops typing
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchItems(searchPending, kind);
      setSearch(searchPending);
    }, 400);
    return () => clearTimeout(timer);
  }, [searchPending, kind, fetchItems]);

  const handleCopy = (item: CopilotItem) => {
    const text = item.content_preview ?? item.description ?? item.name;
    navigator.clipboard.writeText(text).then(() => {
      setCopied(item.id);
      setTimeout(() => setCopied(null), 2000);
    });
  };

  return (
    <>
      {/* Catalog meta bar */}
      {meta && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 16,
          fontSize: 12.5,
          color: 'var(--fg-3)',
        }}>
          <span style={{
            display: 'inline-block',
            background: 'var(--surface)',
            border: '1px solid var(--rule)',
            borderRadius: 6,
            padding: '3px 10px',
            fontWeight: 500,
            color: 'var(--fg-2)',
          }}>
            {meta.count.toLocaleString()} items
          </span>
          <span>·</span>
          <span>last synced {relativeTime(meta.last_synced)}</span>
        </div>
      )}

      {/* Filter bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 4 }}>
          {ALL_KINDS.map(k => (
            <button
              key={k}
              onClick={() => setKind(k)}
              style={{
                padding: '4px 12px',
                borderRadius: 6,
                border: '1px solid var(--rule)',
                background: kind === k ? 'var(--fg-1)' : 'var(--surface)',
                color: kind === k ? 'var(--bg)' : 'var(--fg-2)',
                fontSize: 12.5,
                fontWeight: kind === k ? 600 : 400,
                cursor: 'pointer',
                textTransform: 'capitalize',
              }}
            >
              {k === 'all' ? 'All' : k === 'agent' ? 'Agents' : k === 'instruction' ? 'Instructions' : 'Recipes'}
            </button>
          ))}
        </div>
        <input
          type="text"
          value={searchPending}
          onChange={e => setSearchPending(e.target.value)}
          placeholder="Search catalog…"
          style={{
            marginLeft: 'auto',
            padding: '5px 10px',
            borderRadius: 6,
            border: '1px solid var(--rule)',
            background: 'var(--surface)',
            color: 'var(--fg-1)',
            fontSize: 13,
            outline: 'none',
            minWidth: 200,
          }}
        />
      </div>

      {/* Error state */}
      {error && (
        <div className="card" style={{ borderColor: 'var(--bad)', marginBottom: 16 }}>
          <div className="card__body" style={{ color: 'var(--bad)', fontSize: 13 }}>
            Failed to load catalog: {error}
          </div>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="card">
          <div className="card__body" style={{ color: 'var(--fg-3)', fontSize: 13, padding: '24px 20px' }}>
            Loading catalog…
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && items.length === 0 && (
        <div className="card">
          <div className="card__body" style={{ textAlign: 'center', padding: '48px 20px', color: 'var(--fg-3)' }}>
            <div style={{ fontSize: 13, color: 'var(--fg-2)', marginBottom: 6 }}>
              No catalog items found
            </div>
            {search && (
              <div style={{ fontSize: 12.5 }}>
                Try a different search term or clear the filter.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Grid of item cards */}
      {!loading && items.length > 0 && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
          gap: 14,
        }}>
          {items.map(item => (
            <div
              key={item.id}
              className="card"
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 0,
              }}
            >
              <div className="card__head" style={{ alignItems: 'flex-start', paddingBottom: 8 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {/* Name + kind badge */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <h3 className="card__title" style={{ margin: 0, fontWeight: 700, fontSize: 14 }}>
                      {item.name}
                    </h3>
                    <span style={{
                      display: 'inline-block',
                      padding: '2px 8px',
                      borderRadius: 4,
                      fontSize: 11,
                      fontWeight: 600,
                      background: KIND_BG[item.kind],
                      color: KIND_COLORS[item.kind],
                      textTransform: 'capitalize',
                      flexShrink: 0,
                    }}>
                      {item.kind}
                    </span>
                  </div>
                </div>
              </div>

              {/* Description */}
              {item.description && (
                <div style={{
                  padding: '0 16px',
                  fontSize: 12.5,
                  color: 'var(--fg-2)',
                  lineHeight: 1.55,
                  overflow: 'hidden',
                  display: '-webkit-box',
                  WebkitLineClamp: 3,
                  WebkitBoxOrient: 'vertical',
                  marginBottom: 10,
                }}>
                  {item.description}
                </div>
              )}

              {/* Tags */}
              {item.tags && item.tags.length > 0 && (
                <div style={{
                  padding: '0 16px',
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: 4,
                  marginBottom: 12,
                }}>
                  {item.tags.slice(0, 6).map(tag => (
                    <span key={tag} style={{
                      padding: '2px 7px',
                      borderRadius: 4,
                      fontSize: 11,
                      background: 'var(--surface-soft, var(--surface))',
                      color: 'var(--fg-3)',
                      border: '1px solid var(--rule)',
                    }}>
                      {tag}
                    </span>
                  ))}
                  {item.tags.length > 6 && (
                    <span style={{ fontSize: 11, color: 'var(--fg-3)', alignSelf: 'center' }}>
                      +{item.tags.length - 6}
                    </span>
                  )}
                </div>
              )}

              {/* Footer: GitHub link + copy button */}
              <div style={{
                padding: '10px 16px',
                borderTop: '1px solid var(--rule)',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                marginTop: 'auto',
              }}>
                {item.github_url ? (
                  <a
                    href={item.github_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      fontSize: 12.5,
                      color: 'var(--accent, #0A7BD7)',
                      textDecoration: 'none',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                    }}
                  >
                    View on GitHub →
                  </a>
                ) : (
                  <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>No GitHub link</span>
                )}
                <button
                  onClick={() => handleCopy(item)}
                  style={{
                    marginLeft: 'auto',
                    padding: '4px 10px',
                    borderRadius: 5,
                    border: '1px solid var(--rule)',
                    background: copied === item.id ? 'var(--good-bg, #d1fae5)' : 'var(--surface)',
                    color: copied === item.id ? 'var(--good, #1f8a5b)' : 'var(--fg-2)',
                    fontSize: 12,
                    cursor: 'pointer',
                    transition: 'background 0.15s, color 0.15s',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {copied === item.id ? 'Copied!' : 'Copy'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Page root — tabbed layout
// ---------------------------------------------------------------------------

type TabId = 'plugins' | 'copilot';

const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'plugins',  label: 'Plugins' },
  { id: 'copilot',  label: 'Copilot Catalog' },
];

export default function PluginsPage() {
  const [activeTab, setActiveTab] = useState<TabId>('plugins');

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>Plugins &amp; Catalog</h1>
          <p>Browse first-party plugins and the Awesome Copilot community catalog.</p>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{
        display: 'flex',
        gap: 0,
        borderBottom: '1px solid var(--rule)',
        marginBottom: 24,
      }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '9px 20px',
              border: 'none',
              borderBottom: activeTab === tab.id
                ? '2px solid var(--accent, #0A7BD7)'
                : '2px solid transparent',
              background: 'transparent',
              color: activeTab === tab.id ? 'var(--fg-1)' : 'var(--fg-3)',
              fontSize: 13.5,
              fontWeight: activeTab === tab.id ? 600 : 400,
              cursor: 'pointer',
              marginBottom: '-1px',
              transition: 'color 0.15s',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'plugins'  && <PluginsTab />}
      {activeTab === 'copilot'  && <CopilotCatalogTab />}
    </main>
  );
}
