import { useCallback, useEffect, useState } from 'react';

export type AsyncState<T> =
  | { status: 'loading'; data?: undefined; error?: undefined }
  | { status: 'success'; data: T; error?: undefined }
  | { status: 'error'; data?: undefined; error: Error };

interface Settled<T> {
  loader: () => Promise<T>;
  attempt: number;
  state: AsyncState<T>;
}

/**
 * Runs an async loader and tracks loading / success / error state.
 * `loader` must be stable (module function or useCallback); a new loader
 * triggers a new request. `reload` re-runs it (retry, pull-to-refresh).
 */
export function useAsync<T>(loader: () => Promise<T>) {
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);

  useEffect(() => {
    let cancelled = false;
    const settle = (state: AsyncState<T>) => {
      if (!cancelled) setSettled({ loader, attempt, state });
    };
    loader().then(
      (data) => settle({ status: 'success', data }),
      (error: unknown) =>
        settle({
          status: 'error',
          error: error instanceof Error ? error : new Error('Something went wrong.'),
        }),
    );
    return () => {
      cancelled = true;
    };
  }, [loader, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  // A result only counts if it belongs to the current request; otherwise we are loading.
  const isCurrent = settled?.loader === loader && settled.attempt === attempt;
  const state: AsyncState<T> = isCurrent ? settled.state : { status: 'loading' };

  return { ...state, reload };
}
