import { useSearchParams } from 'react-router';

/** List filters and the page offset kept in the URL, so links and reloads keep them. */
export function useFilters<K extends string>(keys: readonly K[]) {
  const [params, setParams] = useSearchParams();
  const values = Object.fromEntries(keys.map((k) => [k, params.get(k) ?? ''])) as Record<K, string>;
  const offset = Number(params.get('offset') ?? 0) || 0;

  const set = (key: K, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('offset'); // a new filter starts at the first page
    setParams(next, { replace: true });
  };
  const setOffset = (value: number) => {
    const next = new URLSearchParams(params);
    if (value) next.set('offset', String(value));
    else next.delete('offset');
    setParams(next);
  };
  return { values, offset, set, setOffset, key: params.toString() };
}
