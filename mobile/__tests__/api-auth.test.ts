import { apiRequest, onSessionExpired } from '@/lib/api';
import { clearTokens, loadTokens, saveTokens } from '@/lib/token-storage';

const mockFetch = jest.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

function json(status: number, body: unknown = {}) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

beforeEach(async () => {
  await saveTokens({ accessToken: 'old-access', refreshToken: 'old-refresh' });
});

afterEach(async () => {
  await clearTokens();
});

it('sends the access token on authenticated calls', async () => {
  mockFetch.mockResolvedValueOnce(json(200, { ok: true }));

  await apiRequest('GET', '/api/v1/users/me', { auth: true });

  expect(mockFetch.mock.calls[0][1].headers.Authorization).toBe('Bearer old-access');
});

it('refreshes once on 401 and retries with the new token', async () => {
  mockFetch
    .mockResolvedValueOnce(json(401))
    .mockResolvedValueOnce(json(200, { access_token: 'new-access', refresh_token: 'new-refresh' }))
    .mockResolvedValueOnce(json(200, { id: 'u1' }));

  await expect(apiRequest('GET', '/api/v1/users/me', { auth: true })).resolves.toEqual({ id: 'u1' });

  expect(mockFetch.mock.calls[1][0]).toMatch(/\/api\/v1\/auth\/refresh$/);
  expect(JSON.parse(mockFetch.mock.calls[1][1].body)).toEqual({ refresh_token: 'old-refresh' });
  expect(mockFetch.mock.calls[2][1].headers.Authorization).toBe('Bearer new-access');
  expect(await loadTokens()).toEqual({ accessToken: 'new-access', refreshToken: 'new-refresh' });
});

it('ends the session when refreshing fails', async () => {
  const expired = jest.fn();
  const unsubscribe = onSessionExpired(expired);
  mockFetch.mockResolvedValueOnce(json(401)).mockResolvedValueOnce(json(401));

  await expect(apiRequest('GET', '/api/v1/bookings', { auth: true })).rejects.toMatchObject({
    status: 401,
    code: 'session_expired',
  });

  expect(await loadTokens()).toBeNull();
  expect(expired).toHaveBeenCalledTimes(1);
  unsubscribe();
});

it('shares one refresh between concurrent requests', async () => {
  mockFetch.mockImplementation(async (url: string, init: RequestInit) => {
    if (url.endsWith('/auth/refresh')) return json(200, { access_token: 'fresh', refresh_token: 'r2' });
    const auth = (init.headers as Record<string, string>).Authorization;
    return auth === 'Bearer fresh' ? json(200, { ok: true }) : json(401);
  });

  await Promise.all([
    apiRequest('GET', '/a', { auth: true }),
    apiRequest('GET', '/b', { auth: true }),
  ]);

  expect(mockFetch.mock.calls.filter(([url]) => String(url).endsWith('/auth/refresh'))).toHaveLength(1);
  mockFetch.mockReset();
});

it('asks to log in when there is no session', async () => {
  await clearTokens();

  await expect(apiRequest('GET', '/api/v1/bookings', { auth: true })).rejects.toMatchObject({
    status: 401,
    code: 'not_authenticated',
  });
  expect(mockFetch).not.toHaveBeenCalled();
});

it('sends JSON bodies and handles 204', async () => {
  mockFetch.mockResolvedValueOnce({ ok: true, status: 204, json: async () => undefined } as Response);

  await expect(apiRequest('POST', '/api/v1/auth/logout', { body: { refresh_token: 'x' } })).resolves.toBeUndefined();
  expect(mockFetch.mock.calls[0][1].headers['Content-Type']).toBe('application/json');
});
