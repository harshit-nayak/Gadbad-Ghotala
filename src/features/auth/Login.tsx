import { useEffect, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { PRODUCT_NAME } from '../../app/brand';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Logo } from '../../components/ui/Logo';
import { DEMO_EMAIL, useAuth } from '../../state/AuthProvider';
import { Atmosphere } from '../landing/Atmosphere';
import './auth.css';

interface FromState {
  from?: string;
}

export function Login() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState<'form' | 'demo' | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = 'landing';
  }, []);

  const target = (location.state as FromState | null)?.from ?? '/employee';

  const enter = (mode: 'form' | 'demo', address?: string) => {
    setSubmitting(mode);
    signIn(address);
    navigate(target, { replace: true });
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    enter('form', email);
  };

  return (
    <div className="auth">
      <Atmosphere />
      <div className="auth__panel">
        <Link to="/" className="auth__brand" aria-label={`${PRODUCT_NAME} home`}>
          <Logo />
        </Link>

        <div className="auth__body glass">
          <h1 className="auth__title">Sign in to {PRODUCT_NAME}</h1>
          <p className="auth__lede">Use your work account to open the workspace for your role.</p>

          <form className="auth__form" onSubmit={onSubmit}>
            <label className="auth__field">
              <span>Work email</span>
              <input
                type="email"
                name="email"
                autoComplete="username"
                placeholder={DEMO_EMAIL}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label className="auth__field">
              <span>Password</span>
              <input
                type="password"
                name="password"
                autoComplete="current-password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>

            <Button type="submit" variant="primary" size="lg" block loading={submitting === 'form'}>
              Login
            </Button>
          </form>

          <div className="auth__divider">
            <span>or</span>
          </div>

          <Button variant="secondary" size="lg" block icon="arrowRight" loading={submitting === 'demo'} onClick={() => enter('demo')}>
            Continue to demo
          </Button>

          <p className="auth__note">
            <Icon name="lock" size={14} />
            Demo sign-in for the prototype. No credentials are checked or stored.
          </p>
        </div>

        <Link to="/" className="auth__back">
          <Icon name="arrowLeft" size={14} />
          Back to the {PRODUCT_NAME} site
        </Link>
      </div>

      <aside className="auth__aside" aria-hidden="true">
        <div className="auth__aside-inner">
          <p className="auth__quote">Real voices can be cloned. Trust shouldn't be.</p>
          <p className="auth__aside-sub">
            Real-time detection, request-level verification and incident evidence, in one platform.
          </p>
          <ul className="auth__roles">
            <li>Employee</li>
            <li>Security and fraud</li>
            <li>Documents</li>
            <li>Administrator</li>
          </ul>
        </div>
      </aside>
    </div>
  );
}
