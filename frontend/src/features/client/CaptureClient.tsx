import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDetectionFeed } from '../../services/detectionFeed';
import { REPORT_THRESHOLD, evidenceFromLiveSession, stageReportEvidence } from '../../services/reportService';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Pill, type Tone } from '../../components/ui/Pill';
import { useToast } from '../../components/ui/Toast';
import {
  clientControlUrl,
  sendClientCommand,
  useClientControl,
  type ClientCommand,
  type ClientLogEntry,
  type ClientState,
} from '../../services/clientControl';
import './client.css';

type Draft = Partial<Pick<ClientState, 'server_url' | 'far_device' | 'near_device' | 'chunk_seconds' | 'process_names' | 'require_speaker'>>;

const bandTone: Record<string, Tone> = { low: 'safe', elevated: 'warn', high: 'risk' };
const sourceLabel: Record<string, string> = { manual: 'started in the client window', auto: 'auto-detected WhatsApp call', web: 'started from this page' };

function statusTone(status: string): Tone {
  if (/streaming/i.test(status)) return 'safe';
  if (/^connected/i.test(status)) return 'analysis';
  if (/connecting/i.test(status)) return 'warn';
  if (/error/i.test(status)) return 'risk';
  return 'neutral';
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="cc-field">
      <span className="cc-field__label">{label}</span>
      {children}
      {hint && <span className="cc-field__hint">{hint}</span>}
    </label>
  );
}

