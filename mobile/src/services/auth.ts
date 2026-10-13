import { apiRequest } from '@/lib/api';
import { clearTokens, loadTokens, saveTokens } from '@/lib/token-storage';
import type { CurrentUser, RegisterInput } from '@/types/auth';

interface TokenResponse {
  access_token: string;
  refresh_token: string;
}

export async function login(email: string, password: string): Promise<CurrentUser> {
  const tokens = await apiRequest<TokenResponse>('POST', '/api/v1/auth/login', { body: { email, password } });
  await saveTokens({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token });
  return getCurrentUser();
}

export async function register(input: RegisterInput): Promise<CurrentUser> {
  await apiRequest('POST', '/api/v1/auth/register', { body: input });
  return login(input.email, input.password);
}

export function getCurrentUser(): Promise<CurrentUser> {
  return apiRequest<CurrentUser>('GET', '/api/v1/users/me', { auth: true });
}

/** Revoke the session on the server (best effort) and forget it locally. */
export async function logout(): Promise<void> {
  const tokens = await loadTokens();
  if (tokens) {
    try {
      await apiRequest('POST', '/api/v1/auth/logout', { body: { refresh_token: tokens.refreshToken } });
    } catch {
      // Offline or already revoked: the local session is cleared anyway.
    }
  }
  await clearTokens();
}

export async function hasStoredSession(): Promise<boolean> {
  return (await loadTokens()) !== null;
}
