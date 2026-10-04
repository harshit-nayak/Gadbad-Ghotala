import { Link } from 'react-router-dom';
import { PRODUCT_NAME } from '../../app/brand';
import { Icon } from '../../components/ui/Icon';
import { Logo } from '../../components/ui/Logo';
import { useAuth } from '../../state/AuthProvider';
import './landing.css';

interface Pillar {
  id: string;
  to: string;
  icon: 'voice' | 'activity' | 'fileText' | 'dashboard';
  title: string;
  tag: string;
  lead: string;
  bullets: string[];
  cta: string;
  comingSoon?: boolean;
}

const PILLARS: Pillar[] = [
  {
    id: 'audio',
    to: '/audio',
    icon: 'voice',
    title: 'Audio Analysis',
    tag: 'Live Mic & Upload',
    lead: 'Detect cloned voices and synthetic speech in seconds using XLS-R + Mamba.',
    bullets: ['Browser mic capture or file upload', '22+ Indian languages & dialects', 'Real-time risk score & timeline'],
    cta: 'Open Audio Check',
  },
  {
    id: 'video',
    to: '/video',
    icon: 'activity',
    title: 'Video Analysis',
    tag: 'Coming Soon',
    lead: 'Frame-by-frame deepfake and facial manipulation forensics for video calls.',
    bullets: ['GAN boundary & face-swap detection', 'Temporal coherence tracking', 'Anomaly heatmaps'],
    cta: 'Preview Video Engine',
    comingSoon: true,
  },
  {
    id: 'documents',
    to: '/documents',
    icon: 'fileText',
    title: 'Document Integrity',
    tag: 'Ed25519 Signed',
    lead: 'Cryptographic document signing and instant tamper verification via embedded QR certificates.',
    bullets: ['Ed25519 digital signatures', 'QR certificate stamping', 'Audit trail & change detection'],
    cta: 'Verify Documents',
  },
  {
    id: 'dashboard',
    to: '/dashboard',
    icon: 'dashboard',
    title: 'Security Operations',
    tag: 'Command Hub',
    lead: 'Real-time incident response console with biometric caller profiles and automated reports.',
    bullets: ['Live incident feed & alarms', 'Voice profile fingerprinting', 'Court-admissible PDF audits'],
    cta: 'Open Dashboard',
  },
];

const WORKFLOW = [
  { step: '01', title: 'Capture', desc: 'Call audio, mic stream or document upload' },
  { step: '02', title: 'Forensics', desc: 'Acoustic, spectral & temporal inspection' },
  { step: '03', title: 'Scoring', desc: 'Weighted risk matrix tuned for Indian context' },
  { step: '04', title: 'Defense', desc: 'Real-time alert & automated forensic audit' },
];

export function Landing() {
  const { session, user } = useAuth();
  const displayName = user?.user_metadata?.full_name || user?.email?.split('@')[0] || 'User';

  return (
    <div className="compact-landing" data-theme="landing">
      {/* ── Minimalist Top Header with Audio, Video, Document, Dashboard ── */}
      <header className="compact-nav">
        <div className="compact-nav__brand">
          <Logo />
        </div>

        <nav className="compact-nav__menu" aria-label="Main Navigation">
          <Link to="/" className="compact-nav__item compact-nav__item--active">
            About
          </Link>
          <Link to="/audio" className="compact-nav__item">
            <Icon name="voice" size={15} />
            <span>Audio</span>
          </Link>
          <Link to="/video" className="compact-nav__item">
            <Icon name="activity" size={15} />
            <span>Video</span>
            <span className="compact-nav__badge-soon">Soon</span>
          </Link>
          <Link to="/documents" className="compact-nav__item">
            <Icon name="fileText" size={15} />
            <span>Document</span>
          </Link>
          <Link to="/dashboard" className="compact-nav__item">
            <Icon name="dashboard" size={15} />
            <span>Dashboard</span>
          </Link>
        </nav>

        <div className="compact-nav__actions">
          {session ? (
            <Link to="/employee" className="btn btn--primary btn--sm compact-nav__btn">
              <span>Console ({displayName})</span>
              <Icon name="arrowRight" size={14} />
            </Link>
          ) : (
            <Link to="/employee" className="btn btn--primary btn--sm compact-nav__btn">
              <span>Sign in</span>
              <Icon name="arrowRight" size={14} />
            </Link>
          )}
        </div>
      </header>

      <main className="compact-body">
        {/* ── Compact Hero ── */}
        <section className="compact-hero">
          <div className="compact-hero__pill">
            <span className="compact-hero__pill-dot" />
            <span>Real-time Multi-Modal AI Fraud Prevention</span>
          </div>
          <h1 className="compact-hero__title">
            Stop AI impersonation before it costs you
          </h1>
          <p className="compact-hero__subtitle">
            {PRODUCT_NAME} equips organisations against synthetic voice scams, deepfake video manipulation, and forged documents — optimized for Indian languages with sub-second real-time detection.
          </p>
          <div className="compact-hero__actions">
            <Link to="/employee" className="btn btn--primary btn--md">
              Launch Call Protection Demo
            </Link>
            <Link to="/audio" className="btn btn--ghost btn--md">
              <Icon name="voice" size={16} />
              <span>Test Audio Check</span>
            </Link>
          </div>
        </section>

        {/* ── All Features in Compact 4-Pillar Grid ── */}
        <section className="compact-features">
          <div className="compact-features__grid">
            {PILLARS.map((p) => (
              <div key={p.id} className={`compact-card compact-card--${p.id}`}>
                <div className="compact-card__head">
                  <div className="compact-card__icon-box">
                    <Icon name={p.icon} size={20} />
                  </div>
                  <span className={`compact-card__tag ${p.comingSoon ? 'compact-card__tag--soon' : ''}`}>
                    {p.tag}
                  </span>
                </div>

                <h3 className="compact-card__title">{p.title}</h3>
                <p className="compact-card__lead">{p.lead}</p>

                <ul className="compact-card__list">
                  {p.bullets.map((b) => (
                    <li key={b}>
                      <Icon name="shieldCheck" size={13} />
                      <span>{b}</span>
                    </li>
                  ))}
                </ul>

                <Link to={p.to} className="compact-card__cta">
                  <span>{p.cta}</span>
                  <span className="compact-card__arrow">→</span>
                </Link>
              </div>
            ))}
          </div>
        </section>

        {/* ── Streamlined 4-Step Pipeline Strip ── */}
        <section className="compact-flow">
          <div className="compact-flow__header">
            <span className="compact-flow__label">How It Works</span>
            <span className="compact-flow__sub">End-to-end multi-layer detection pipeline</span>
          </div>
          <div className="compact-flow__steps">
            {WORKFLOW.map((s, idx) => (
              <div key={s.step} className="compact-flow__step">
                <div className="compact-flow__step-badge">{s.step}</div>
                <div className="compact-flow__step-content">
                  <strong>{s.title}</strong>
                  <p>{s.desc}</p>
                </div>
                {idx < WORKFLOW.length - 1 && <span className="compact-flow__divider">›</span>}
              </div>
            ))}
          </div>
        </section>
      </main>

      {/* ── Clean, Minimal Footer ── */}
      <footer className="compact-footer">
        <div className="compact-footer__inner">
          <span>{PRODUCT_NAME} · Smart India Hackathon 2026 (SIH26104)</span>
          <div className="compact-footer__links">
            <Link to="/employee">Employee Call App</Link>
            <Link to="/security">Security Ops</Link>
            <Link to="/documents">Documents</Link>
            <Link to="/admin">Admin</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
