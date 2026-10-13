import { useCallback, useEffect, useState } from 'react';

import { ApiError } from '@/lib/api';
import { searchVehicles } from '@/services/vehicles';
import type { MarketplaceVehicle, SearchFilters } from '@/types/vehicle';

interface Page {
  key: string;
  items: MarketplaceVehicle[];
  total: number;
  error?: ApiError;
}

function toApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError('Something went wrong.', 0, 'unknown');
}

/**
 * Paginated marketplace search. A new filter set starts a fresh search; responses for an
 * older filter set are ignored, so fast typing never shows stale results.
 */
export function useVehicleSearch(filters: SearchFilters) {
  const key = JSON.stringify(filters);
  const [page, setPage] = useState<Page | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    searchVehicles(JSON.parse(key) as SearchFilters).then(
      (result) => !cancelled && setPage({ key, items: result.items, total: result.total }),
      (error: unknown) => !cancelled && setPage({ key, items: [], total: 0, error: toApiError(error) }),
    );
    return () => {
      cancelled = true;
    };
  }, [key]);

  const current = page?.key === key ? page : null;

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const result = await searchVehicles(JSON.parse(key) as SearchFilters);
      setPage({ key, items: result.items, total: result.total });
    } catch (error) {
      setPage({ key, items: [], total: 0, error: toApiError(error) });
    } finally {
      setRefreshing(false);
    }
  }, [key]);

  const loadMore = useCallback(async () => {
    if (!current || current.error || loadingMore || current.items.length >= current.total) return;
    setLoadingMore(true);
    try {
      const result = await searchVehicles(JSON.parse(key) as SearchFilters, current.items.length);
      setPage((prev) =>
        prev && prev.key === key
          ? { ...prev, items: [...prev.items, ...result.items], total: result.total }
          : prev,
      );
    } catch {
      // Keep what is already shown; the next scroll to the end retries.
    } finally {
      setLoadingMore(false);
    }
  }, [current, key, loadingMore]);

  return {
    status: current ? (current.error ? 'error' : 'success') : 'loading',
    items: current?.items ?? [],
    total: current?.total ?? 0,
    error: current?.error,
    loadingMore,
    refreshing,
    refresh,
    loadMore,
  } as const;
}
