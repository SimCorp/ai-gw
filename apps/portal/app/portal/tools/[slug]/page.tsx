'use client';

import { useState, useEffect, use } from 'react';
import Link from 'next/link';
import { useAuth } from '../../_lib/authContext';

const BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? 'http://localhost:8005';
const TOOLS_APP_BASE = process.env.NEXT_PUBLIC_TOOLS_APP_URL ?? '/tools-app';

interface Tool {
  tool_id: string;
  label: string;
  category: string;
  enabled: boolean;
}

export default function ToolPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
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
        const found = data.find(t => t.tool_id === slug);
        if (found) setTool(found);
        else setNotFound(true);
      })
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [token, slug]);

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
        src={`${TOOLS_APP_BASE}/${slug}`}
        title={tool?.label ?? slug}
        style={{
          flex: 1, border: 'none', borderRadius: 8,
          background: '#fff', minHeight: 600,
        }}
        onError={() => {/* handled by browser's native iframe error display */}}
      />
      <div style={{ padding: '10px 0', fontSize: 12, color: 'var(--fg-mute)', flexShrink: 0 }}>
        Having trouble? Access the tools app directly at{' '}
        <a
          href={`${TOOLS_APP_BASE}/${slug}`}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: 'var(--sc-link, #0A7BD7)' }}
        >
          {TOOLS_APP_BASE}/{slug} ↗
        </a>
      </div>
    </main>
  );
}
