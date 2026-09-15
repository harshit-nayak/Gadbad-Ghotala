import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Pill } from '../../components/ui/Pill';
import { useToast } from '../../components/ui/Toast';
import { downloadFile } from '../../lib/download';
import { useDetectionFeed } from '../../services/detectionFeed';
import { useAuth } from '../../state/AuthProvider';
import {
  REPORT_THRESHOLD,
  clearReport,
  emptyDetails,
  evidenceFromLiveSession,
  isReportable,
  loadProgress,
  loadReport,
  loadStagedEvidence,
  newReportId,
  outcomeLabel,
  paymentLabel,
  platformLabel,
  relationshipLabel,
  requestLabel,
  saveProgress,
  saveReport,
  validateDetails,
  type CallDetails,
  type ReportEvidence,
  type ReportRecord,
  type RequestKind,
} from '../../services/reportService';
import { GUIDANCE_SOURCES, buildGuidance, whenLabel, type GuidanceStep } from './guidance';
import { ReportDocument, reportHtmlFile } from './ReportDocument';
import './report.css';

type Stage = 'details' | 'report' | 'steps';

const stages: { id: Stage; label: string }[] = [
  { id: 'details', label: 'Call details' },
  { id: 'report', label: 'Report' },
  { id: 'steps', label: 'What to do now' },
];

const options = <T extends string>(labels: Record<T, string>) => Object.entries(labels) as [T, string][];

