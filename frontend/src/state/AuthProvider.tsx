import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { Session, User } from '@supabase/supabase-js';
import { isAuthConfigured, supabase } from '../lib/supabase';

interface AuthContextValue {
  configured: boolean;
  loading: boolean;
  session: Session | null;
  user: User | null;
  /** Error from the last sign-in attempt, e.g. the provider rejected it */
  error: string | null;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Where to return after Google sends the user back (the OAuth redirect drops the #/route). */
const RETURN_KEY = 'gg.auth.returnTo';

/** Reads ?error / ?code left by the OAuth redirect, then removes them without disturbing the #/route. */
function takeRedirectParams(): string | null {
  const params = new URLSearchParams(window.location.search);
  const error = params.get('error_description') || params.get('error');
  if (params.has('code') || error) {
    let hash = window.location.hash;
    try {
      hash = window.sessionStorage.getItem(RETURN_KEY) || hash;
      window.sessionStorage.removeItem(RETURN_KEY);
    } catch {
      // storage blocked: land on the default route
    }
    window.history.replaceState(null, '', `${window.location.pathname}${hash}`);
  }
  return error;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(isAuthConfigured);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!supabase) return;
    let active = true;
    // getSession waits for supabase-js to finish exchanging a ?code= from the redirect.
    supabase.auth.getSession().then(({ data, error: sessionError }) => {
      if (!active) return;
      const redirectError = takeRedirectParams();
      setSession(data.session);
      setError(redirectError ?? sessionError?.message ?? null);
      setLoading(false);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next));
    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, []);

  const signInWithGoogle = useCallback(async () => {
    if (!supabase) return;
    setError(null);
    try {
      window.sessionStorage.setItem(RETURN_KEY, window.location.hash);
    } catch {
      // not critical
    }
    const { error: signInError } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}${window.location.pathname}`,
        queryParams: { prompt: 'select_account' },
      },
    });
    if (signInError) setError(signInError.message);
  }, []);

  const signOut = useCallback(async () => {
    if (!supabase) return;
    await supabase.auth.signOut();
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      configured: isAuthConfigured,
      loading,
      session,
      user: session?.user ?? null,
      error,
      signInWithGoogle,
      signOut,
    }),
    [loading, session, error, signInWithGoogle, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
