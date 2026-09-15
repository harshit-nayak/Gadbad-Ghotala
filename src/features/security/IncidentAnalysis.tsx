import { useCallback, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { CallAudio } from '../../components/incident/CallAudio';
import { riskColor, signalColor, signalShortLabel } from '../../components/incident/labels';
import { SignalBreakdown } from '../../components/incident/SignalBreakdown';
import { Transcript } from '../../components/incident/Transcript';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { EmptyState, Tabs } from '../../components/ui/Controls';
import { Icon } from '../../components/ui/Icon';
import { speechTurns } from '../../data/callAudio';
import { formatClock, formatInr } from '../../domain/format';
import { riskLevelFor } from '../../domain/risk';
import type { AudioRegion, Incident, SignalId } from '../../domain/types';
import { useElementWidth } from '../../hooks/useElementWidth';
import { useIncidentFromRoute } from './useIncident';

type TabId = 'signals' | 'audio' | 'transcript' | 'context';
const TAB_IDS: TabId[] = ['signals', 'audio', 'transcript', 'context'];

/** One lane per signal showing when across the call it fired. */
function SignalLanes({ incident, position, onSeek }: { incident: Incident; position: number; onSeek: (s: number) => void }) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const duration = incident.metadata.durationSec;
  const labelW = 132;
  const trackW = Math.max(40, width - labelW);
  const laneH = 26;
  const lanes = incident.signals.filter((s) => s.weight > 0).sort((a, b) => b.weight - a.weight);
  const x = (sec: number) => labelW + (sec / duration) * trackW;
  const height = lanes.length * laneH + 20;

  return (
    <div ref={ref} className="lanes">
      <svg width={width} height={height} role="img" aria-label="Detection signal timeline across the call">
        {lanes.map((signal, row) => {
          const y = row * laneH;
          const regions = incident.audioRegions.filter((r) => r.signal === signal.id);
          return (
            <g key={signal.id}>
              <text x={0} y={y + laneH / 2} dy="0.32em" className="lanes__label">
                {signalShortLabel[signal.id]}
              </text>
              <rect x={labelW} y={y + 8} width={trackW} height={10} rx={5} className="lanes__track" />
              {regions.length === 0 ? (
                <rect x={labelW} y={y + 8} width={trackW} height={10} rx={5} fill={signalColor[signal.id]} opacity={signal.conclusive ? 0.08 + signal.risk / 400 : 0.06} />
              ) : (
                regions.map((r, i) => (
                  <rect key={i} x={x(r.start)} y={y + 8} width={Math.max(4, x(r.end) - x(r.start))} height={10} rx={5} fill={signalColor[signal.id]}>
                    <title>{`${formatClock(r.start)}–${formatClock(r.end)} ${r.label}`}</title>
                  </rect>
                ))
              )}
            </g>
          );
        })}
        <line x1={x(position)} x2={x(position)} y1={0} y2={lanes.length * laneH} className="lanes__playhead" />
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <text key={f} x={x(f * duration)} y={height - 4} textAnchor={f === 0 ? 'start' : f === 1 ? 'end' : 'middle'} className="lanes__tick">
            {formatClock(f * duration)}
          </text>
        ))}
        <rect x={labelW} y={0} width={trackW} height={lanes.length * laneH} fill="transparent" style={{ cursor: 'pointer' }}
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            onSeek(((e.clientX - rect.left) / rect.width) * duration);
          }}
        />
      </svg>
      <p className="lanes__note">Solid segments mark where a signal fired. Faint lanes were evaluated across the whole call without a localised finding.</p>
    </div>
  );
}

interface PolicyCheck {
  label: string;
  passed: boolean;
  detail: string;
}

