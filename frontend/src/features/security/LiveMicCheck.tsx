import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { REPORT_THRESHOLD, stageReportEvidence, type ReportEvidence } from '../../services/reportService';
import { riskLevelTone } from '../../components/incident/labels';
import { Panel } from '../../components/layout/Workspace';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Pill } from '../../components/ui/Pill';
import { RiskRing } from '../../components/viz/RiskRing';
import { formatClock } from '../../domain/format';
import type { RiskLevel } from '../../domain/types';
import { startLiveMic, type LiveMicSession, type LiveSummary, type LiveVerdict } from '../../services/liveMicService';

type Phase = 'idle' | 'starting' | 'live' | 'stopping' | 'done' | 'error';

const labelCopy: Record<string, { text: string; level: RiskLevel }> = {
  likely_real: { text: 'Sounds real', level: 'low' },
  uncertain: { text: 'Unclear', level: 'medium' },
  likely_synthetic: { text: 'Sounds AI-generated', level: 'high' },
};
const levelForBand: Record<string, RiskLevel> = { low: 'low', elevated: 'medium', high: 'high' };
const bandCopy: Record<RiskLevel, string> = {
  low: 'No sign of an AI-generated voice',
  medium: 'Possibly AI-generated: verify the speaker another way',
  high: 'Likely an AI-generated voice',
};

/**
 * Live check from the browser microphone: streams to the backend while the
 * person speaks and shows each verdict as it is scored. The backend does the
 * speech detection (Silero VAD), so silence and pauses are never scored.
 */
