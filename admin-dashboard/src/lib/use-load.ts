import { useCallback, useEffect, useState } from 'react';

export type Loaded<T> =
  | { status: 'loading'; data?: undefined; error?: undefined }
  | { status: 'ready'; data: T; error?: undefined }
  | { status: 'error'; data?: undefined; error: Error };

/**
 * Runs `loader` when `key` changes (e.g. the filters as a string) and on `reload()`. Results of
 * an outdated request are ignored, so quick filter changes cannot show stale data. A reload
 * keeps the current data visible until the new data arrives.
 */
export function useLoad<T>(loader: () => Promise<T>, key: string) {
  const [state, setState] = useState<{ key: string; attempt: number; value: Loaded<T> } | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    loader().then(
      (data) => current && setState({ key, attempt, value: { status: 'ready', data } }),
      (error: unknown) =>
        current &&
        setState({ key, attempt, value: { status: 'error', error: error instanceof Error ? error : new Error(String(error)) } }),
    );
    return () => {
      current = false;
    };
    // `loader` is recreated every render; `key` and `attempt` say when to load again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  // While reloading the same key, keep showing what is on screen (no flash, open views stay
  // open); a new key (other filters, another record) shows loading.
  const value: Loaded<T> =
    state && state.key === key && (state.attempt === attempt || state.value.status === 'ready')
      ? state.value
      : { status: 'loading' };
  return { ...value, reload };
}
