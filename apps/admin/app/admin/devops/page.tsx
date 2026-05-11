'use client';

import { useState, useRef, useEffect } from 'react';
import { getAdminToken } from '../../../lib/adminAuth';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface ToolCall {
  tool: string;
  args: Record<string, unknown>;
  elapsed_ms: number;
  result_preview: string;
}

interface AgentResponse {
  reply: string;
  tool_log: ToolCall[];
}

const SUGGESTED = [
  { label: 'Full health check', prompt: 'Run a full health check of the gateway and summarise any issues.' },
  { label: 'Error analysis', prompt: 'Show me recent API errors. What patterns do you see and what should I fix?' },
  { label: 'Budget overview', prompt: 'Which teams are close to or over their monthly budget?' },
  { label: 'Top spending teams', prompt: 'Show me the top teams by spend this month and their cache efficiency.' },
  { label: 'Model usage', prompt: 'What models are being used most over the last 7 days? Any wasteful usage?' },
  { label: 'Optimisation tips', prompt: 'Analyse the gateway and give me 3 concrete optimisation recommendations.' },
];

const TOOL_ICONS: Record<string, string> = {
  check_service_health: '🩺',
  get_gateway_metrics: '📊',
  get_recent_errors: '🚨',
  get_budget_status: '💰',
  get_model_usage: '🤖',
  get_audit_log: '📋',
  get_top_teams_by_spend: '🏆',
};

function ToolCallBadge({ call }: { call: ToolCall }) {
  const [expanded, setExpanded] = useState(false);
  const icon = TOOL_ICONS[call.tool] ?? '🔧';
  const argsStr = Object.keys(call.args).length
    ? Object.entries(call.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')
    : '';

  return (
    <div
      style={{
        margin: '4px 0',
        padding: '6px 10px',
        background: 'rgba(255,255,255,0.04)',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: 8,
        fontSize: 12,
        cursor: 'pointer',
        userSelect: 'none',
      }}
      onClick={() => setExpanded(v => !v)}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--side-fg-mute, #8b8fa8)' }}>
        <span>{icon}</span>
        <span style={{ fontFamily: 'monospace', color: 'var(--sc-blue, #0A7BD7)' }}>{call.tool}</span>
        {argsStr && <span style={{ opacity: 0.7 }}>({argsStr})</span>}
        <span style={{ marginLeft: 'auto' }}>{call.elapsed_ms}ms</span>
        <span>{expanded ? '▴' : '▾'}</span>
      </div>
      {expanded && (
        <div style={{ marginTop: 6, color: 'var(--side-fg, #c8cad8)', fontFamily: 'monospace', fontSize: 11.5, wordBreak: 'break-word' }}>
          {call.result_preview}
        </div>
      )}
    </div>
  );
}

function AssistantMessage({ content, toolLog }: { content: string; toolLog: ToolCall[] }) {
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', maxWidth: 820 }}>
      <div style={{
        width: 30, height: 30, borderRadius: '50%', flexShrink: 0,
        background: 'rgba(10,123,215,0.2)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 14, marginTop: 2,
      }}>
        ✦
      </div>
      <div style={{ flex: 1 }}>
        {toolLog.length > 0 && (
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 11, color: 'var(--side-fg-mute, #8b8fa8)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Tools used
            </div>
            {toolLog.map((tc, i) => <ToolCallBadge key={i} call={tc} />)}
          </div>
        )}
        <div style={{
          background: 'rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 10,
          padding: '12px 16px',
          fontSize: 13.5,
          lineHeight: 1.7,
          color: 'var(--side-fg, #e8eaf0)',
          whiteSpace: 'pre-wrap',
        }}>
          {content}
        </div>
      </div>
    </div>
  );
}

