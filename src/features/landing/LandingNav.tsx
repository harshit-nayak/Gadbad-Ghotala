import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Icon } from '../../components/ui/Icon';
import { Logo } from '../../components/ui/Logo';
import { navLinks } from './content';
import { scrollToId } from './scrollTo';
import { PRODUCT_NAME } from '../../app/brand';

export function LandingNav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 10);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className={`lnav-wrap ${scrolled ? 'is-scrolled' : ''}`}>
      <header className="lnav">
        <Link to="/" className="lnav__brand" aria-label={`${PRODUCT_NAME} home`}>
          <Logo />
        </Link>

        <nav className="lnav__links" aria-label="Sections">
          {navLinks.map((link) => (
            <a key={link.href} href={link.href} onClick={(e) => scrollToId(e, link.href)}>
              {link.label}
            </a>
          ))}
        </nav>

        <div className="lnav__actions">
          <Link to="/login" className="lnav__login">
            Login
          </Link>
          <Link to="/login" className="btn btn--primary btn--md lnav__cta">
            <span>Get started</span>
          </Link>
        </div>

        <button
          type="button"
          className="lnav__toggle"
          aria-expanded={open}
          aria-controls="lnav-mobile"
          aria-label={open ? 'Close menu' : 'Open menu'}
          onClick={() => setOpen((v) => !v)}
        >
          <Icon name={open ? 'close' : 'list'} size={18} />
        </button>
      </header>

      {open && (
        <div className="lnav-mobile" id="lnav-mobile">
          <nav aria-label="Sections">
            {navLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                onClick={(e) => {
                  scrollToId(e, link.href);
                  setOpen(false);
                }}
              >
                {link.label}
              </a>
            ))}
          </nav>
          <div className="lnav-mobile__actions">
            <Link to="/login" className="btn btn--secondary btn--md" onClick={() => setOpen(false)}>
              <span>Login</span>
            </Link>
            <Link to="/login" className="btn btn--primary btn--md" onClick={() => setOpen(false)}>
              <span>Get started</span>
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
