'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { useAuth } from '../_lib/authContext';

const BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? 'http://localhost:8005';

interface Tool {
  tool_id: string;
  label: string;
  category: string;
  enabled: boolean;
}

const CATEGORY_EMOJI: Record<string, string> = {
  'Crypto':          '🔐',
  'Converter':       '🔄',
  'Web':             '🌐',
  'Images & Videos': '🖼️',
  'Development':     '💻',
  'Network':         '📡',
  'Math':            '🧮',
  'Measurement':     '📏',
  'Text':            '📝',
  'Data':            '📊',
  'Time & Date':     '🕐',
  'Random':          '🎲',
};

export default function ToolsPage() {
  const { token } = useAuth();
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState('All');

  useEffect(() => {
    if (!token) return;
    fetch(`${BASE}/tools?enabled_only=true`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(data => { setTools(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, [token]);

  const categories = useMemo(() => {
    const cats = Array.from(new Set(tools.map(t => t.category))).sort();
    return ['All', ...cats];
  }, [tools]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return tools.filter(t => {
      const matchesSearch = !q || t.label.toLowerCase().includes(q) || t.category.toLowerCase().includes(q);
      const matchesCategory = activeCategory === 'All' || t.category === activeCategory;
      return matchesSearch && matchesCategory;
    });
  }, [tools, search, activeCategory]);

  return (
    <main className="pmain">
      <div className="phero">
        <h1 className="phero__title">Developer Tools</h1>
        <p className="phero__sub">Utilities for everyday development tasks — {tools.length} tools available</p>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          type="search"
          placeholder="Search tools…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            flex: '1 1 220px', maxWidth: 340, padding: '8px 12px',
            background: 'var(--surface)', border: '1px solid var(--rule)',
            borderRadius: 6, color: 'var(--fg-1)', fontSize: 14,
          }}
        />
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {categories.map(cat => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              style={{
                padding: '5px 12px', borderRadius: 20, fontSize: 13, cursor: 'pointer',
                border: '1px solid var(--rule)',
                background: activeCategory === cat ? 'var(--accent)' : 'var(--surface)',
                color: activeCategory === cat ? 'var(--accent-fg)' : 'var(--fg-2)',
                fontFamily: 'inherit',
              }}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {loading && <p style={{ color: 'var(--fg-2)' }}>Loading tools…</p>}

      {!loading && filtered.length === 0 && (
        <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--fg-2)' }}>
          <p style={{ fontSize: 16 }}>No tools match your search.</p>
          <button
            onClick={() => { setSearch(''); setActiveCategory('All'); }}
            style={{ marginTop: 8, background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 14 }}
          >
            Clear filters
          </button>
        </div>
      )}

      {!loading && filtered.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
          {filtered.map(tool => (
            <Link
              key={tool.tool_id}
              href={`/portal/tools/${tool.tool_id}`}
              style={{ textDecoration: 'none' }}
            >
              <div
                className="card"
                style={{ padding: '14px 16px', cursor: 'pointer', height: '100%' }}
              >
                <div style={{ fontSize: 20, marginBottom: 8 }}>
                  {CATEGORY_EMOJI[tool.category] ?? '🔧'}
                </div>
                <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4, color: 'var(--fg-1)' }}>
                  {tool.label}
                </div>
                <div style={{ fontSize: 12, color: 'var(--fg-2)' }}>
                  {tool.category}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
