/**
 * HTTP client for the FastAPI backend, for administrators only.
 *
 * Session storage: the access token lives only in memory; the refresh token is kept in
 * sessionStorage so a page reload in the same tab stays signed in, and closing the tab ends
 * the session. On a 401 the client refreshes once (concurrent calls share one refresh) and
 * retries; if that fails, the session is cleared and listeners are told.
 */

export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/+$/, '');
const REFRESH_KEY = 'carhire.admin.refresh';
const TIMEOUT_MS = 20_000;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>[];

  constructor(message: string, status: number, code: string, details: Record<string, unknown>[] = []) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

export function buildUrl(path: string, params?: Query): string {
  const query = Object.entries(params ?? {})
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
  return `${API_URL}/api/v1${path}${query ? `?${query}` : ''}`;
}

let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;
const expiredListeners = new Set<() => void>();

function storedRefresh(): string | null {
  try {
    return sessionStorage.getItem(REFRESH_KEY);
  } catch {
    return null;
  }
}

function storeTokens(tokens: { access_token: string; refresh_token: string } | null) {
  accessToken = tokens?.access_token ?? null;
  try {
    if (tokens) sessionStorage.setItem(REFRESH_KEY, tokens.refresh_token);
    else sessionStorage.removeItem(REFRESH_KEY);
  } catch {
    // Storage blocked: the session simply does not survive a reload.
  }
}

export function onSessionExpired(listener: () => void): () => void {
  expiredListeners.add(listener);
  return () => expiredListeners.delete(listener);
}

async function send(method: string, path: string, init: { params?: Query; body?: unknown; token?: string | null }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (init.body !== undefined) headers['Content-Type'] = 'application/json';
  if (init.token) headers.Authorization = `Bearer ${init.token}`;
  try {
    return await fetch(buildUrl(path, init.params), {
      method,
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: controller.signal,
      credentials: 'omit',
    });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === 'AbortError';
    throw new ApiError(
      timedOut ? 'The server took too long to respond.' : 'Could not reach the server. Is the backend running?',
      0,
      timedOut ? 'timeout' : 'network_error',
    );
  } finally {
    clearTimeout(timer);
  }
}

async function toError(response: Response): Promise<ApiError> {
  try {
    const body = await response.json();
    return new ApiError(
      body?.error?.message ?? `Request failed (${response.status}).`,
      response.status,
      body?.error?.code ?? 'http_error',
      body?.error?.details ?? [],
    );
  } catch {
    return new ApiError(`Request failed (${response.status}).`, response.status, 'http_error');
  }
}

/** Exchange the stored refresh token for new tokens. */
export function refreshSession(): Promise<boolean> {
  refreshing ??= (async () => {
    try {
      const refreshToken = storedRefresh();
      if (!refreshToken) return false;
      const response = await send('POST', '/auth/refresh', { body: { refresh_token: refreshToken } });
      if (!response.ok) {
        storeTokens(null);
        return false;
      }
      storeTokens(await response.json());
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

async function authorised(method: string, path: string, init: { params?: Query; body?: unknown }): Promise<Response> {
  if (!accessToken && !(await refreshSession())) {
    throw new ApiError('Please sign in.', 401, 'not_authenticated');
  }
  let response = await send(method, path, { ...init, token: accessToken });
  if (response.status === 401) {
    if (!(await refreshSession())) {
      storeTokens(null);
      expiredListeners.forEach((listener) => listener());
      throw new ApiError('Your session has ended. Please sign in again.', 401, 'session_expired');
    }
    response = await send(method, path, { ...init, token: accessToken });
  }
  if (!response.ok) throw await toError(response);
  return response;
}

export async function api<T>(method: string, path: string, init: { params?: Query; body?: unknown } = {}): Promise<T> {
  const response = await authorised(method, path, init);
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export const get = <T>(path: string, params?: Query) => api<T>('GET', path, { params });
export const post = <T>(path: string, body: unknown = {}) => api<T>('POST', path, { body });

/** A private file (ID document, vehicle document, photo) as a blob: URL. Revoke it when done. */
export async function fileUrl(path: string): Promise<{ url: string; type: string }> {
  const blob = await (await authorised('GET', path, {})).blob();
  return { url: URL.createObjectURL(blob), type: blob.type };
}

// --- session ---------------------------------------------------------------------------------

export interface Me {
  id: string;
  email: string;
  full_name: string;
  roles: string[];
}

export class NotAdminError extends ApiError {
  constructor() {
    super('This account is not an administrator.', 403, 'not_admin');
  }
}

async function requireAdmin(): Promise<Me> {
  const me = await get<Me>('/users/me');
  if (!me.roles.includes('ADMIN')) {
    await signOut();
    throw new NotAdminError();
  }
  return me;
}

export async function signIn(email: string, password: string): Promise<Me> {
  const response = await send('POST', '/auth/login', { body: { email, password } });
  if (!response.ok) throw await toError(response);
  storeTokens(await response.json());
  return requireAdmin();
}

/** Restore the session after a reload, or null if there is none. */
export async function restoreSession(): Promise<Me | null> {
  if (!storedRefresh() || !(await refreshSession())) return null;
  try {
    return await requireAdmin();
  } catch {
    return null;
  }
}

export async function signOut(): Promise<void> {
  const refreshToken = storedRefresh();
  storeTokens(null);
  if (refreshToken) {
    try {
      await send('POST', '/auth/logout', { body: { refresh_token: refreshToken } });
    } catch {
      // Already signed out locally; the refresh token expires on its own.
    }
  }
}