export function LiveMicCheck({ onBack }: { onBack: () => void }) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [verdicts, setVerdicts] = useState<LiveVerdict[]>([]);
  const [summary, setSummary] = useState<LiveSummary | null>(null);
  const [sentSeconds, setSentSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const sessionRef = useRef<LiveMicSession | null>(null);
  const navigate = useNavigate();

  // Leaving the page mid-check stops the mic and ends the backend session.
  useEffect(() => () => void sessionRef.current?.stop(), []);

  const start = async () => {
    setPhase('starting');
    setError(null);
    setVerdicts([]);
    setSummary(null);
    setSentSeconds(0);
    try {
      sessionRef.current = await startLiveMic((event) => {
        switch (event.type) {
          case 'level':
            setLevel(event.rms);
            break;
          case 'chunk_sent':
            setSentSeconds(event.seconds);
            break;
          case 'verdict':
            setVerdicts((prev) => [...prev, event.verdict]);
            break;
          case 'summary':
            setSummary(event.summary);
            break;
          case 'error':
            setError(event.message);
            break;
        }
      });
      setStartedAt(Date.now());
      setPhase('live');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setPhase('error');
    }
  };

  const stop = async () => {
    setPhase('stopping');
    setLevel(0);
    await sessionRef.current?.stop();
    sessionRef.current = null;
    setPhase('done');
  };

  const last = verdicts.at(-1);
  const far = summary?.tracks.far;
  const band = summary?.risk.far?.risk_band ?? last?.risk_band;
  const riskLevel: RiskLevel = band ? (levelForBand[band] ?? 'low') : 'low';
  const score = Math.round((summary?.risk.far?.session_risk ?? last?.session_risk ?? 0) * 100);
  const recommendation = summary?.risk.far?.recommendation ?? last?.recommendation ?? null;
  const count = (label: string) => verdicts.filter((v) => v.label === label).length;
  const detector = summary?.detector ?? last?.detector ?? null;
  // Mic level in dBFS mapped onto the meter: -60 dB empty, 0 dB full.
  const meter = level > 0 ? Math.max(0, Math.min(1, (20 * Math.log10(level) + 60) / 60)) : 0;

  const evidence = (): ReportEvidence => ({
    source: 'live_call',
    reference: sessionRef.current?.sessionId ?? `browser-mic-${startedAt ?? Date.now()}`,
    detector: detector ?? 'unknown',
    analysedAt: new Date(startedAt ?? Date.now()).toISOString(),
    riskPercent: score,
    band: band ?? 'low',
    recommendation,
    speechSeconds: far?.speech_seconds ?? last?.speech_seconds ?? 0,
    durationSeconds: sentSeconds,
    counts: { real: count('likely_real'), uncertain: count('uncertain'), synthetic: count('likely_synthetic') },
    windows: verdicts.map((v) => ({
      startMs: v.window_start_ms ?? null,
      endMs: v.window_end_ms ?? null,
      label: v.label,
      pReal: v.p_bonafide,
    })),
  });

  if (phase === 'idle' || phase === 'starting' || (phase === 'error' && verdicts.length === 0)) {
    return (
      <Panel>
        <button type="button" className="audio-back-btn" onClick={onBack}>← Back</button>
        <div className="mic-recorder">
          {error && (
            <div className="mic-recorder__denied" role="alert">
              <Icon name="alert" size={18} />
              <div>
                <strong>Couldn't start the live check.</strong>
                <p>{error}</p>
              </div>
            </div>
          )}
          <div className="mic-recorder__prompt">
            <div className="mic-recorder__icon-wrap"><Icon name="activity" size={26} /></div>
            <p className="mic-recorder__title">Live check from microphone</p>
            <p className="mic-recorder__sub">
              Audio streams to the detection model as you speak, and each stretch of speech is scored within seconds.
              Play the suspect voice near the microphone, or put the call on speaker.
            </p>
            <button type="button" className="btn btn--primary" onClick={() => void start()} disabled={phase === 'starting'}>
              {phase === 'starting'
                ? <><span className="spinner spinner--sm" aria-hidden="true" /> Connecting…</>
                : <><Icon name="activity" size={16} /> Start live check</>}
            </button>
          </div>
        </div>
      </Panel>
    );
  }

  const live = phase === 'live';
  return (
    <>
      <div className="grid grid--main-side">
        <Panel
          title={live ? 'Listening' : phase === 'stopping' ? 'Finishing…' : 'Live check finished'}
          subtitle={`${formatClock(sentSeconds)} streamed`}
          actions={
            live ? (
              <Button variant="primary" onClick={() => void stop()}>Stop</Button>
            ) : phase === 'done' || phase === 'error' ? (
              <Button variant="ghost" icon="refresh" onClick={() => void start()}>Start again</Button>
            ) : null
          }
        >
          <div className="live-mic">
            <div className={`mic-recorder__ring ${live ? '' : 'live-mic__ring--idle'}`} aria-hidden="true">
              {live && <span className="mic-recorder__ring-pulse" />}
              <Icon name="voice" size={22} />
            </div>
            <div className="live-mic__body">
              <div className="live-mic__meter" role="meter" aria-label="Microphone level" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(meter * 100)}>
                <span style={{ transform: `scaleX(${meter})` }} />
              </div>
              <p className="muted">
                {live
                  ? verdicts.length === 0
                    ? 'Speak normally. The first verdict arrives after about 4 seconds of continuous speech; pauses and silence are skipped.'
                    : 'Scoring each stretch of speech as it ends.'
                  : phase === 'stopping'
                    ? 'Scoring the last stretch of speech…'
                    : 'Microphone off.'}
              </p>
            </div>
          </div>
          {error && (
            <p className="audio-error" role="alert">
              <Icon name="alert" size={16} />
              {error}
            </p>
          )}
        </Panel>

        <Panel title="Result" actions={detector && <Pill tone={detector === 'placeholder' ? 'warn' : 'analysis'}>{detector}</Pill>}>
          {verdicts.length === 0 ? (
            <p className="muted">
              {phase === 'done'
                ? `Not enough continuous speech to score. The model needs at least ${far?.utterance_min_seconds ?? 3} seconds of someone speaking without a pause.`
                : 'Waiting for the first stretch of speech to be scored.'}
            </p>
          ) : (
            <>
              <div className="audio-verdict" aria-live="polite">
                <RiskRing score={score} level={riskLevel} size={76} />
                <div>
                  <p className="audio-verdict__title">{bandCopy[riskLevel]}</p>
                  <p className="muted">{live ? 'Updates as each stretch of speech is scored.' : 'Final result for this session.'}</p>
                </div>
              </div>
              <dl className="audio-stats">
                <div><dt>Speech heard</dt><dd className="tabular">{last?.speech_seconds != null ? `${last.speech_seconds.toFixed(1)} s` : '…'}</dd></div>
                <div><dt>Windows scored</dt><dd className="tabular">{verdicts.length}</dd></div>
                <div><dt>Sounded AI-generated</dt><dd className="tabular">{count('likely_synthetic')}</dd></div>
                <div><dt>Unclear</dt><dd className="tabular">{count('uncertain')}</dd></div>
                <div><dt>Sounded real</dt><dd className="tabular">{count('likely_real')}</dd></div>
                <div><dt>Too short to score</dt><dd className="tabular">{far ? `${far.unscored_speech_seconds.toFixed(1)} s` : '…'}</dd></div>
              </dl>
              {recommendation && <p className="audio-recommend">{recommendation}</p>}
              {phase === 'done' && score >= REPORT_THRESHOLD && (
                <div className="audio-report">
                  <p className="muted">This session is at or above the {REPORT_THRESHOLD}% risk threshold.</p>
                  <Button
                    variant="primary"
                    block
                    icon="fileText"
                    onClick={() => {
                      stageReportEvidence(evidence());
                      navigate('/report');
                    }}
                  >
                    Create incident report
                  </Button>
                </div>
              )}
              {detector === 'placeholder' && (
                <p className="audio-error">
                  <Icon name="alert" size={16} />
                  No detection model is loaded on the backend. These scores are a placeholder heuristic.
                </p>
              )}
            </>
          )}
        </Panel>
      </div>

      {verdicts.length > 0 && (
        <Panel flush title="Scored windows" subtitle="Newest first. Each window is up to 4 seconds of one continuous stretch of speech.">
          <div className="table-wrap">
            <table className="table">
              <caption className="visually-hidden">Scored windows</caption>
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Verdict</th>
                  <th scope="col" className="num">P(real)</th>
                  <th scope="col" className="num">Running risk</th>
                  <th scope="col" className="num">Scored in</th>
                  <th scope="col">Note</th>
                </tr>
              </thead>
              <tbody>
                {[...verdicts].reverse().map((v) => {
                  const copy = labelCopy[v.label] ?? { text: v.label, level: 'low' as RiskLevel };
                  return (
                    <tr key={v.sequence}>
                      <td className="tabular">
                        {v.window_start_ms != null && v.window_end_ms != null
                          ? `${formatClock(v.window_start_ms / 1000)}–${formatClock(v.window_end_ms / 1000)}`
                          : `#${v.sequence + 1}`}
                      </td>
                      <td><Pill tone={riskLevelTone[copy.level]}>{copy.text}</Pill></td>
                      <td className="num tabular">{v.p_bonafide.toFixed(3)}</td>
                      <td className="num tabular">{Math.round(v.session_risk * 100)}%</td>
                      <td className="num tabular">{v.latency_ms != null ? `${(v.latency_ms / 1000).toFixed(1)} s` : ''}</td>
                      <td className="muted">{v.padded ? 'Short stretch, repeated to fill the window' : ''}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </>
  );
}
