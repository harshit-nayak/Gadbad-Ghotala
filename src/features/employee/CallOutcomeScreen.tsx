import type { CSSProperties } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { Icon, type IconName } from '../../components/ui/Icon';
import { Pill, type Tone } from '../../components/ui/Pill';
import { incidentStatusLabel, riskLevelLabel } from '../../components/incident/labels';
import { formatInr } from '../../domain/format';
import type { CallOutcome, Incident } from '../../domain/types';
import { useDemo } from '../../state/DemoProvider';

interface OutcomeCopy {
  tone: 'safe' | 'warn';
  icon: IconName;
  chip: { text: string; tone: Tone };
  title: string;
  body: (i: Incident) => string;
  done: (i: Incident) => string[];
  next?: string;
}

const amountOf = (i: Incident) => (i.request.amountInr ? formatInr(i.request.amountInr) : 'Requested');

const outcomeCopy: Record<CallOutcome, OutcomeCopy> = {
  impersonation_confirmed: {
    tone: 'safe',
    icon: 'shieldCheck',
    chip: { text: 'Potential impersonation confirmed', tone: 'risk' },
    title: 'Transfer stopped',
    body: (i) => `${i.claimedIdentity.name} confirmed he didn't make this request, so this is being treated as fraud. The call has been ended.`,
    done: (i) => [
      `${amountOf(i)} transfer blocked`,
      'Security team alerted',
      `Incident #${i.id} created`,
      'Call ended',
      'Organisation-level alert raised',
    ],
    next: "If this number calls or messages you again, including on WhatsApp, don't respond. Security will follow up with you.",
  },
  request_confirmed: {
    tone: 'safe',
    icon: 'check',
    chip: { text: 'Request confirmed', tone: 'safe' },
    title: 'Request confirmed',
    body: (i) => `${i.claimedIdentity.name} confirmed this request. Continue with the standard payment approval process.`,
    done: (i) => [
      'Confirmation recorded',
      `Call logged for Security review as incident #${i.id}, because risk signals were high`,
      `Not used to update ${i.claimedIdentity.name}'s voice profile`,
    ],
  },
  escalated: {
    tone: 'warn',
    icon: 'bell',
    chip: { text: 'Awaiting security review', tone: 'warn' },
    title: 'Security has been notified',
    body: () => 'Keep the transfer on hold. An analyst will contact you about this call.',
    done: (i) => ['Request on hold', `Incident #${i.id} sent to the Security team`, 'Call details shared with the fraud team'],
    next: "Don't make the transfer until Security, or the requester through an official channel, confirms it.",
  },
  ended_unverified: {
    tone: 'warn',
    icon: 'phone',
    chip: { text: 'High risk, not verified', tone: 'risk' },
    title: 'Call ended',
    body: () => "The request wasn't verified, so don't act on it.",
    done: (i) => ['No transfer made', `Incident #${i.id} sent to the Security team`],
    next: 'If the caller reaches out again, verify the request before doing anything.',
  },
};

export function CallOutcomeScreen() {
  const { state } = useDemo();
  const navigate = useNavigate();
  const incident = state.incidents.find((i) => i.live);
  if (!state.outcome || !incident) return null;

  const copy = outcomeCopy[state.outcome];
  const summary: [string, string][] = [
    ['Caller claimed to be', `${incident.claimedIdentity.name}, ${incident.claimedIdentity.roleShort}`],
    ['Request', `${amountOf(incident)} transfer`],
    ['Risk', riskLevelLabel[incident.riskLevel]],
    ['Verification', incident.verification.summary],
    ['Incident', `#${incident.id}, ${incidentStatusLabel[incident.status].toLowerCase()}`],
  ];

  return (
    <div className={`screen outcome outcome--${copy.tone}`}>
      <section className="outcome__hero" aria-live="polite">
        <span className="outcome__icon">
          <Icon name={copy.icon} size={34} className={copy.icon === 'phone' ? 'icon-hangup' : undefined} />
        </span>
        <Pill tone={copy.chip.tone} dot>
          {copy.chip.text}
        </Pill>
        <h2 className="outcome__title">{copy.title}</h2>
        <p className="outcome__body">{copy.body(incident)}</p>
      </section>

      <ul className="outcome__done">
        {copy.done(incident).map((item, index) => (
          <li key={item} style={{ '--i': index } as CSSProperties}>
            <span className="outcome__tick" aria-hidden="true">
              <Icon name="check" size={12} strokeWidth={3} />
            </span>
            {item}
          </li>
        ))}
      </ul>

      {copy.next && (
        <p className="outcome__next">
          <Icon name="message" size={16} />
          {copy.next}
        </p>
      )}

      <dl className="summary">
        {summary.map(([term, value]) => (
          <div key={term} className="summary__row">
            <dt>{term}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      <footer className="screen__footer">
        <Button variant="primary" size="lg" block onClick={() => navigate(`/security/incidents/${incident.id}`)}>
          View incident
        </Button>
      </footer>
    </div>
  );
}