export default function DevOpsAgentPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [toolLogMap, setToolLogMap] = useState<Record<number, ToolCall[]>>({});
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  async function send(text: string) {
    const userMsg: Message = { role: 'user', content: text };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput('');
    setLoading(true);

    const assistantIndex = nextMessages.length; // index the assistant reply will occupy

    try {
      const token = getAdminToken();
      const res = await fetch(`${ADMIN_API}/devops-agent/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ messages: nextMessages }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `Error ${res.status}`);
      }

      const data: AgentResponse = await res.json();
      const assistantMsg: Message = { role: 'assistant', content: data.reply };
      setMessages([...nextMessages, assistantMsg]);
      if (data.tool_log?.length) {
        setToolLogMap(prev => ({ ...prev, [assistantIndex]: data.tool_log }));
      }
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Unknown error';
      setMessages([...nextMessages, {
        role: 'assistant',
        content: `Sorry, I couldn't complete the request: ${errMsg}`,
      }]);
    } finally {
      setLoading(false);
    }
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (input.trim() && !loading) send(input.trim());
    }
  }

  const isEmpty = messages.length === 0;

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100%',
      background: 'var(--bg, #0f1117)',
      color: 'var(--side-fg, #e8eaf0)',
    }}>
      {/* Header */}
      <div style={{
        padding: '18px 28px 14px',
        borderBottom: '1px solid var(--side-rule, rgba(255,255,255,0.08))',
        display: 'flex', alignItems: 'center', gap: 14, flexShrink: 0,
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: 10,
          background: 'rgba(10,123,215,0.2)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 18,
        }}>✦</div>
        <div>
          <div style={{ fontWeight: 700, fontSize: 16 }}>DevOps Agent</div>
          <div style={{ fontSize: 12, color: 'var(--side-fg-mute, #8b8fa8)', marginTop: 1 }}>
            Inspects and troubleshoots the AI Gateway using live data · Direct LLM connection (bypasses proxy)
          </div>
        </div>
        {loading && (
          <div style={{
            marginLeft: 'auto', fontSize: 12,
            color: 'var(--sc-blue, #0A7BD7)',
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <span style={{ animation: 'pulse 1.2s infinite' }}>◉</span> Agent thinking…
          </div>
        )}
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        {isEmpty && !loading && (
          <div style={{ maxWidth: 700 }}>
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 6 }}>Gateway DevOps Assistant</div>
              <div style={{ fontSize: 14, color: 'var(--side-fg-mute, #8b8fa8)', lineHeight: 1.6 }}>
                I can inspect live gateway data, analyse errors, check service health, review budgets,
                and give concrete optimisation recommendations. I call tools directly — not through the proxy.
              </div>
            </div>

            <div style={{ fontSize: 12, color: 'var(--side-fg-mute, #8b8fa8)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Suggested tasks
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {SUGGESTED.map(s => (
                <button
                  key={s.label}
                  onClick={() => send(s.prompt)}
                  style={{
                    padding: '10px 14px',
                    background: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 10,
                    cursor: 'pointer',
                    textAlign: 'left',
                    color: 'var(--side-fg, #e8eaf0)',
                    fontFamily: 'inherit',
                    fontSize: 13,
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.08)'; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.04)'; }}
                >
                  <div style={{ fontWeight: 500, marginBottom: 3 }}>{s.label}</div>
                  <div style={{ fontSize: 11.5, color: 'var(--side-fg-mute, #8b8fa8)', lineHeight: 1.4 }}>{s.prompt}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => {
          if (m.role === 'user') {
            return (
              <div key={i} style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <div style={{
                  maxWidth: 600,
                  padding: '10px 14px',
                  background: 'var(--sc-blue, #0A7BD7)',
                  borderRadius: '12px 12px 2px 12px',
                  fontSize: 13.5, lineHeight: 1.6,
                  color: '#fff',
                  whiteSpace: 'pre-wrap',
                }}>
                  {m.content}
                </div>
              </div>
            );
          }
          return (
            <AssistantMessage key={i} content={m.content} toolLog={toolLogMap[i] ?? []} />
          );
        })}

        {loading && (
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
            <div style={{
              width: 30, height: 30, borderRadius: '50%', flexShrink: 0,
              background: 'rgba(10,123,215,0.2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14,
            }}>✦</div>
            <div style={{
              padding: '10px 14px', fontSize: 13.5,
              color: 'var(--side-fg-mute, #8b8fa8)', fontStyle: 'italic',
            }}>
              Querying gateway data…
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: '14px 28px 20px',
        borderTop: '1px solid var(--side-rule, rgba(255,255,255,0.08))',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', maxWidth: 820 }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about gateway health, errors, budgets, usage… (Enter to send, Shift+Enter for newline)"
            rows={2}
            disabled={loading}
            style={{
              flex: 1, resize: 'none',
              border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: 10, padding: '10px 14px',
              fontSize: 13.5, fontFamily: 'inherit',
              background: 'rgba(255,255,255,0.05)',
              color: 'var(--side-fg, #e8eaf0)',
              outline: 'none', lineHeight: 1.5,
              maxHeight: 140, overflowY: 'auto',
            }}
          />
          <button
            onClick={() => { if (input.trim() && !loading) send(input.trim()); }}
            disabled={loading || !input.trim()}
            style={{
              padding: '10px 20px',
              background: 'var(--sc-blue, #0A7BD7)',
              color: '#fff', border: 'none', borderRadius: 10,
              cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
              fontSize: 13.5, fontFamily: 'inherit', fontWeight: 500,
              opacity: loading || !input.trim() ? 0.5 : 1,
              flexShrink: 0,
              transition: 'opacity 0.15s',
            }}
          >
            Send
          </button>
        </div>
        <div style={{ fontSize: 11, color: 'var(--side-fg-mute, #8b8fa8)', marginTop: 8, maxWidth: 820 }}>
          This agent has read-only access to live gateway data. It cannot modify configuration or restart services.
        </div>
      </div>
    </div>
  );
}
