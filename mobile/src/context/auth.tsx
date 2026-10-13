import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { onSessionExpired } from '@/lib/api';
import * as authService from '@/services/auth';
import type { CurrentUser, RegisterInput } from '@/types/auth';

type AuthState =
  | { status: 'loading'; user: null }
  | { status: 'signedOut'; user: null }
  | { status: 'signedIn'; user: CurrentUser };

interface AuthContextValue {
  state: AuthState;
  login: (email: string, password: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** The signed-in user for the stored session, or null (no session, or it is no longer valid). */
async function loadSessionUser(): Promise<CurrentUser | null> {
  try {
    if (!(await authService.hasStoredSession())) return null;
    return await authService.getCurrentUser();
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading', user: null });

  useEffect(() => {
    let cancelled = false;
    loadSessionUser().then((user) => {
      if (!cancelled) setState(user ? { status: 'signedIn', user } : { status: 'signedOut', user: null });
    });
    const unsubscribe = onSessionExpired(() => setState({ status: 'signedOut', user: null }));
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  const refreshUser = useCallback(async () => {
    const user = await loadSessionUser();
    setState(user ? { status: 'signedIn', user } : { status: 'signedOut', user: null });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      login: async (email, password) => {
        setState({ status: 'signedIn', user: await authService.login(email, password) });
      },
      register: async (input) => {
        setState({ status: 'signedIn', user: await authService.register(input) });
      },
      logout: async () => {
        await authService.logout();
        setState({ status: 'signedOut', user: null });
      },
      refreshUser,
    }),
    [state, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>');
  return context;
}
