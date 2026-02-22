import { useState, useEffect, useCallback } from "react";
import { useArchStore } from "../store";
import type { AdminSummary } from "../types";

interface UseAdminDataResult {
  data: AdminSummary | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useAdminData(): UseAdminDataResult {
  const { adminOpen, liveConfig } = useArchStore();
  const [data, setData] = useState<AdminSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetchCount, setFetchCount] = useState(0);

  const refetch = useCallback(() => {
    setFetchCount((c) => c + 1);
  }, []);

  useEffect(() => {
    if (!adminOpen || !liveConfig?.enabled) return;

    let cancelled = false;
    async function fetchData() {
      setLoading(true);
      setError(null);
      try {
        const url = `${liveConfig!.data_url}/admin-summary.json`;
        const res = await fetch(url);
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const json: AdminSummary = await res.json();
        if (!cancelled) {
          setData(json);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load admin data");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    fetchData();
    return () => { cancelled = true; };
  }, [adminOpen, liveConfig, fetchCount]);

  return { data, loading, error, refetch };
}
