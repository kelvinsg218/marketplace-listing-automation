"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";

/** GET with loading/error state; re-runs when the path changes (e.g. switching organization). null path = idle. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!path) return;
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    api<T>(path, { signal: ctrl.signal })
      .then((d) => { setData(d); setLoading(false); })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        setError(err instanceof ApiError ? err.message : "Falha ao carregar.");
        setLoading(false);
      });
    return () => ctrl.abort();
  }, [path, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload, setData };
}
