/**
 * Minimal HTTP client for the FastAPI backend. Every failure becomes an ApiError with a
 * stable `code`, so screens can show the right message without parsing responses.
 */
const DEFAULT_TIMEOUT_MS = 15_000;

export const API_BASE_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/+$/, '');

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }

  get isNotFound() {
    return this.status === 404;
  }
}

type QueryValue = string | number | boolean | null | undefined;

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

export async function apiGet<T>(
  path: string,
  params?: Record<string, QueryValue>,
  { timeoutMs = DEFAULT_TIMEOUT_MS }: { timeoutMs?: number } = {},
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(buildUrl(path, params), {
      headers: { Accept: 'application/json' },
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

  if (!response.ok) {
    let message = 'Something went wrong. Please try again.';
    let code = 'http_error';
    try {
      const body = await response.json();
      message = body?.error?.message ?? message;
      code = body?.error?.code ?? code;
    } catch {
      // Not JSON (e.g. a proxy error page): keep the generic message.
    }
    throw new ApiError(message, response.status, code);
  }
  return (await response.json()) as T;
}
