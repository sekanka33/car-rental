import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, buildUrl, get, NotAdminError, onSessionExpired, restoreSession, signIn, signOut } from '../lib/api';
import { ADMIN_ME, mockApi, reply, TOKENS } from './mock-api';

beforeEach(async () => {
  vi.unstubAllGlobals();
  // Start every test signed out (clears the in-memory access token).
  mockApi({ 'POST /auth/logout': reply(204) });
  sessionStorage.setItem('carhire.admin.refresh', 'x');
  await signOut();
});

describe('buildUrl', () => {
  it('drops empty parameters and encodes values', () => {
    expect(buildUrl('/admin/users', { q: 'a b', role: '', status: undefined, limit: 25 })).toBe(
      'http://localhost:8000/api/v1/admin/users?q=a%20b&limit=25',
    );
  });
});

describe('signing in', () => {
  it('keeps only the refresh token in session storage', async () => {
    const calls = mockApi({ 'POST /auth/login': TOKENS, 'GET /users/me': ADMIN_ME });

    await expect(signIn('admin@example.com', 'pw')).resolves.toMatchObject({ roles: ['ADMIN'] });

    expect(sessionStorage.getItem('carhire.admin.refresh')).toBe('refresh-1');
    expect(JSON.stringify(sessionStorage)).not.toContain('access-1');
    expect(calls[1].auth).toBe('Bearer access-1');
  });

  it('refuses accounts that are not administrators and ends their session', async () => {
    const calls = mockApi({
      'POST /auth/login': TOKENS,
      'GET /users/me': { ...ADMIN_ME, roles: ['OWNER'] },
      'POST /auth/logout': reply(204),
    });

    await expect(signIn('owner@example.com', 'pw')).rejects.toBeInstanceOf(NotAdminError);

    expect(calls.map((c) => `${c.method} ${c.path}`)).toContain('POST /auth/logout');
    expect(calls.find((c) => c.path === '/auth/logout')?.body).toEqual({ refresh_token: 'refresh-1' });
    expect(sessionStorage.getItem('carhire.admin.refresh')).toBeNull();
  });

  it('shows the backend message for wrong credentials', async () => {
    mockApi({ 'POST /auth/login': reply(401, { error: { code: 'invalid_credentials', message: 'Incorrect email or password.' } }) });
    await expect(signIn('a@b.co', 'bad')).rejects.toMatchObject({ status: 401, message: 'Incorrect email or password.' });
  });
});

describe('expired access tokens', () => {
  it('refreshes once and retries, sharing one refresh between parallel requests', async () => {
    let usersCalls = 0;
    const calls = mockApi({
      'POST /auth/login': TOKENS,
      'GET /users/me': ADMIN_ME,
      'POST /auth/refresh': { ...TOKENS, access_token: 'access-2', refresh_token: 'refresh-2' },
      'GET /admin/users': () => {
        usersCalls += 1;
        return usersCalls <= 2 ? { status: 401, json: {} } : { json: { items: [], total: 0 } };
      },
    });
    await signIn('admin@example.com', 'pw');

    await Promise.all([get('/admin/users'), get('/admin/users')]);

    expect(calls.filter((c) => c.path === '/auth/refresh')).toHaveLength(1);
    expect(calls.filter((c) => c.path === '/admin/users').slice(-2).map((c) => c.auth)).toEqual([
      'Bearer access-2',
      'Bearer access-2',
    ]);
    expect(sessionStorage.getItem('carhire.admin.refresh')).toBe('refresh-2');
  });

  it('signs out and tells the app when refreshing fails', async () => {
    mockApi({
      'POST /auth/login': TOKENS,
      'GET /users/me': ADMIN_ME,
      'POST /auth/refresh': reply(401),
      'GET /admin/users': reply(401),
    });
    await signIn('admin@example.com', 'pw');
    const expired = vi.fn();
    const stop = onSessionExpired(expired);

    const error = await get('/admin/users').catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe('session_expired');
    expect(expired).toHaveBeenCalledOnce();
    expect(sessionStorage.getItem('carhire.admin.refresh')).toBeNull();
    stop();
  });
});

describe('restoring a session after reload', () => {
  it('uses the stored refresh token', async () => {
    sessionStorage.setItem('carhire.admin.refresh', 'refresh-1');
    mockApi({ 'POST /auth/refresh': TOKENS, 'GET /users/me': ADMIN_ME });
    await expect(restoreSession()).resolves.toMatchObject({ email: 'admin@example.com' });
  });

  it('returns nothing without a stored token, without calling the server', async () => {
    const calls = mockApi({});
    await expect(restoreSession()).resolves.toBeNull();
    expect(calls).toHaveLength(0);
  });
});
