import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

/**
 * Frontend-only demo authentication for the prototype.
 * There is no backend: any credentials are accepted, and "Continue to demo"
 * skips the form. Replace `signIn` with a real API call and keep the shape.
 */
export interface AuthUser {
  name: string;
  email: string;
}

/**
 * 'signed-out' means the person deliberately left the app, so the route guard
 * returns them to the public site instead of the login page. The landing page
 * clears it back to 'anonymous' on arrival.
 */
export type AuthStatus = 'anonymous' | 'authenticated' | 'signed-out';

interface AuthValue {
  user: AuthUser | null;
  status: AuthStatus;
  isAuthenticated: boolean;
  signIn: (email?: string) => void;
  signOut: () => void;
  clearSignOut: () => void;
}

export const DEMO_EMAIL = 'priya.menon@kaveriholdings.in';

const AuthContext = createContext<AuthValue | null>(null);

const nameFromEmail = (email: string) =>
  email
    .split('@')[0]
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(' ') || 'Demo user';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>('anonymous');

  const signIn = useCallback((email = DEMO_EMAIL) => {
    const clean = email.trim() || DEMO_EMAIL;
    setUser({ email: clean, name: nameFromEmail(clean) });
    setStatus('authenticated');
  }, []);

  const signOut = useCallback(() => {
    setUser(null);
    setStatus('signed-out');
  }, []);

  const clearSignOut = useCallback(() => {
    setStatus((current) => (current === 'signed-out' ? 'anonymous' : current));
  }, []);

  const value = useMemo<AuthValue>(
    () => ({ user, status, isAuthenticated: user !== null, signIn, signOut, clearSignOut }),
    [user, status, signIn, signOut, clearSignOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
