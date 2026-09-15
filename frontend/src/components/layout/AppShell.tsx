import { useCallback, useEffect } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { areaForPath, productAreas } from '../../app/navigation';
import { useDemo } from '../../state/DemoProvider';
import { Button } from '../ui/Button';
import { Logo } from '../ui/Logo';
import './layout.css';
import { PRODUCT_NAME } from '../../app/brand';
import { usePresenterMode } from '../../hooks/usePresenterMode';
import { useToast } from '../ui/Toast';
import { useAuth } from '../../state/AuthProvider';
import '../../features/auth/auth.css';

export function AppShell() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { state, actions } = useDemo();
  const area = areaForPath(pathname);
  const latestIncident = state.incidents.find((i) => i.live);
  const { user, signOut } = useAuth();
  const avatarUrl: string | undefined = user?.user_metadata?.avatar_url;
  const displayName: string = user?.user_metadata?.full_name || user?.email || 'Account';

  // Theme the document too, so overscroll and page edges match the area.
  useEffect(() => {
    document.documentElement.dataset.theme = area.theme;
  }, [area.theme]);

  // Start each screen at the top, as a real app navigation would.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  const notify = useToast();
  const announcePresenter = useCallback((on: boolean) => notify(on ? 'Presenter controls shown' : 'Presenter controls hidden'), [notify]);
  usePresenterMode(announcePresenter);

  const restartDemo = () => {
    actions.resetDemo();
    navigate('/employee');
  };

  return (
    <div className="shell" data-theme={area.theme}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="shell__bar">
        <Link to="/employee" className="shell__brand" aria-label={`${PRODUCT_NAME} home`}>
          <Logo />
        </Link>
        <nav className="shell__nav" aria-label="Product areas">
          {productAreas.filter((item) => !item.hidden).map((item) => (
            <NavLink
              key={item.id}
              to={item.basePath}
              className="shell__tab"
              aria-current={item.id === area.id ? 'page' : undefined}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="shell__tools">
          {latestIncident && (
            <Link to={`/security/incidents/${latestIncident.id}`} className="shell__incident">
              <span className="shell__incident-dot" aria-hidden="true" />
              Incident #{latestIncident.id}
            </Link>
          )}
          <Button variant="ghost" icon="refresh" onClick={restartDemo} className="presenter-only">
            Restart demo
          </Button>
          {user && (
            <span className="account" title={user.email ?? undefined}>
              {avatarUrl ? (
                <img className="account__avatar" src={avatarUrl} alt="" referrerPolicy="no-referrer" />
              ) : (
                <span className="account__initial" aria-hidden="true">{displayName.charAt(0).toUpperCase()}</span>
              )}
              <span className="account__name">{displayName}</span>
              <Button variant="ghost" onClick={() => void signOut()}>
                Sign out
              </Button>
            </span>
          )}
        </div>
      </header>
      <main id="main" className="shell__main">
        <Outlet />
      </main>
    </div>
  );
}
