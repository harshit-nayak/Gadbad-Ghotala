import { formatClock } from '../../domain/format';
import {
  REPORT_THRESHOLD,
  formatLocalDateTime,
  outcomeLabel,
  paymentLabel,
  platformLabel,
  relationshipLabel,
  requestLabel,
  summarise,
  verdictLabel,
  type ReportRecord,
} from '../../services/reportService';
import { whenLabel, type GuidanceStep } from './guidance';

/**
 * The report itself. Styled with its own fixed, paper-like stylesheet (not
 * the app theme) so the on-screen view, the print-out and the downloaded HTML
 * file look the same.
 */
export const REPORT_DOC_CSS = `
.rpd { --ink:#1b1d24; --muted:#5b6070; --line:#e3e5ec; --soft:#f5f6f9; --risk:#c0392b; --warn:#b9770e; --safe:#1e8449;
  max-width: 860px; margin: 0 auto; padding: 40px 44px; background:#fff; color:var(--ink);
  font: 14px/1.55 system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; border:1px solid var(--line); border-radius:14px; }
.rpd h1 { margin:0; font-size:22px; line-height:1.25; }
.rpd h2 { margin:28px 0 10px; padding-bottom:6px; border-bottom:1px solid var(--line); font-size:15px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
.rpd p { margin:0 0 8px; }
.rpd__head { display:flex; justify-content:space-between; gap:24px; align-items:flex-start; }
.rpd__meta { color:var(--muted); font-size:12.5px; text-align:right; white-space:nowrap; }
.rpd__meta strong { display:block; color:var(--ink); font-size:14px; }
.rpd__verdict { display:flex; gap:20px; align-items:center; margin-top:22px; padding:16px 18px; border-radius:12px; background:#fdf0ee; border:1px solid #f2c4bd; }
.rpd__score { font-size:36px; font-weight:700; color:var(--risk); line-height:1; }
.rpd__score small { display:block; margin-top:4px; font-size:11px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }
.rpd__grid { display:grid; grid-template-columns: 190px 1fr; gap:6px 16px; margin:0; }
.rpd__grid dt { color:var(--muted); }
.rpd__grid dd { margin:0; font-weight:600; }
.rpd__chips { display:flex; flex-wrap:wrap; gap:6px; margin:0; padding:0; list-style:none; }
.rpd__chips li { padding:2px 10px; border-radius:999px; background:#fdf0ee; border:1px solid #f2c4bd; color:var(--risk); font-size:12.5px; font-weight:600; }
.rpd__stats { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:0 0 14px; }
.rpd__stats div { padding:10px 12px; border-radius:10px; background:var(--soft); }
.rpd__stats dt { color:var(--muted); font-size:12px; }
.rpd__stats dd { margin:0; font-size:18px; font-weight:700; }
.rpd__timeline { position:relative; height:22px; margin:6px 0 4px; border-radius:6px; background:var(--soft); overflow:hidden; }
.rpd__timeline span { position:absolute; top:3px; bottom:3px; border-radius:3px; }
.rpd__axis { display:flex; justify-content:space-between; color:var(--muted); font-size:11px; }
.rpd table { width:100%; border-collapse:collapse; margin-top:12px; font-size:13px; }
.rpd th, .rpd td { padding:6px 8px; border-bottom:1px solid var(--line); text-align:left; }
.rpd th { color:var(--muted); font-weight:600; font-size:12px; }
.rpd .num { text-align:right; font-variant-numeric:tabular-nums; }
.rpd__label--likely_synthetic { color:var(--risk); font-weight:700; }
.rpd__label--uncertain { color:var(--warn); font-weight:600; }
.rpd__label--likely_real { color:var(--safe); }
.rpd__steps { margin:0; padding-left:20px; }
.rpd__steps li { margin-bottom:4px; }
.rpd__when { display:inline-block; margin-left:6px; padding:0 7px; border-radius:999px; background:var(--soft); color:var(--muted); font-size:11px; font-weight:600; }
.rpd__when--now { background:#fdf0ee; color:var(--risk); }
.rpd__note { padding:12px 14px; border-radius:10px; background:var(--soft); color:var(--muted); font-size:12.5px; }
.rpd__sign { display:grid; grid-template-columns:1fr 1fr; gap:32px; margin-top:36px; }
.rpd__sign div { padding-top:28px; border-top:1px solid var(--ink); color:var(--muted); font-size:12px; }
@media (max-width: 640px) { .rpd { padding:24px 18px; } .rpd__head { flex-direction:column; } .rpd__meta { text-align:left; }
  .rpd__grid { grid-template-columns:1fr; } .rpd__stats { grid-template-columns:repeat(2,1fr); } }
@media print { .rpd { border:0; border-radius:0; padding:0; max-width:none; } .rpd table, .rpd__verdict { break-inside:avoid; } }
`;