function EventLog({ entries }: { entries: ClientLogEntry[] }) {
  const ref = useRef<HTMLOListElement>(null);
  const pinned = useRef(true);

  useEffect(() => {
    const el = ref.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [entries]);

  if (entries.length === 0) return <p className="muted">No events yet.</p>;
  return (
    <ol
      ref={ref}
      className="cc-log"
      aria-live="polite"
      onScroll={(e) => {
        const el = e.currentTarget;
        pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
      }}
    >
      {entries.map((entry) => (
        <li key={entry.id} className={`cc-log__line cc-log__line--${entry.tag}`}>
          <time className="cc-log__time">{new Date(entry.ts * 1000).toLocaleTimeString([], { hour12: false })}</time>
          <span className="cc-log__text">{entry.text}</span>
        </li>
      ))}
    </ol>
  );
}

export function CaptureClient() {
  const { reachability, state, log } = useClientControl();
  const notify = useToast();
  const [draft, setDraft] = useState<Draft>({});
  const [pending, setPending] = useState<ClientCommand | null>(null);
  const feed = useDetectionFeed();
  const navigate = useNavigate();

  if (reachability !== 'online' || !state) {
    return (
      <div className="client-page page">
        <PageHeader title="Capture client" description="The desktop capture client that records WhatsApp calls on this computer and streams them to the detector." />
        <Panel>
          <div className="cc-offline">
            {reachability === 'checking' ? (
              <p className="muted"><span className="spinner spinner--sm" aria-hidden="true" /> Looking for the capture client…</p>
            ) : (
              <>
                <span className="cc-offline__icon"><Icon name="device" size={24} /></span>
                <p className="cc-offline__title">The capture client isn't running</p>
                <p className="muted">Start it on this computer, and this tab connects on its own:</p>
                <code className="cc-code">.\run_client.ps1</code>
                <p className="subtle">
                  Looking at {clientControlUrl}. An older client without web control needs restarting too.
                </p>
              </>
            )}
          </div>
        </Panel>
      </div>
    );
  }

  const value = <K extends keyof Draft>(key: K) => (draft[key] ?? state[key]) as ClientState[K];
  const edit = (patch: Draft) => setDraft((prev) => ({ ...prev, ...patch }));

  const run = async (command: ClientCommand, payload: Record<string, unknown> = {}, clears: (keyof Draft)[] = []) => {
    setPending(command);
    try {
      await sendClientCommand(command, payload);
      setDraft((prev) => {
        const next = { ...prev };
        clears.forEach((key) => delete next[key]);
        return next;
      });
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err));
    } finally {
      setPending(null);
    }
  };

  const start = () =>
    run(
      'start',
      {
        server_url: value('server_url'),
        far_device: value('far_device'),
        near_device: value('near_device'),
        chunk_seconds: value('chunk_seconds'),
      },
      ['server_url', 'far_device', 'near_device', 'chunk_seconds'],
    );

  const setAutoDetect = (enabled: boolean) =>
    run(
      'auto_detect',
      { enabled, process_names: value('process_names'), require_speaker: value('require_speaker') },
      ['process_names', 'require_speaker'],
    );

  const { stats, risk, running } = state;
  const tick = state.detector_tick;
  // The client's own verdicts carry no window times; the backend feed has the same session with full detail.
  const reportEvidence = risk.value >= REPORT_THRESHOLD && feed.session ? evidenceFromLiveSession(feed.session) : null;

  return (
    <div className="client-page page">
      <PageHeader
        title="Capture client"
        description="The desktop capture client on this computer. Everything here mirrors its window, and changes apply to both."
        actions={
          <Pill tone={statusTone(state.status)} dot={running ? 'live' : true}>
            {state.status}
          </Pill>
        }
      />

      {risk.value >= REPORT_THRESHOLD && (
        <div className="cc-report" role="alert">
          <Icon name="alert" size={20} />
          <div className="cc-report__text">
            <p className="cc-report__title">Risk has reached {risk.value}%</p>
            <p className="muted">
              {reportEvidence
                ? "Don't act on anything the caller asks. Create a report with the analysis so far and see what to do next."
                : 'The web page is not connected to the backend feed, so the analysis details are not available for a report yet.'}
            </p>
          </div>
          <Button
            variant="danger"
            icon="fileText"
            disabled={!reportEvidence}
            onClick={() => {
              if (!reportEvidence) return;
              stageReportEvidence(reportEvidence);
              navigate('/report');
            }}
          >
            Create incident report
          </Button>
        </div>
      )}

      <div className="grid grid--main-side">
        <div className="stack">
          <Panel
            title="Session"
            subtitle={running && state.session_source ? `Recording, ${sourceLabel[state.session_source] ?? state.session_source}` : state.auto_status || 'Not recording'}
            actions={
              running ? (
                <Button variant="danger" icon="close" loading={pending === 'stop'} onClick={() => run('stop')}>
                  Stop
                </Button>
              ) : (
                <Button variant="primary" icon="play" loading={pending === 'start'} onClick={start}>
                  Start
                </Button>
              )
            }
          >
            {state.session_id && (
              <p className="cc-session tabular">
                Session <code className="cc-code">{state.session_id}</code>
              </p>
            )}

            <div className="cc-risk">
              <div className="cc-risk__head">
                <span className="cc-field__label">Impersonation risk (far party)</span>
                <Pill tone={risk.band ? bandTone[risk.band] : 'neutral'}>{risk.label}</Pill>
              </div>
              <span className={`cc-risk__bar cc-risk__bar--${risk.band ?? 'none'}`} aria-hidden="true">
                <span style={{ transform: `scaleX(${risk.value / 100})` }} />
              </span>
              <p className="muted cc-risk__detail">{risk.detail}</p>
            </div>

            <dl className="cc-stats">
              <div><dt>Far chunks sent</dt><dd className="tabular">{stats.far_sent}</dd></div>
              <div><dt>Far acked</dt><dd className="tabular">{stats.far_acked}</dd></div>
              <div><dt>Near chunks sent</dt><dd className="tabular">{stats.near_sent}</dd></div>
              <div><dt>Near acked</dt><dd className="tabular">{stats.near_acked}</dd></div>
            </dl>
          </Panel>

          <Panel title="Verdicts / events" subtitle="The client window's log, live.">
            <EventLog entries={log} />
          </Panel>
        </div>

        <div className="stack">
          <Panel title="Server">
            <Field label="WebSocket URL" hint={state.token_set ? 'An auth token is set in the client window.' : 'Set an auth token in the client window if the backend needs one.'}>
              <input className="cc-input" value={value('server_url')} disabled={running} onChange={(e) => edit({ server_url: e.target.value })} />
            </Field>
          </Panel>

          <Panel
            title="Audio sources"
            actions={
              <Button variant="ghost" icon="refresh" disabled={running} loading={pending === 'refresh_devices'} onClick={() => run('refresh_devices')}>
                Refresh
              </Button>
            }
          >
            <div className="cc-fields">
              <Field label="Far (call audio via loopback)">
                <select className="cc-input" value={value('far_device')} disabled={running} onChange={(e) => edit({ far_device: e.target.value })}>
                  {state.far_devices.length === 0 && <option value="">No loopback devices found</option>}
                  {state.far_devices.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </Field>
              <Field label="Near (your microphone)">
                <select className="cc-input" value={value('near_device')} disabled={running} onChange={(e) => edit({ near_device: e.target.value })}>
                  {state.near_devices.length === 0 && <option value="">No microphones found</option>}
                  {state.near_devices.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </Field>
            </div>
          </Panel>

          <Panel title="Options">
            <div className="cc-fields">
              <Field label="Chunk length (seconds)">
                <input
                  className="cc-input cc-input--short"
                  type="number"
                  min={1}
                  max={10}
                  value={value('chunk_seconds')}
                  disabled={running}
                  onChange={(e) => edit({ chunk_seconds: e.target.value })}
                />
              </Field>

              <label className="cc-check">
                <input type="checkbox" checked={state.auto_detect} disabled={pending === 'auto_detect'} onChange={(e) => setAutoDetect(e.target.checked)} />
                <span>Auto-detect WhatsApp calls and record automatically</span>
              </label>

              <Field label="Process name(s)" hint={state.auto_detect ? 'Turn auto-detect off and on again to apply changes.' : undefined}>
                <input className="cc-input" value={value('process_names')} onChange={(e) => edit({ process_names: e.target.value })} />
              </Field>

              <label className="cc-check">
                <input type="checkbox" checked={value('require_speaker')} onChange={(e) => edit({ require_speaker: e.target.checked })} />
                <span>Require speaker session too (uncheck to test mic-only detection)</span>
              </label>

              <div className="cc-scan">
                <Button variant="secondary" icon="search" loading={pending === 'scan'} onClick={() => run('scan')}>
                  Scan active audio apps
                </Button>
                {tick && (
                  <span className="cc-tick">
                    Right now: <Pill tone={tick.mic ? 'safe' : 'neutral'} dot>mic {tick.mic ? 'active' : 'idle'}</Pill>
                    <Pill tone={tick.speaker ? 'safe' : 'neutral'} dot>speaker {tick.speaker ? 'active' : 'idle'}</Pill>
                  </span>
                )}
              </div>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