function policyChecks(incident: Incident): PolicyCheck[] {
  const { request } = incident;
  const tactics = request.pressureTactics.join(' ').toLowerCase();
  const flagged = incident.transcript.flatMap((l) => l.flags ?? []).join(' ').toLowerCase();
  return [
    {
      label: 'Counterparty is a known payee',
      passed: !/not in|differs|outside|never/i.test(request.counterpartyNote),
      detail: request.counterpartyNote,
    },
    {
      label: 'Amount within single-approver limit (₹5,00,000)',
      passed: !request.amountInr || request.amountInr <= 500_000,
      detail: request.amountInr ? `${formatInr(request.amountInr)} requested` : 'No amount involved',
    },
    {
      label: 'No approval or verification bypass',
      passed: !/skip|approval|bypass|call-back|no time/.test(`${tactics} ${flagged}`),
      detail: /skip|approval|bypass|call-back|no time/.test(`${tactics} ${flagged}`) ? 'Caller asked to skip a control' : 'Normal process followed',
    },
    {
      label: 'No secrecy or move off official channels',
      passed: !/confidential|between us|whatsapp/.test(`${tactics} ${flagged}`),
      detail: /whatsapp/.test(flagged) ? 'Asked to keep it confidential and move to WhatsApp' : /confidential|between us/.test(`${tactics} ${flagged}`) ? 'Asked to keep it confidential' : 'None detected',
    },
    {
      label: 'Reasonable deadline',
      passed: request.urgency !== 'high',
      detail: `Asked to act ${request.deadline}`,
    },
  ];
}

