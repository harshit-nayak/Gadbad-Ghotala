import { useCallback, useEffect } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { areaForPath, productAreas } from '../../app/navigation';
import { useAuth } from '../../state/AuthProvider';
import { useDemo } from '../../state/DemoProvider';
import { Button } from '../ui/Button';
import { Logo } from '../ui/Logo';
import './layout.css';
import { PRODUCT_NAME } from '../../app/brand';
import { usePresenterMode } from '../../hooks/usePresenterMode';
import { useToast } from '../ui/Toast';

export function AppShell() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { state, actions } = useDemo();
  const { signOut } = useAuth();
  const area = areaForPath(pathname);
  const latestIncident = state.incidents.find((i) => i.live);

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
          {productAreas.map((item) => (
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
          <Button
            variant="ghost"
            onClick={signOut}
          >
            Sign out
          </Button>
        </div>
      </header>
      <main id="main" className="shell__main">
        <Outlet />
      </main>
    </div>
  );
}
