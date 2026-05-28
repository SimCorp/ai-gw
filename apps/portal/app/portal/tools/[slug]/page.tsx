'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useAuth } from '../../_lib/authContext';

const BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? 'http://localhost:8005';

interface Tool {
  tool_id: string;
  label: string;
  category: string;
  enabled: boolean;
}

export default function ToolPage({ params }: { params: { slug: string } }) {
  const { token } = useAuth();
  const [tool, setTool] = useState<Tool | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    fetch(`${BASE}/tools?enabled_only=true`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then((data: Tool[]) => {
        const found = data.find(t => t.tool_id === params.slug);
        if (found) setTool(found);
        else setNotFound(true);
      })
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [token, params.slug]);

  if (loading) {
    return (
      <main className="pmain">
        <p style={{ color: 'var(--fg-mute)' }}>Loading…</p>
      </main>
    );
  }

  if (notFound) {
    return (
      <main className="pmain">
        <div className="phero">
          <h1 className="phero__title">Tool not found</h1>
          <p className="phero__sub">This tool may be disabled or the link is incorrect.</p>
        </div>
        <Link href="/portal/tools" className="btn">← Back to Tools</Link>
      </main>
    );
  }

  return (
    <main className="pmain" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexShrink: 0 }}>
        <Link href="/portal/tools" style={{ color: 'var(--fg-mute)', textDecoration: 'none', fontSize: 13 }}>
          ← Tools
        </Link>
        {tool && (
          <>
            <span style={{ color: 'var(--border)' }}>/</span>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg)' }}>{tool.label}</span>
            <span style={{
              padding: '2px 8px', borderRadius: 20, fontSize: 11,
              background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--fg-mute)',
            }}>
              {tool.category}
            </span>
          </>
        )}
      </div>
      <iframe
        src={`/tools-app/${params.slug}`}
        title={tool?.label ?? params.slug}
        style={{
          flex: 1, border: 'none', borderRadius: 8,
          background: '#fff', minHeight: 600,
        }}
      />
    </main>
  );
}