function Stepper({ stage, reportReady, onChange }: { stage: Stage; reportReady: boolean; onChange: (s: Stage) => void }) {
  const current = stages.findIndex((s) => s.id === stage);
  return (
    <ol className="rp-stepper rp-noprint">
      {stages.map((s, i) => {
        const enabled = i === 0 || reportReady;
        return (
          <li key={s.id} className={`rp-stepper__item ${i === current ? 'is-current' : i < current ? 'is-done' : ''}`}>
            <button type="button" disabled={!enabled} onClick={() => onChange(s.id)} aria-current={i === current ? 'step' : undefined}>
              <span className="rp-stepper__num">{i < current ? <Icon name="check" size={12} strokeWidth={3} /> : i + 1}</span>
              {s.label}
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function Field({ label, error, hint, children, wide }: { label: string; error?: string; hint?: string; children: ReactNode; wide?: boolean }) {
  return (
    <label className={`rp-field ${wide ? 'rp-field--wide' : ''} ${error ? 'has-error' : ''}`}>
      <span className="rp-field__label">{label}</span>
      {children}
      {error ? <span className="rp-field__error">{error}</span> : hint && <span className="rp-field__hint">{hint}</span>}
    </label>
  );
}

function EvidenceCard({ evidence }: { evidence: ReportEvidence }) {
  return (
    <Panel title="What the detector found">
      <div className="rp-evidence">
        <p className="rp-evidence__score">{evidence.riskPercent}%</p>
        <p className="muted">synthetic-voice risk, at or above the {REPORT_THRESHOLD}% reporting threshold</p>
      </div>
      <dl className="rp-evidence__list">
        <div><dt>Source</dt><dd>{evidence.source === 'live_call' ? 'Live call' : evidence.reference}</dd></div>
        <div><dt>Model</dt><dd>{evidence.detector}</dd></div>
        <div><dt>Speech analysed</dt><dd className="tabular">{evidence.speechSeconds.toFixed(1)} s</dd></div>
        <div><dt>Sounded AI-generated</dt><dd className="tabular">{evidence.counts.synthetic} of {evidence.windows.length}</dd></div>
      </dl>
      <p className="subtle rp-evidence__note">This is added to the report automatically. Add what only you know about the call.</p>
    </Panel>
  );
}

function DetailsForm({
  evidence,
  initial,
  fromAccount,
  onSubmit,
}: {
  evidence: ReportEvidence;
  initial: CallDetails;
  fromAccount: boolean;
  onSubmit: (d: CallDetails) => void;
}) {
  const [details, setDetails] = useState(initial);
  const [showErrors, setShowErrors] = useState(false);
  const errors = validateDetails(details);
  const set = <K extends keyof CallDetails>(key: K, value: CallDetails[K]) => setDetails((d) => ({ ...d, [key]: value }));
  const toggleRequest = (r: RequestKind) =>
    set('requests', details.requests.includes(r) ? details.requests.filter((x) => x !== r) : [...details.requests, r]);

  const submit = () => {
    if (Object.keys(errors).length) {
      setShowErrors(true);
      return;
    }
    onSubmit(details);
  };
  const err = (key: keyof CallDetails) => (showErrors ? errors[key] : undefined);

  return (
    <div className="grid grid--main-side">
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        noValidate
      >
        <Panel title="About you">
          <div className="rp-form">
            <Field label="Your name" error={err('reporterName')} hint={fromAccount && initial.reporterName ? 'From your Google account.' : undefined}>
              <input className="rp-input" value={details.reporterName} onChange={(e) => set('reporterName', e.target.value)} autoComplete="name" />
            </Field>
            <Field
              label="Phone or email (optional)"
              hint={fromAccount && initial.reporterContact ? 'From your Google account. Add a phone number if you prefer.' : 'So police or your bank can reach you.'}
            >
              <input className="rp-input" value={details.reporterContact} onChange={(e) => set('reporterContact', e.target.value)} />
            </Field>
            <Field label="Organisation (optional)" hint="Clear this if the call wasn't about work." wide>
              <input className="rp-input" value={details.organisation} onChange={(e) => set('organisation', e.target.value)} />
            </Field>
          </div>
        </Panel>

        <Panel title="The call">
          <div className="rp-form">
            <Field label="When did the call happen?" error={err('callTime')}>
              <input className="rp-input" type="datetime-local" value={details.callTime} onChange={(e) => set('callTime', e.target.value)} />
            </Field>
            <Field label="How did they call?">
              <select className="rp-input" value={details.platform} onChange={(e) => set('platform', e.target.value as CallDetails['platform'])}>
                {options(platformLabel).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </Field>
            <Field label="Caller's number or ID" hint="As shown on your phone. Leave blank if hidden.">
              <input className="rp-input" value={details.callerNumber} onChange={(e) => set('callerNumber', e.target.value)} inputMode="tel" />
            </Field>
            <Field label="Who did they claim to be?">
              <select className="rp-input" value={details.relationship} onChange={(e) => set('relationship', e.target.value as CallDetails['relationship'])}>
                {options(relationshipLabel).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </Field>
            <Field label="Name they used (optional)" hint="For example “Rahul, your son” or “SBI fraud department”." wide>
              <input className="rp-input" value={details.claimedName} onChange={(e) => set('claimedName', e.target.value)} />
            </Field>
          </div>

          <fieldset className="rp-choices">
            <legend className="rp-field__label">What did they ask you to do?</legend>
            {options(requestLabel).map(([value, label]) => (
              <label key={value} className="rp-check">
                <input type="checkbox" checked={details.requests.includes(value)} onChange={() => toggleRequest(value)} />
                <span>{label}</span>
              </label>
            ))}
          </fieldset>
        </Panel>

        <Panel title="What happened">
          <fieldset className="rp-choices rp-choices--stack">
            <legend className="visually-hidden">What happened</legend>
            {options(outcomeLabel).map(([value, label]) => (
              <label key={value} className="rp-check">
                <input type="radio" name="outcome" checked={details.outcome === value} onChange={() => set('outcome', value)} />
                <span>{label}</span>
              </label>
            ))}
          </fieldset>

          {details.outcome === 'sent_money' && (
            <div className="rp-form rp-form--money">
              <Field label="Amount sent (₹)" error={err('amountInr')}>
                <input className="rp-input" type="number" min={1} inputMode="numeric" value={details.amountInr} onChange={(e) => set('amountInr', e.target.value)} />
              </Field>
              <Field label="Payment method">
                <select className="rp-input" value={details.paymentMethod} onChange={(e) => set('paymentMethod', e.target.value as CallDetails['paymentMethod'])}>
                  {options(paymentLabel).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </Field>
              <Field label="Transaction ID or UTR (optional)" hint="From the payment receipt or bank SMS." wide>
                <input className="rp-input" value={details.transactionRef} onChange={(e) => set('transactionRef', e.target.value)} />
              </Field>
            </div>
          )}

          <Field label="What did the caller say? (optional)" hint="Their story, any names, accounts or links they gave." wide>
            <textarea className="rp-input rp-textarea" rows={5} value={details.notes} onChange={(e) => set('notes', e.target.value)} />
          </Field>
        </Panel>

        {showErrors && Object.keys(errors).length > 0 && (
          <p className="rp-alert" role="alert">
            <Icon name="alert" size={16} /> Fill in the highlighted fields to create the report.
          </p>
        )}
        <div className="rp-actions">
          <Button type="submit" variant="primary" size="lg" icon="fileText">
            Create report
          </Button>
        </div>
      </form>

      <div className="stack">
        <EvidenceCard evidence={evidence} />
      </div>
    </div>
  );
}

function Tutorial({ steps, onBackToReport, onStartOver }: { steps: GuidanceStep[]; onBackToReport: () => void; onStartOver: () => void }) {
  const [index, setIndex] = useState(0);
  const [done, setDone] = useState<Record<string, boolean>>(loadProgress);
  const finished = index >= steps.length;
  const step = steps[Math.min(index, steps.length - 1)];

  useEffect(() => saveProgress(done), [done]);
  useEffect(() => window.scrollTo({ top: 0, behavior: 'smooth' }), [index]);

  const key = (s: GuidanceStep, i: number) => `${s.id}:${i}`;
  const stepComplete = (s: GuidanceStep) => s.actions.every((_, i) => done[key(s, i)]);
  const completed = steps.filter(stepComplete).length;

  return (
    <div className="rp-tutorial">
      <aside className="rp-tutorial__nav">
        <p className="rp-tutorial__progress">
          <span className="tabular">{completed} of {steps.length}</span> steps done
        </p>
        <span className="rp-bar" aria-hidden="true"><span style={{ transform: `scaleX(${completed / steps.length})` }} /></span>
        <ol>
          {steps.map((s, i) => (
            <li key={s.id}>
              <button type="button" className={`rp-navstep ${i === index ? 'is-current' : ''} ${stepComplete(s) ? 'is-done' : ''}`} onClick={() => setIndex(i)}>
                <span className="rp-navstep__num">{stepComplete(s) ? <Icon name="check" size={12} strokeWidth={3} /> : i + 1}</span>
                <span>
                  <span className="rp-navstep__title">{s.title}</span>
                  <span className={`rp-when rp-when--${s.when}`}>{whenLabel[s.when]}</span>
                </span>
              </button>
            </li>
          ))}
          <li>
            <button type="button" className={`rp-navstep ${finished ? 'is-current' : ''}`} onClick={() => setIndex(steps.length)}>
              <span className="rp-navstep__num"><Icon name="shieldCheck" size={12} /></span>
              <span className="rp-navstep__title">Finish</span>
            </button>
          </li>
        </ol>
      </aside>

      {finished ? (
        <Panel className="rp-card">
          <span className="rp-card__icon rp-card__icon--safe"><Icon name="shieldCheck" size={26} /></span>
          <h2 className="rp-card__title">{completed === steps.length ? "You've done everything on the list" : 'Nearly there'}</h2>
          <p className="muted">
            {completed === steps.length
              ? 'Keep the report and your acknowledgement numbers somewhere safe. If the caller contacts you again, don\'t engage; add the new details to your complaint.'
              : `${steps.length - completed} ${steps.length - completed === 1 ? 'step still has' : 'steps still have'} unchecked items. Anything marked “Do this now” matters most.`}
          </p>
          <ul className="rp-summary">
            {steps.map((s, i) => (
              <li key={s.id} className={stepComplete(s) ? 'is-done' : ''}>
                <Icon name={stepComplete(s) ? 'check' : 'clock'} size={14} />
                <button type="button" className="rp-link" onClick={() => setIndex(i)}>{s.title}</button>
              </li>
            ))}
          </ul>
          <div className="rp-sources">
            <p className="rp-field__label">Sources for this guidance</p>
            <ul>
              {GUIDANCE_SOURCES.map((s) => (
                <li key={s.href}><a href={s.href} target="_blank" rel="noreferrer">{s.label} <Icon name="external" size={12} /></a></li>
              ))}
            </ul>
          </div>
          <div className="rp-actions rp-actions--split">
            <Button variant="secondary" icon="fileText" onClick={onBackToReport}>Back to the report</Button>
            <Button variant="ghost" icon="refresh" onClick={onStartOver}>Start a new report</Button>
          </div>
        </Panel>
      ) : (
        <Panel className={`rp-card ${step.when === 'now' ? 'rp-card--urgent' : ''}`}>
          <p className="rp-card__eyebrow">
            Step {index + 1} of {steps.length}
            <span className={`rp-when rp-when--${step.when}`}>{whenLabel[step.when]}</span>
          </p>
          <h2 className="rp-card__title">{step.title}</h2>
          <p className="rp-card__summary">{step.summary}</p>

          <ul className="rp-todo">
            {step.actions.map((action, i) => (
              <li key={i}>
                <label className="rp-check rp-check--todo">
                  <input
                    type="checkbox"
                    checked={!!done[key(step, i)]}
                    onChange={(e) => setDone((d) => ({ ...d, [key(step, i)]: e.target.checked }))}
                  />
                  <span>{action}</span>
                </label>
              </li>
            ))}
          </ul>

          {step.links && (
            <div className="rp-links">
              {step.links.map((l) => (
                <a key={l.href} className={`btn btn--md ${step.when === 'now' ? 'btn--danger' : 'btn--secondary'}`} href={l.href} target={l.href.startsWith('tel:') ? undefined : '_blank'} rel="noreferrer">
                  <Icon name={l.href.startsWith('tel:') ? 'phone' : 'external'} size={18} />
                  <span>{l.label}</span>
                </a>
              ))}
            </div>
          )}

          <div className="rp-actions rp-actions--split">
            <Button variant="ghost" icon="chevronLeft" disabled={index === 0} onClick={() => setIndex((i) => i - 1)}>Back</Button>
            <Button variant="primary" onClick={() => setIndex((i) => i + 1)}>
              {index === steps.length - 1 ? 'Finish' : 'Next step'}
            </Button>
          </div>
        </Panel>
      )}
    </div>
  );
}

export function ReportPage() {
  const feed = useDetectionFeed();
  const notify = useToast();
  const { user } = useAuth();
  const reporter = { name: user?.user_metadata?.full_name ?? user?.user_metadata?.name, email: user?.email };
  const [record, setRecord] = useState<ReportRecord | null>(loadReport);
  const [staged, setStaged] = useState<ReportEvidence | null>(() => loadReport()?.evidence ?? loadStagedEvidence());
  const [stage, setStage] = useState<Stage>(() => (loadReport() ? 'report' : 'details'));

  // Opened directly during a high-risk live call: report on that call.
  const liveEvidence = feed.session ? evidenceFromLiveSession(feed.session) : null;
  const evidence = staged ?? (isReportable(liveEvidence) ? liveEvidence : null);

  const steps = useMemo(() => (record ? buildGuidance(record.details) : []), [record]);

  const go = (next: Stage) => {
    setStage(next);
    window.scrollTo({ top: 0 });
  };

  const create = (details: CallDetails) => {
    if (!evidence) return;
    const next: ReportRecord = {
      id: record?.id ?? newReportId(),
      generatedAt: new Date().toISOString(),
      details,
      evidence,
    };
    saveReport(next);
    setRecord(next);
    setStaged(evidence);
    go('report');
  };

  const startOver = () => {
    clearReport();
    setRecord(null);
    setStaged(null);
    go('details');
  };

  const download = () => {
    if (!record) return;
    const ok = downloadFile(`${record.id}-incident-report.html`, reportHtmlFile(record), 'text/html');
    notify(ok ? 'Report downloaded' : 'Download failed. Use Print and save as PDF instead.');
  };

  return (
    <div className="rp-page page">
      <div className="rp-noprint">
        <PageHeader
          eyebrow={<Pill tone="risk" dot>High risk call</Pill>}
          title="Incident report"
          description="Add a few details about the call. They're combined with the voice analysis into a report you can give to police, your bank or your security team, followed by the steps to take now."
        />
      </div>

      {!evidence ? (
        <Panel>
          <div className="rp-empty">
            <span className="rp-card__icon"><Icon name="fileText" size={24} /></span>
            <p className="rp-card__title">No high-risk call to report yet</p>
            <p className="muted">
              Reports are created when the detector scores a call at {REPORT_THRESHOLD}% risk or higher: during a live call, from the Capture client
              tab, or after checking a recording.
            </p>
            <div className="rp-actions rp-actions--center">
              <Link className="btn btn--md btn--primary" to="/security/audio"><Icon name="voice" size={18} /><span>Check a recording</span></Link>
              <Link className="btn btn--md btn--secondary" to="/client"><Icon name="device" size={18} /><span>Capture client</span></Link>
            </div>
          </div>
        </Panel>
      ) : (
        <>
          <Stepper stage={stage} reportReady={!!record} onChange={go} />

          {stage === 'details' && (
            <DetailsForm key={record?.id ?? 'new'} evidence={evidence} initial={record?.details ?? emptyDetails(evidence, reporter)} fromAccount={!!user} onSubmit={create} />
          )}

          {stage === 'report' && record && (
            <>
              <div className="rp-toolbar rp-noprint">
                <Button variant="ghost" icon="chevronLeft" onClick={() => go('details')}>Edit details</Button>
                <div className="rp-toolbar__right">
                  <Button variant="secondary" icon="printer" onClick={() => window.print()}>Print or save as PDF</Button>
                  <Button variant="secondary" icon="download" onClick={download}>Download</Button>
                  <Button variant="primary" icon="arrowRight" onClick={() => go('steps')}>What to do now</Button>
                </div>
              </div>
              <ReportDocument record={record} steps={steps} />
            </>
          )}

          {stage === 'steps' && record && <Tutorial steps={steps} onBackToReport={() => go('report')} onStartOver={startOver} />}
        </>
      )}
    </div>
  );
}
