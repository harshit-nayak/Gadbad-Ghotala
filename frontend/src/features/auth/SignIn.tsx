import { useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { PRODUCT_NAME } from '../../app/brand';
import { Logo } from '../../components/ui/Logo';
import { useAuth } from '../../state/AuthProvider';
import './auth.css';

function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}

function GithubMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
    </svg>
  );
}

/** Full-screen sign-in, shown instead of the app until the user has a session. */
export function SignIn() {
  const navigate = useNavigate();
  const { configured, signInWithGoogle, signInWithGithub, error } = useAuth();
  const [activeProvider, setActiveProvider] = useState<'google' | 'github' | null>(null);

  const startOAuth = async (provider: 'google' | 'github') => {
    setActiveProvider(provider);
    if (provider === 'google') {
      await signInWithGoogle();
    } else {
      await signInWithGithub();
    }
    // Only reached if redirect didn't happen (an error was raised).
    setActiveProvider(null);
  };

  return (
    <AuthScreen>
      <h1 className="auth__title">Sign in to {PRODUCT_NAME}</h1>
      <p className="auth__lead">Real-time protection against AI voice impersonation, deepfake video and document fraud.</p>

      <div className="auth__actions">
        <button
          type="button"
          className="auth__oauth-btn auth__google"
          id="auth-google-btn"
          onClick={() => void startOAuth('google')}
          disabled={activeProvider !== null}
          aria-busy={activeProvider === 'google' || undefined}
        >
          {activeProvider === 'google' ? <span className="spinner spinner--sm" aria-hidden="true" /> : <GoogleMark />}
          <span>{activeProvider === 'google' ? 'Connecting to Google…' : 'Sign in with Google'}</span>
        </button>

        <div className="auth__divider">or</div>

        <button
          type="button"
          className="auth__oauth-btn auth__github"
          id="auth-github-btn"
          onClick={() => void startOAuth('github')}
          disabled={activeProvider !== null}
          aria-busy={activeProvider === 'github' || undefined}
        >
          {activeProvider === 'github' ? <span className="spinner spinner--sm" aria-hidden="true" /> : <GithubMark />}
          <span>{activeProvider === 'github' ? 'Connecting to GitHub…' : 'Sign in with GitHub'}</span>
        </button>

        {(!configured || Boolean(error)) && (
          <div style={{ marginTop: 'var(--space-2)', width: '100%' }}>
            <button
              type="button"
              className="btn btn--primary"
              style={{ width: '100%', justifyContent: 'center' }}
              onClick={() => navigate('/employee')}
            >
              Continue to Console (Demo Mode) →
            </button>
          </div>
        )}
      </div>

      {error && (
        <p className="auth__error" role="alert">
          Sign-in didn't complete: {error}
        </p>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'var(--space-3)', width: '100%' }}>
        <Link to="/" style={{ color: 'var(--forest, #30483a)', fontSize: 'var(--text-xs)', fontWeight: 600, textDecoration: 'none' }}>
          ← Back to About
        </Link>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--ink-subtle, #7a8272)' }}>SIH26104</span>
      </div>
    </AuthScreen>
  );
}

export function AuthLoading() {
  return (
    <AuthScreen>
      <p className="auth__lead auth__loading">
        <span className="spinner spinner--sm" aria-hidden="true" /> Checking your sign-in…
      </p>
    </AuthScreen>
  );
}

function AuthScreen({ children }: { children: ReactNode }) {
  return (
    <div className="auth" data-theme="landing">
      <main className="auth__card">
        <div className="auth__brand">
          <Logo />
        </div>
        {children}
      </main>
    </div>
  );
}
