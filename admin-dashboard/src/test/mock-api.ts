import { vi } from 'vitest';

type Handler = (body: unknown, url: URL) => { status?: number; json?: unknown; blob?: Blob };

/**
 * Replaces fetch with a table of "METHOD /path" → handler (path without /api/v1 and query).
 * Unknown requests fail the test loudly. Returns the list of calls made.
 */
export function mockApi(routes: Record<string, Handler | object>) {
  const calls: { method: string; path: string; query: URLSearchParams; body: unknown; auth: string | null }[] = [];
  const fetchMock = vi.fn(async (input: string, init: RequestInit = {}) => {
    const url = new URL(input);
    const path = url.pathname.replace(/^\/api\/v1/, '');
    const method = init.method ?? 'GET';
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : undefined;
    const headers = (init.headers ?? {}) as Record<string, string>;
    calls.push({ method, path, query: url.searchParams, body, auth: headers.Authorization ?? null });
    const route = routes[`${method} ${path}`];
    if (route === undefined) throw new Error(`Unexpected request ${method} ${path}`);
    const result = typeof route === 'function' ? (route as Handler)(body, url) : { json: route };
    const status = result.status ?? 200;
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => result.json,
      blob: async () => result.blob ?? new Blob(),
    } as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
  return calls;
}

export const ADMIN_ME = { id: 'admin-1', email: 'admin@example.com', full_name: 'Platform Admin', roles: ['ADMIN'] };
export const TOKENS = { access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer', expires_in: 900 };

/** A response with a status code (plain objects in `mockApi` routes are 200 JSON bodies). */
export const reply = (status: number, json: unknown = {}) => () => ({ status, json });
