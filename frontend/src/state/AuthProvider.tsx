import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { Provider, Session, User } from '@supabase/supabase-js';
import { isAuthConfigured, supabase } from '../lib/supabase';

interface AuthContextValue {
  configured: boolean;
  loading: boolean;
  session: Session | null;
  user: User | null;
  /** Error from the last sign-in attempt, e.g. the provider rejected it */
  error: string | null;
  signInWithGoogle: () => Promise<void>;
  signInWithGithub: () => Promise<void>;
  signInWithOAuth: (provider: Provider) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Where to return after OAuth sends the user back (the OAuth redirect drops the #/route). */
const RETURN_KEY = 'gg.auth.returnTo';

/**
 * Restores the pre-login #/route saved before OAuth redirect, and strips any
 * ?code= or ?error left by the OAuth redirect so the URL remains clean.
 */
function takeRedirectParams(): string | null {
  const params = new URLSearchParams(window.location.search);
  const error = params.get('error_description') || params.get('error');
  const hasCode = params.has('code');
  let savedHash: string | null = null;
  try {
    savedHash = window.sessionStorage.getItem(RETURN_KEY);
    window.sessionStorage.removeItem(RETURN_KEY);
  } catch {
    // storage blocked: land on the default route
  }

  if (hasCode || error || savedHash !== null) {
    params.delete('code');
    params.delete('error');
    params.delete('error_description');
    params.delete('error_code');
    const remaining = params.toString();
    const queryPart = remaining ? `?${remaining}` : '';
    const hashPart = savedHash ?? window.location.hash;
    window.history.replaceState(null, '', `${window.location.pathname}${queryPart}${hashPart}`);
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

    const { data } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      setLoading(false);
    });

    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, []);

  const signInWithOAuth = useCallback(async (provider: Provider) => {
    if (!supabase) return;
    setError(null);
    try {
      window.sessionStorage.setItem(RETURN_KEY, window.location.hash);
    } catch {
      // not critical
    }
    const { error: signInError } = await supabase.auth.signInWithOAuth({
      provider,
      options: {
        redirectTo: `${window.location.origin}${window.location.pathname}`,
        queryParams: provider === 'google' ? { prompt: 'select_account' } : undefined,
      },
    });
    if (signInError) setError(signInError.message);
  }, []);

  const signInWithGoogle = useCallback(() => signInWithOAuth('google'), [signInWithOAuth]);
  const signInWithGithub = useCallback(() => signInWithOAuth('github'), [signInWithOAuth]);

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
      signInWithGithub,
      signInWithOAuth,
      signOut,
    }),
    [loading, session, error, signInWithGoogle, signInWithGithub, signInWithOAuth, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
