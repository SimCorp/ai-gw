import { useEffect, useRef, useState, useCallback } from "react";

export type StreamStatus = "connecting" | "open" | "error";

export interface UseStreamResult<T> {
  events: T[];
  status: StreamStatus;
  clear: () => void;
}

const BACKOFF_BASE_MS = 100;
const BACKOFF_MAX_MS = 30_000;

/**
 * Hook for consuming Server-Sent Events with automatic exponential-backoff
 * reconnection on error/close.
 *
 * @param url     Full URL of the SSE endpoint.
 * @param enabled When false the stream is paused (no new events are buffered
 *                and the EventSource is closed). Resuming re-opens the stream.
 */
export function useStream<T = unknown>(
  url: string,
  enabled = true
): UseStreamResult<T> {
  const [events, setEvents] = useState<T[]>([]);
  const [status, setStatus] = useState<StreamStatus>("connecting");

  const esRef = useRef<EventSource | null>(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  const enabledRef = useRef(enabled);

  // Keep a stable ref to the latest enabled value to avoid stale closure in retry
  enabledRef.current = enabled;

  const clear = useCallback(() => setEvents([]), []);

  useEffect(() => {
    mountedRef.current = true;

    function connect(): void {
      if (!mountedRef.current || !enabledRef.current) return;

      setStatus("connecting");
      const es = new EventSource(url);
      esRef.current = es;

      es.addEventListener("open", () => {
        if (!mountedRef.current) return;
        retryCountRef.current = 0;
        setStatus("open");
      });

      es.addEventListener("message", (event: MessageEvent<string>) => {
        if (!mountedRef.current) return;
        try {
          const parsed = JSON.parse(event.data) as T;
          setEvents((prev) => [...prev, parsed]);
        } catch {
          // Ignore malformed events
        }
      });

      es.addEventListener("error", () => {
        if (!mountedRef.current) return;
        es.close();
        esRef.current = null;
        setStatus("error");

        // Exponential backoff: 100ms, 200ms, 400ms … capped at 30s
        const delay = Math.min(
          BACKOFF_BASE_MS * Math.pow(2, retryCountRef.current),
          BACKOFF_MAX_MS
        );
        retryCountRef.current += 1;

        retryTimerRef.current = setTimeout(() => {
          if (mountedRef.current && enabledRef.current) connect();
        }, delay);
      });
    }

    if (enabled) {
      connect();
    } else {
      // Pause: close any open connection
      if (retryTimerRef.current !== null) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
      setStatus("connecting"); // reset so re-enable shows "connecting" first
    }

    return () => {
      mountedRef.current = false;
      if (retryTimerRef.current !== null) {
        clearTimeout(retryTimerRef.current);
      }
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, [url, enabled]);

  return { events, status, clear };
}
