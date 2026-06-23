'use client';

import React, { useState, useEffect, useRef } from 'react';
import { apiFetch } from '../../../../lib/apiClient';

interface UserResult {
  id: string;
  email: string;
  display_name: string;
}

interface UserSearchFieldProps {
  onSelect: (userId: string, email: string, displayName: string) => void;
  placeholder?: string;
  disabled?: boolean;
}

export function UserSearchField({ onSelect, placeholder = 'Search by email or name…', disabled }: UserSearchFieldProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<UserResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (query.trim().length < 2) { setResults([]); setOpen(false); return; }
    timerRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await apiFetch<{ total: number; items: UserResult[] }>(
          `/admin/users?search=${encodeURIComponent(query.trim())}&limit=10`
        );
        setResults(data.items ?? []);
        setOpen(true);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
  }, [query]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  function handleSelect(u: UserResult) {
    onSelect(u.id, u.email, u.display_name);
    setQuery('');
    setResults([]);
    setOpen(false);
  }

  return (
    <div ref={containerRef} style={{ position: 'relative' }}>
      <input
        type="text"
        value={query}
        onChange={e => setQuery(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        style={{
          width: '100%', boxSizing: 'border-box',
          padding: '7px 10px', fontSize: 13,
          background: 'var(--surface-2)', border: '1px solid var(--rule)',
          borderRadius: 6, color: 'var(--fg-1)', outline: 'none',
        }}
      />
      {open && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0,
          background: 'var(--surface)', border: '1px solid var(--rule)',
          borderRadius: 6, boxShadow: 'var(--shadow-pop)',
          zIndex: 200, marginTop: 2, maxHeight: 240, overflowY: 'auto',
        }}>
          {loading && (
            <div style={{ padding: '10px 12px', fontSize: 12, color: 'var(--fg-3)' }}>Searching…</div>
          )}
          {!loading && results.length === 0 && (
            <div style={{ padding: '10px 12px', fontSize: 12, color: 'var(--fg-3)' }}>No users found</div>
          )}
          {!loading && results.map((u, i) => (
            <div
              key={u.id}
              onClick={() => handleSelect(u)}
              style={{
                padding: '9px 12px', cursor: 'pointer',
                borderBottom: i < results.length - 1 ? '1px solid var(--rule)' : 'none',
                display: 'flex', flexDirection: 'column', gap: 2,
              }}
              onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)'}
              onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = ''}
            >
              <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--fg-1)' }}>
                {u.display_name || u.email}
              </span>
              {u.display_name && (
                <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>{u.email}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