const labelColor: Record<string, string> = { likely_synthetic: '#c0392b', uncertain: '#b9770e', likely_real: '#1e8449' };

export function ReportDocument({ record, steps }: { record: ReportRecord; steps: GuidanceStep[] }) {
  const { details, evidence } = record;
  const span = evidence.durationSeconds ?? Math.max(1, ...evidence.windows.map((w) => (w.endMs ?? 0) / 1000));
  const pct = (ms: number | null) => `${Math.min(100, Math.max(0, ((ms ?? 0) / 1000 / span) * 100))}%`;
  const redFlags = [
    ...details.requests.map((r) => requestLabel[r]),
    ...(evidence.counts.synthetic > 0 ? [`${evidence.counts.synthetic} AI-sounding stretches of speech`] : []),
    ...(details.relationship !== 'unknown' ? [`Claimed to be a ${relationshipLabel[details.relationship].toLowerCase()}`] : []),
  ];

  return (
    <div id="gg-report">
      <style>{REPORT_DOC_CSS}</style>
      <article className="rpd">
        <header className="rpd__head">
          <div>
            <h1>Suspected AI voice impersonation: incident report</h1>
            <p style={{ color: '#5b6070', marginTop: 6 }}>Prepared by the person who received the call, with automated voice analysis.</p>
          </div>
          <p className="rpd__meta">
            <strong>{record.id}</strong>
            Generated {new Date(record.generatedAt).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}
          </p>
        </header>

        <section className="rpd__verdict">
          <p className="rpd__score">
            {evidence.riskPercent}%<small>Synthetic-voice risk</small>
          </p>
          <p style={{ margin: 0 }}>{summarise(record)}</p>
        </section>

        <h2>Call details</h2>
        <dl className="rpd__grid">
          <dt>Reported by</dt>
          <dd>{details.reporterName}{details.reporterContact.trim() ? `, ${details.reporterContact.trim()}` : ''}</dd>
          {details.organisation.trim() && (
            <>
              <dt>Organisation</dt>
              <dd>{details.organisation.trim()}</dd>
            </>
          )}
          <dt>Date and time of call</dt>
          <dd>{formatLocalDateTime(details.callTime)}</dd>
          <dt>Call type</dt>
          <dd>{platformLabel[details.platform]}</dd>
          <dt>Caller's number or ID</dt>
          <dd>{details.callerNumber.trim() || 'Not known'}</dd>
          <dt>Caller claimed to be</dt>
          <dd>{details.claimedName.trim() ? `${details.claimedName.trim()}, ${relationshipLabel[details.relationship]}` : relationshipLabel[details.relationship]}</dd>
          <dt>What happened</dt>
          <dd>{outcomeLabel[details.outcome]}</dd>
        </dl>

        {details.outcome === 'sent_money' && (
          <>
            <h2>Money lost</h2>
            <dl className="rpd__grid">
              <dt>Amount</dt>
              <dd>₹{Number(details.amountInr).toLocaleString('en-IN')}</dd>
              <dt>Payment method</dt>
              <dd>{paymentLabel[details.paymentMethod]}</dd>
              <dt>Transaction ID / UTR</dt>
              <dd>{details.transactionRef.trim() || 'Not provided'}</dd>
            </dl>
          </>
        )}

        {redFlags.length > 0 && (
          <>
            <h2>Warning signs</h2>
            <ul className="rpd__chips">
              {redFlags.map((flag) => <li key={flag}>{flag}</li>)}
            </ul>
          </>
        )}

        {details.notes.trim() && (
          <>
            <h2>What was said</h2>
            <p style={{ whiteSpace: 'pre-wrap' }}>{details.notes.trim()}</p>
          </>
        )}

        <h2>Voice analysis</h2>
        <dl className="rpd__grid" style={{ marginBottom: 14 }}>
          <dt>Source</dt>
          <dd>{evidence.source === 'live_call' ? 'Recorded live during the call' : `Uploaded recording: ${evidence.reference}`}</dd>
          {evidence.source === 'live_call' && (
            <>
              <dt>Analysis session</dt>
              <dd style={{ fontFamily: 'ui-monospace, Consolas, monospace', fontWeight: 500 }}>{evidence.reference}</dd>
            </>
          )}
          <dt>Detection model</dt>
          <dd>{evidence.detector}</dd>
          <dt>Risk band</dt>
          <dd>{evidence.band} (report threshold {REPORT_THRESHOLD}%)</dd>
        </dl>
        <dl className="rpd__stats">
          <div><dt>Speech analysed</dt><dd>{evidence.speechSeconds.toFixed(1)} s</dd></div>
          <div><dt>Sounded AI-generated</dt><dd style={{ color: '#c0392b' }}>{evidence.counts.synthetic}</dd></div>
          <div><dt>Unclear</dt><dd>{evidence.counts.uncertain}</dd></div>
          <div><dt>Sounded real</dt><dd>{evidence.counts.real}</dd></div>
        </dl>

        <div className="rpd__timeline" aria-label="Where in the call each analysed stretch was">
          {evidence.windows.map((w, i) => (
            <span key={i} style={{ left: pct(w.startMs), width: `max(3px, calc(${pct(w.endMs)} - ${pct(w.startMs)}))`, background: labelColor[w.label] ?? '#8a8f9c' }} />
          ))}
        </div>
        <div className="rpd__axis">
          <span>00:00</span>
          <span>{formatClock(span)}</span>
        </div>

        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Time in {evidence.source === 'live_call' ? 'call' : 'recording'}</th>
              <th>Model verdict</th>
              <th className="num">P(real)</th>
            </tr>
          </thead>
          <tbody>
            {evidence.windows.map((w, i) => (
              <tr key={i}>
                <td>{i + 1}</td>
                <td>{w.startMs != null && w.endMs != null ? `${formatClock(w.startMs / 1000)}–${formatClock(w.endMs / 1000)}` : 'n/a'}</td>
                <td className={`rpd__label--${w.label}`}>{verdictLabel[w.label] ?? w.label}</td>
                <td className="num">{w.pReal != null ? w.pReal.toFixed(3) : 'n/a'}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h2>Recommended next steps</h2>
        <ol className="rpd__steps">
          {steps.map((step) => (
            <li key={step.id}>
              {step.title}
              <span className={`rpd__when rpd__when--${step.when}`}>{whenLabel[step.when]}</span>
            </li>
          ))}
        </ol>
        <p style={{ marginTop: 10 }}>
          Cyber crime helpline <strong>1930</strong> · cybercrime.gov.in · Sanchar Saathi (Chakshu): sancharsaathi.gov.in
        </p>

        <h2>About this analysis</h2>
        <p className="rpd__note">
          The risk score is the output of a machine-learning voice model. It indicates that the caller's voice has characteristics of AI-generated
          speech; it is not proof on its own, and its thresholds have not been independently calibrated. Only stretches of at least 3 seconds of
          continuous speech are scored. Keep the original recording, call log and messages as primary evidence.
        </p>

        <div className="rpd__sign">
          <div>Signature of person reporting</div>
          <div>Received by (officer / bank / security team)</div>
        </div>
      </article>
    </div>
  );
}

/** A standalone HTML file of the rendered report, for download. */
export function reportHtmlFile(record: ReportRecord): string {
  const body = document.getElementById('gg-report')?.innerHTML ?? '';
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${record.id} incident report</title><style>body{margin:0;padding:24px;background:#eef0f4}</style></head><body>${body}</body></html>`;
}
