import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { type Me, onSessionExpired, restoreSession, signIn, signOut } from './api';

type AuthState = { status: 'loading' } | { status: 'signedOut'; expired?: boolean } | { status: 'signedIn'; me: Me };

interface AuthValue {
  state: AuthState;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' });

  useEffect(() => {
    let active = true;
    void restoreSession().then((me) => active && setState(me ? { status: 'signedIn', me } : { status: 'signedOut' }));
    const unsubscribe = onSessionExpired(() => setState({ status: 'signedOut', expired: true }));
    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setState({ status: 'signedIn', me: await signIn(email, password) });
  }, []);

  const logout = useCallback(async () => {
    await signOut();
    setState({ status: 'signedOut' });
  }, []);

  const value = useMemo(() => ({ state, login, logout }), [state, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
