"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const listeners = new Set<() => void>();

/** Re-run every active query. Called after mutations so screens stay in sync. */
export function invalidateQueries() {
  listeners.forEach((fn) => fn());
}

export type QueryStatus = "loading" | "success" | "error";

export interface QueryResult<T> {
  data: T | undefined;
  status: QueryStatus;
  error: Error | null;
  /** Re-run the query. Existing data stays on screen while it reloads. */
  reload: () => void;
}

interface Options<T> {
  /** Return a delay in ms to poll again, or false to stop. */
  refetchInterval?: (data: T | undefined) => number | false;
  enabled?: boolean;
}

/**
 * Tiny data-fetching hook around the API abstraction. Intentionally minimal:
 * when the real backend arrives this can be swapped for TanStack Query
 * without touching screens, because they only use { data, status, reload }.
 */
export function useQuery<T>(key: string, fn: () => Promise<T>, options: Options<T> = {}): QueryResult<T> {
  const { refetchInterval, enabled = true } = options;
  const [data, setData] = useState<T | undefined>(undefined);
  const [status, setStatus] = useState<QueryStatus>("loading");
  const [error, setError] = useState<Error | null>(null);
  const [tick, setTick] = useState(0);

  const fnRef = useRef(fn);
  const intervalRef = useRef(refetchInterval);
  useEffect(() => {
    fnRef.current = fn;
    intervalRef.current = refetchInterval;
  });

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const run = async () => {
      try {
        const result = await fnRef.current();
        if (cancelled) return;
        setData(result);
        setError(null);
        setStatus("success");
        const next = intervalRef.current?.(result);
        if (next) timer = setTimeout(run, next);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e : new Error(String(e)));
        setStatus("error");
      }
    };
    void run();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [key, tick, enabled]);

  const reload = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    listeners.add(reload);
    return () => {
      listeners.delete(reload);
    };
  }, [reload]);

  return { data, status, error, reload };
}
