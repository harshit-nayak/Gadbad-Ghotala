import type { ReactNode } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { workspaceNav } from '../../app/navigation';
import { Icon } from '../ui/Icon';
import './layout.css';

interface WorkspaceProps {
  area: keyof typeof workspaceNav;
  footer?: ReactNode;
}

/** Sidebar layout shared by Security, Documents and Administrator. */
export function Workspace({ area, footer }: WorkspaceProps) {
  const nav = workspaceNav[area];
  return (
    <div className="workspace">
      <aside className="workspace__side">
        <p className="workspace__title">{nav.title}</p>
        <nav aria-label={nav.title}>
          <ul className="workspace__nav">
            {nav.links.map((link) => (
              <li key={link.to}>
                <NavLink to={link.to} end={link.end} className="workspace__link">
                  <Icon name={link.icon} size={17} />
                  {link.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        {footer && <div className="workspace__footer">{footer}</div>}
      </aside>
      <div className="workspace__content">
        <Outlet />
      </div>
    </div>
  );
}

interface PageHeaderProps {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  return (
    <header className="page-head">
      <div className="page-head__text">
        {eyebrow && <div className="page-head__eyebrow">{eyebrow}</div>}
        <h1 className="page-head__title">{title}</h1>
        {description && <p className="page-head__desc">{description}</p>}
      </div>
      {actions && <div className="page-head__actions">{actions}</div>}
    </header>
  );
}

interface PanelProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  flush?: boolean;
  id?: string;
}

export function Panel({ title, subtitle, actions, children, className = '', flush = false, id }: PanelProps) {
  return (
    <section className={`panel ${flush ? 'panel--flush' : ''} ${className}`} aria-labelledby={title && id ? id : undefined}>
      {(title || actions) && (
        <div className="panel__head">
          <div>
            {title && (
              <h2 className="panel__title" id={id}>
                {title}
              </h2>
            )}
            {subtitle && <p className="panel__subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="panel__actions">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
