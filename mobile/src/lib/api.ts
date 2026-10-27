/**
 * HTTP client for the FastAPI backend.
 * - Every failure becomes an ApiError with a stable `code` (network, timeout, backend envelope).
 * - Authenticated calls send the access token; on a 401 the client refreshes the session once
 *   (concurrent refreshes share one request) and retries. If refreshing fails, the stored
 *   session is cleared and `onSessionExpired` listeners are told.
 */
import { clearTokens, loadTokens, saveTokens } from '@/lib/token-storage';
import { Platform } from 'react-native';

const DEFAULT_TIMEOUT_MS = 15_000;

export function getApiBaseUrl(platform: typeof Platform.OS, configuredUrl?: string): string {
  const defaultUrl = platform === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000';
  const url = configuredUrl?.trim() || defaultUrl;
  const platformUrl =
    platform === 'android'
      ? url.replace(/^(https?:\/\/)(?:localhost|127\.0\.0\.1)(?=[:/]|$)/i, (host) =>
          host.replace(/localhost|127\.0\.0\.1/i, '10.0.2.2'),
        )
      : url;
  return platformUrl.replace(/\/+$/, '');
}

export const API_BASE_URL = getApiBaseUrl(Platform.OS, process.env.EXPO_PUBLIC_API_URL);

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly details: { reason?: string; [key: string]: unknown }[] = [],
  ) {
    super(message);
    this.name = 'ApiError';
  }

  get isNotFound() {
    return this.status === 404;
  }
}

type QueryValue = string | number | boolean | null | undefined;

interface RequestOptions {
  params?: Record<string, QueryValue>;
  body?: unknown;
  /** Multipart upload (files); sent instead of `body`. The boundary header is set by fetch. */
  form?: FormData;
  auth?: boolean;
  timeoutMs?: number;
}

export function buildUrl(path: string, params?: Record<string, QueryValue>): string {
  const url = path.startsWith('http') ? path : `${API_BASE_URL}${path}`;
  const query = Object.entries(params ?? {})
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join('&');
  return query ? `${url}?${query}` : url;
}

/** Absolute URL for a path the API returned (e.g. a photo URL). */
export function resolveApiUrl(path: string): string {
  return buildUrl(path);
}

const sessionExpiredListeners = new Set<() => void>();

export function onSessionExpired(listener: () => void): () => void {
  sessionExpiredListeners.add(listener);
  return () => sessionExpiredListeners.delete(listener);
}

async function send(method: string, path: string, options: RequestOptions, accessToken?: string): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (options.body !== undefined && !options.form) headers['Content-Type'] = 'application/json';
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  try {
    return await fetch(buildUrl(path, options.params), {
      method,
      headers,
      body: options.form ?? (options.body === undefined ? undefined : JSON.stringify(options.body)),
      signal: controller.signal,
    });
  } catch (error) {
    const timedOut = error instanceof Error && error.name === 'AbortError';
    throw new ApiError(
      timedOut
        ? 'The server took too long to respond. Please try again.'
        : 'Could not reach the server. Check your internet connection.',
      0,
      timedOut ? 'timeout' : 'network_error',
    );
  } finally {
    clearTimeout(timer);
  }
}

async function toError(response: Response): Promise<ApiError> {
  let message = 'Something went wrong. Please try again.';
  let code = 'http_error';
  let details: ApiError['details'] = [];
  try {
    const body = await response.json();
    message = body?.error?.message ?? message;
    code = body?.error?.code ?? code;
    details = body?.error?.details ?? [];
  } catch {
    // Not JSON (e.g. a proxy error page): keep the generic message.
  }
  return new ApiError(message, response.status, code, details);
}

let refreshing: Promise<string | null> | null = null;

/** Exchange the refresh token for new tokens. Returns the new access token or null. */
function refreshSession(): Promise<string | null> {
  refreshing ??= (async () => {
    try {
      const tokens = await loadTokens();
      if (!tokens) return null;
      const response = await send('POST', '/api/v1/auth/refresh', { body: { refresh_token: tokens.refreshToken } });
      if (!response.ok) return null;
      const body = await response.json();
      await saveTokens({ accessToken: body.access_token, refreshToken: body.refresh_token });
      return body.access_token as string;
    } catch {
      return null;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

export async function apiRequest<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  let token: string | undefined;
  if (options.auth) {
    token = (await loadTokens())?.accessToken;
    if (!token) throw new ApiError('Please log in to continue.', 401, 'not_authenticated');
  }
  let response = await send(method, path, options, token);
  if (options.auth && response.status === 401) {
    const renewed = await refreshSession();
    if (!renewed) {
      await clearTokens();
      sessionExpiredListeners.forEach((listener) => listener());
      throw new ApiError('Your session has ended. Please log in again.', 401, 'session_expired');
    }
    response = await send(method, path, options, renewed);
  }
  if (!response.ok) throw await toError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** WebSocket URL for an API path (http → ws, https → wss). */
export function websocketUrl(path: string): string {
  return `${API_BASE_URL.replace(/^http/, 'ws')}${path}`;
}

/**
 * Access token for a WebSocket, which cannot use the automatic retry above. With `renew`, the
 * session is refreshed first (after the server closed the socket because the token expired).
 */
export async function getAccessToken({ renew = false }: { renew?: boolean } = {}): Promise<string | null> {
  if (renew) return refreshSession();
  return (await loadTokens())?.accessToken ?? null;
}

export function apiGet<T>(
  path: string,
  params?: Record<string, QueryValue>,
  { timeoutMs }: { timeoutMs?: number } = {},
): Promise<T> {
  return apiRequest<T>('GET', path, { params, timeoutMs });
}