export function IncidentAnalysis() {
  const incident = useIncidentFromRoute();
  const [params, setParams] = useSearchParams();
  const tab = (TAB_IDS as string[]).includes(params.get('tab') ?? '') ? (params.get('tab') as TabId) : 'signals';
  const [position, setPosition] = useState(0);
  const [region, setRegion] = useState<AudioRegion | null>(null);
  const seek = useCallback((s: number) => setPosition(s), []);
  const turns = useMemo(() => (incident ? speechTurns(incident) : []), [incident]);

  if (!incident) {
    return (
      <div className="page">
        <Panel>
          <EmptyState icon="shield" title="Incident not found">
            <Link to="/security/incidents" className="text-link">Back to incidents</Link>
          </EmptyState>
        </Panel>
      </div>
    );
  }

  const flaggedLines = incident.transcript.filter((l) => l.flags?.length);
  const checks = policyChecks(incident);
  const context = incident.signals.find((s) => s.id === 'contextIntent');
  const activeRegions = incident.audioRegions.filter((r) => position >= r.start && position <= r.end);

  return (
    <div className="page">
      <PageHeader
        eyebrow={
          <>
            <Link to="/security/incidents">Incidents</Link>
            <Icon name="chevronRight" size={14} />
            <Link to={`/security/incidents/${incident.id}`} className="tabular">#{incident.id}</Link>
            <Icon name="chevronRight" size={14} />
            <span>Analysis</span>
          </>
        }
        title="Audio & transcript analysis"
        description={`${incident.claimedIdentity.name} (claimed) to ${incident.receiver.name} · ${incident.metadata.language} · ${incident.metadata.network} · ${formatClock(incident.metadata.durationSec)}`}
        actions={
          <Link to={`/security/incidents/${incident.id}`} className="btn btn--secondary btn--md">
            <Icon name="arrowLeft" size={16} />
            <span>Back to incident</span>
          </Link>
        }
      />

      <Panel>
        <CallAudio incident={incident} position={position} onSeek={seek} height={128} selectedRegion={region} />
        <div className="now-firing" aria-live="polite">
          <span className="now-firing__label">At {formatClock(position)}</span>
          {activeRegions.length ? (
            activeRegions.map((r, i) => (
              <span key={i} className="now-firing__chip">
                <span className="legend__swatch" style={{ background: signalColor[r.signal] }} />
                {signalShortLabel[r.signal]}: {r.label}
              </span>
            ))
          ) : (
            <span className="subtle">No localised signal at this point</span>
          )}
        </div>
      </Panel>

      <Tabs<TabId>
        label="Analysis views"
        active={tab}
        onChange={(id) => setParams({ tab: id }, { replace: true })}
        tabs={[
          { id: 'signals', label: 'Detection signals', count: incident.signals.filter((s) => s.weight > 0).length },
          { id: 'audio', label: 'Audio', count: incident.audioRegions.length },
          { id: 'transcript', label: 'Transcript', count: flaggedLines.length },
          { id: 'context', label: 'Context' },
        ]}
      />

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="stack">
        {tab === 'signals' && (
          <>
            <Panel title="Detection signal timeline" subtitle="Where each signal fired during the call. Click to move the playhead.">
              <SignalLanes incident={incident} position={position} onSeek={seek} />
            </Panel>
            <Panel title="Weighted contributions">
              <SignalBreakdown signals={incident.signals} score={incident.riskScore} />
            </Panel>
          </>
        )}

        {tab === 'audio' && (
          <div className="grid grid--main-side">
            <Panel flush title="Audio segments" subtitle="Speech turns and the signals that fired during each. Select a row to jump to it.">
              <div className="table-wrap">
                <table className="table">
                  <caption className="visually-hidden">Speech segments with findings</caption>
                  <thead><tr><th scope="col">Time</th><th scope="col">Speaker</th><th scope="col" className="num">Length</th><th scope="col">Findings</th></tr></thead>
                  <tbody>
                    {turns.map((t, i) => {
                      // Voice findings describe the caller; only line-level findings apply to the employee's speech.
                      const findings = incident.audioRegions.filter(
                        (r) => r.start < t.end && r.end > t.start && (t.speaker === 'caller' || r.signal === 'backgroundNoise' || r.signal === 'codecArtifacts'),
                      );
                      const active = position >= t.start && position <= t.end;
                      return (
                        <tr key={i} className={`table__row--link ${active ? 'is-current' : ''}`} onClick={() => seek(t.start)}>
                          <td className="tabular muted nowrap">{formatClock(t.start)}</td>
                          <td className="nowrap">{t.speaker === 'caller' ? 'Caller' : incident.receiver.name}</td>
                          <td className="num tabular nowrap">{(t.end - t.start).toFixed(1)} s</td>
                          <td>
                            {findings.length ? (
                              <span className="finding-chips">
                                {findings.map((r, j) => (
                                  <span key={j} className="finding-chip" title={r.label}>
                                    <span className="legend__swatch" style={{ background: signalColor[r.signal] }} />
                                    {signalShortLabel[r.signal]}
                                  </span>
                                ))}
                              </span>
                            ) : (
                              <span className="subtle">None</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Panel>
            <div className="stack">
              <Panel title="Suspicious regions" subtitle="Select a region to jump to it">
                <CallAudioRegions incident={incident} region={region} onSelect={(r) => { setRegion(r); seek(r.start); }} position={position} />
              </Panel>
              <Panel title="Audio conditions">
                <dl className="meta-list">
                  <div><dt>Network</dt><dd>{incident.metadata.network}</dd></div>
                  <div><dt>Codec</dt><dd>{incident.metadata.codec}</dd></div>
                  <div><dt>Audio quality</dt><dd>{incident.metadata.audioQuality}</dd></div>
                  <div><dt>Background noise</dt><dd>{incident.metadata.backgroundNoise}</dd></div>
                  <div><dt>Audio analysed</dt><dd className="tabular">{formatClock(incident.metadata.analysedSec)} of {formatClock(incident.metadata.durationSec)}</dd></div>
                  <div><dt>Caller ID</dt><dd>{incident.metadata.callerIdNote}</dd></div>
                </dl>
              </Panel>
            </div>
          </div>
        )}

        {tab === 'transcript' && (
          <div className="grid grid--main-side">
            <Panel title="Transcript" subtitle="Select a timestamp to jump to that point">
              <Transcript incident={incident} activeAt={position} onSeek={seek} />
            </Panel>
            <Panel title="High-risk phrases">
              <ul className="phrases">
                {flaggedLines.flatMap((line) =>
                  (line.flags ?? []).map((flag) => (
                    <li key={`${line.at}-${flag}`}>
                      <button type="button" className="phrase" onClick={() => seek(line.at)}>
                        <span className="phrase__text">“{flag}”</span>
                        <span className="phrase__time tabular">{formatClock(line.at)}</span>
                      </button>
                    </li>
                  )),
                )}
              </ul>
            </Panel>
          </div>
        )}

        {tab === 'context' && (
          <div className="grid grid--main-side">
            <div className="stack">
              <Panel title="Extracted request">
                <dl className="facts-grid facts-grid--two">
                  <div><dt>Intent</dt><dd>{incident.request.description}</dd></div>
                  <div><dt>Amount</dt><dd className="tabular">{incident.request.amountInr ? formatInr(incident.request.amountInr) : 'None'}</dd></div>
                  <div><dt>Counterparty</dt><dd>{incident.request.counterparty}</dd></div>
                  <div><dt>Deadline</dt><dd>{incident.request.deadline}</dd></div>
                  <div><dt>Authority claimed</dt><dd>{incident.claimedIdentity.role}</dd></div>
                  <div><dt>Requested at</dt><dd className="tabular">{formatClock((new Date(incident.request.requestedAt).getTime() - new Date(incident.metadata.startedAt).getTime()) / 1000)} into call</dd></div>
                </dl>
              </Panel>
              <Panel title="Policy checks" subtitle="Request compared with organisation payment and verification policy">
                <ul className="checks-list">
                  {checks.map((c) => (
                    <li key={c.label} className={`check-row ${c.passed ? 'is-pass' : 'is-fail'}`}>
                      <span className="check-row__icon"><Icon name={c.passed ? 'check' : 'close'} size={13} strokeWidth={2.8} /></span>
                      <span className="check-row__label">{c.label}</span>
                      <span className="check-row__detail">{c.detail}</span>
                    </li>
                  ))}
                </ul>
              </Panel>
            </div>
            <div className="stack">
              {context && (
                <Panel title="Context & intent signal">
                  <p className="context-score">
                    <span className="tabular" style={{ color: riskColor[riskLevelFor(context.risk)] }}>{context.risk}</span>
                    <span className="subtle">/100</span>
                  </p>
                  <p className="muted">{context.reading}</p>
                </Panel>
              )}
              <Panel title="Pressure tactics">
                <ul className="tactics">
                  {incident.request.pressureTactics.map((t) => <li key={t}><Icon name="alert" size={14} />{t}</li>)}
                </ul>
                <h3 className="mini-heading">Evidence in transcript</h3>
                <Transcript incident={incident} onlyFlagged onSeek={seek} />
              </Panel>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function CallAudioRegions({ incident, region, onSelect, position }: { incident: Incident; region: AudioRegion | null; onSelect: (r: AudioRegion) => void; position: number }) {
  const grouped = incident.audioRegions.reduce<Record<string, AudioRegion[]>>((acc, r) => {
    (acc[r.signal] ??= []).push(r);
    return acc;
  }, {});
  return (
    <div className="region-groups">
      {(Object.keys(grouped) as SignalId[]).map((signal) => (
        <div key={signal} className="region-group">
          <p className="region-group__title">
            <span className="legend__swatch" style={{ background: signalColor[signal] }} />
            {signalShortLabel[signal]}
          </p>
          <ul className="region-list">
            {grouped[signal].map((r, i) => (
              <li key={i}>
                <button type="button" className={`region-chip region-chip--compact ${region === r ? 'is-selected' : ''} ${position >= r.start && position <= r.end ? 'is-live' : ''}`} onClick={() => onSelect(r)}>
                  <span className="region-chip__dot" style={{ background: riskColor[r.level] }} />
                  <span className="tabular region-chip__time">{formatClock(r.start)}–{formatClock(r.end)}</span>
                  <span className="region-chip__label">{r.label}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
