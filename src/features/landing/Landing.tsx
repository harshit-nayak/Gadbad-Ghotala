import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { PRODUCT_NAME } from '../../app/brand';
import { Icon } from '../../components/ui/Icon';
import { useReveal } from '../../hooks/useReveal';
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion';
import { useAuth } from '../../state/AuthProvider';
import { benchmark, benchmarkNote, caseStudies, metrics, stages } from './content';
import { Atmosphere } from './Atmosphere';
import { Editorial } from './EditorialArt';
import { assertUniqueImagery } from './imagery';
import { Hero } from './Hero';
import { LandingNav } from './LandingNav';
import './landing.css';

const problemCards = [
  {
    slot: 'problemExecutive' as const,
    label: 'Executive impersonation',
    quote: 'Transfer this immediately. I am in a meeting.',
    meta: 'Voice: familiar  ·  Request: financial',
  },
  {
    slot: 'problemVendor' as const,
    label: 'Vendor impersonation',
    quote: 'We have changed our bank details.',
    meta: 'Voice: known contact  ·  Request: payment change',
  },
  {
    slot: 'problemAuthority' as const,
    label: 'Authority impersonation',
    quote: 'Skip the normal verification process.',
    meta: 'Voice: senior manager  ·  Request: process bypass',
  },
];

function Problem() {
  const ref = useReveal<HTMLElement>();
  return (
    <section id="problem" ref={ref} className="problem reveal">
      <div className="lwrap">
        <header className="problem__head">
          <h2 className="statement">
            Voice cloning
            <br />
            changes the rules
            <br />
            of trust.
          </h2>
          <p className="problem__sub">
            Attackers sound real. They know the context. And they ask for real actions, while someone is on the line.
          </p>
        </header>

        <div className="problem__row">
          {problemCards.map((card, i) => (
            <article key={card.label} className={`pcard pcard--${i + 1}`}>
              <Editorial slot={card.slot} className="pcard__photo edit--zoom">
                <span className="pcard__index">{String(i + 1).padStart(2, '0')}</span>
              </Editorial>
              <p className="pcard__label">{card.label}</p>
              <blockquote className="pcard__quote">“{card.quote}”</blockquote>
            </article>
          ))}

          <p className="problem__rail" aria-hidden="true">
            Real conversations. Real risks. Real impact.
          </p>
        </div>
      </div>
    </section>
  );
}

const capabilityLabels = [
  'Voice detection',
  'Context analysis',
  'Risk scoring',
  'Request verification',
  'Incident investigation',
];

function HowItWorks() {
  const ref = useReveal<HTMLElement>();
  return (
    <section id="how-it-works" ref={ref} className="process reveal">
      <div className="lwrap process__inner">
        <div className="process__lede">
          <p className="eyebrow eyebrow--light">How {PRODUCT_NAME} works</p>
          <h2 className="process__title">
            From conversation
            <br />
            to confident action.
          </h2>
          <p className="process__body">
            {PRODUCT_NAME} analyses the voice, understands the request, assesses the risk and helps the employee take
            the right action before anything is sent.
          </p>
          <ul className="process__caps">
            {capabilityLabels.map((label) => (
              <li key={label}>{label}</li>
            ))}
          </ul>
        </div>

        <ol className="chain">
          {stages.map((stage, i) => (
            <li key={stage.id} className={`chain__step is-${stage.id}`} style={{ ['--i' as string]: i }}>
              <span className="chain__icon">
                <Icon name={stage.icon} size={30} strokeWidth={1.8} />
              </span>
              <p className="chain__name">{stage.title}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

const caseSlots = ['caseExecutive', 'caseVendor', 'caseAuthority'] as const;
const caseMeta = [
  ['Familiar', 'Financial', 'High', 'Prevented'],
  ['Known contact', 'Payment change', 'High', 'Held'],
  ['Senior manager', 'Process exception', 'High', 'Refused'],
];

function CaseStudies() {
  const ref = useReveal<HTMLElement>();
  return (
    <section id="case-studies" ref={ref} className="cases reveal">
      {caseStudies.map((study, index) => (
        <article key={study.id} className={`cs cs--${index + 1}`}>
          <div className="lwrap cs__grid">
            <Editorial slot={caseSlots[index]} className="cs__photo edit--zoom" />

            <div className="cs__text">
              <p className="cs__number">{study.number}</p>
              <h3 className="cs__title">{study.title}</h3>
              <p className="cs__summary">{study.summary}</p>
              <ol className="cs__flow">
                {study.steps.map((step, i) => (
                  <li key={step} className={i === study.steps.length - 1 ? 'is-final' : ''}>
                    {step}
                  </li>
                ))}
              </ol>
            </div>

            <dl className="cs__evidence">
              {['Voice', 'Request', 'Risk', 'Result'].map((term, i) => (
                <div key={term}>
                  <dt>{term}</dt>
                  <dd className={i === 2 ? 'is-risk' : i === 3 ? 'is-safe' : ''}>{caseMeta[index][i]}</dd>
                </div>
              ))}
            </dl>
          </div>
        </article>
      ))}
    </section>
  );
}

function Benchmark() {
  const ref = useReveal<HTMLElement>();
  return (
    <section id="benchmarks" ref={ref} className="strip reveal">
      <div className="lwrap strip__inner">
        <div className="strip__label">
          <p className="strip__title">Proven impact</p>
          <p className="strip__note">Figures come from our own evaluation set and are published once complete.</p>
        </div>

        <ul className="strip__numbers">
          {metrics.map((m) => (
            <li key={m.label}>
              <span className="strip__value tabular">{m.value}</span>
              <span className="strip__metric">{m.label}</span>
            </li>
          ))}
        </ul>
      </div>
      <p className="strip__rail" aria-hidden="true">
        {benchmark.map((b) => b.metric).join(' · ')}
      </p>
      <p className="strip__disclaimer">{benchmarkNote}</p>
    </section>
  );
}

function FinalCta() {
  const ref = useReveal<HTMLElement>();
  return (
    <section ref={ref} className="cta reveal">
      <Editorial slot="finalCta" className="cta__bleed" />
      <div className="lwrap cta__inner">
        <h2 className="cta__title">
          Trust the conversation.
          <br />
          <em>Verify the action.</em>
        </h2>
        <p className="cta__body">
          Real-time detection of cloned voices, verification of the request itself, and the evidence your security team
          needs afterwards.
        </p>
        <Link to="/login" className="btn btn--primary btn--lg">
          <span>Get started</span>
          <Icon name="arrowRight" size={20} />
        </Link>
      </div>
    </section>
  );
}

export function Landing() {
  const { clearSignOut } = useAuth();
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    document.documentElement.dataset.theme = 'landing';
    clearSignOut();
    if (import.meta.env.DEV) assertUniqueImagery();
  }, [clearSignOut]);

  return (
    <div className={`landing ${reduced ? 'is-still' : ''}`}>
      <Atmosphere />
      <LandingNav />
      <main id="main">
        <Hero />
        <Problem />
        <HowItWorks />
        <CaseStudies />
        <Benchmark />
        <FinalCta />
      </main>
      <footer className="landing-foot">
        <div className="lwrap landing-foot__inner">
          <p>{PRODUCT_NAME} · Smart India Hackathon 2026 prototype · Demonstration data only</p>
          <p className="landing-foot__credit">Photography: Vitaly Gariev / Unsplash</p>
          <Link to="/login" className="landing-foot__link">
            Login
          </Link>
        </div>
      </footer>
    </div>
  );
}
