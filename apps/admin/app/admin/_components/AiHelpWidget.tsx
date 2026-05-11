'use client';

import { useState, useRef, useEffect } from 'react';
import { getAdminToken } from '../../../lib/adminAuth';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

const STARTERS = [
  'How do I set a team budget?',
  'Where do I manage guardrails?',
  'How do I revoke a developer API key?',
  'What does the audit log record?',
];

export default function AiHelpWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
      inputRef.current?.focus();
    }
  }, [open, messages]);

  async function send(text: string) {
    const userMsg: Message = { role: 'user', content: text };
    const next = [...messages, userMsg];
    setMessages(next);
    setInput('');
    setLoading(true);

    try {
      const token = getAdminToken();
      const res = await fetch(`${ADMIN_API}/ai-help/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ messages: next, context: 'admin' }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      setMessages([...next, { role: 'assistant', content: data.reply }]);
    } catch {
      setMessages([...next, { role: 'assistant', content: 'Sorry, I couldn\'t reach the AI backend right now. Try again in a moment.' }]);
    } finally {
      setLoading(false);
    }
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (input.trim()) send(input.trim());
    }
  }

  return (
    <>
      {/* Floating button */}
      <button
        onClick={() => setOpen(v => !v)}
        title="AI Help"
        style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 1000,
          width: 44, height: 44, borderRadius: '50%',
          background: 'var(--sc-blue, #0A7BD7)',
          border: 'none', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 2px 12px rgba(0,0,0,0.3)',
          color: '#fff', fontSize: 20,
          transition: 'transform 0.15s',
        }}
        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.transform = 'scale(1.08)'; }}
        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.transform = 'scale(1)'; }}
      >
        {open ? '✕' : '✦'}
      </button>

      {/* Chat panel */}
      {open && (
        <div style={{
          position: 'fixed', bottom: 80, right: 24, zIndex: 999,
          width: 360, maxHeight: '70vh',
          display: 'flex', flexDirection: 'column',
          background: 'var(--bg, #1a1f2e)',
          border: '1px solid var(--side-rule, rgba(255,255,255,0.1))',
          borderRadius: 12,
          boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
          overflow: 'hidden',
        }}>
          {/* Header */}
          <div style={{
            padding: '12px 16px',
            borderBottom: '1px solid var(--side-rule, rgba(255,255,255,0.1))',
            display: 'flex', alignItems: 'center', gap: 10,
            background: 'rgba(10,123,215,0.08)',
          }}>
            <span style={{ fontSize: 18 }}>✦</span>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13.5, color: 'var(--side-fg, #e8eaf0)' }}>Gateway Assistant</div>
              <div style={{ fontSize: 11.5, color: 'var(--side-fg-mute, #8b8fa8)' }}>Ask me anything about the admin portal</div>
            </div>
          </div>

          {/* Messages */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            {messages.length === 0 && (
              <div>
                <div style={{ fontSize: 12.5, color: 'var(--side-fg-mute, #8b8fa8)', marginBottom: 10 }}>
                  Quick questions:
                </div>
                {STARTERS.map(s => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    style={{
                      display: 'block', width: '100%', textAlign: 'left',
                      padding: '7px 10px', marginBottom: 4,
                      background: 'rgba(255,255,255,0.05)',
                      border: '1px solid var(--side-rule, rgba(255,255,255,0.1))',
                      borderRadius: 8, cursor: 'pointer',
                      fontSize: 12.5, color: 'var(--side-fg, #e8eaf0)',
                      fontFamily: 'inherit',
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} style={{
                display: 'flex',
                justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
              }}>
                <div style={{
                  maxWidth: '85%',
                  padding: '8px 12px',
                  borderRadius: m.role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
                  background: m.role === 'user'
                    ? 'var(--sc-blue, #0A7BD7)'
                    : 'rgba(255,255,255,0.07)',
                  color: m.role === 'user' ? '#fff' : 'var(--side-fg, #e8eaf0)',
                  fontSize: 13,
                  lineHeight: 1.5,
                  whiteSpace: 'pre-wrap',
                }}>
                  {m.content}
                </div>
              </div>
            ))}

            {loading && (
              <div style={{ color: 'var(--side-fg-mute, #8b8fa8)', fontSize: 13, fontStyle: 'italic' }}>
                Thinking…
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div style={{
            padding: '10px 12px',
            borderTop: '1px solid var(--side-rule, rgba(255,255,255,0.1))',
            display: 'flex', gap: 8, alignItems: 'flex-end',
          }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="Ask a question… (Enter to send)"
              rows={1}
              disabled={loading}
              style={{
                flex: 1, resize: 'none',
                border: '1px solid var(--side-rule, rgba(255,255,255,0.1))',
                borderRadius: 8, padding: '7px 10px',
                fontSize: 13, fontFamily: 'inherit',
                background: 'rgba(255,255,255,0.05)',
                color: 'var(--side-fg, #e8eaf0)',
                outline: 'none', lineHeight: 1.4,
                maxHeight: 100, overflowY: 'auto',
              }}
            />
            <button
              onClick={() => { if (input.trim()) send(input.trim()); }}
              disabled={loading || !input.trim()}
              style={{
                padding: '7px 14px',
                background: 'var(--sc-blue, #0A7BD7)',
                color: '#fff', border: 'none', borderRadius: 8,
                cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
                fontSize: 13, fontFamily: 'inherit',
                opacity: loading || !input.trim() ? 0.5 : 1,
                flexShrink: 0,
              }}
            >
              Send
            </button>
          </div>
        </div>
      )}
    </>
  );
}
