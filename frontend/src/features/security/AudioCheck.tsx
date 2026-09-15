import { useEffect, useRef, useState, type DragEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { REPORT_THRESHOLD, evidenceFromAudioCheck, stageReportEvidence } from '../../services/reportService';
import { riskColor, riskLevelTone } from '../../components/incident/labels';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Pill } from '../../components/ui/Pill';
import { RiskRing } from '../../components/viz/RiskRing';
import { formatClock } from '../../domain/format';
import type { RiskLevel } from '../../domain/types';
import { useElementWidth } from '../../hooks/useElementWidth';
import {
  analyseAudio,
  decodeToPcm16,
  type AudioCheckSummary,
  type AudioSegment,
  type AudioWindowResult,
} from '../../services/audioCheckService';
import './audioCheck.css';

type Phase = 'idle' | 'decoding' | 'analysing' | 'done' | 'error';

const labelCopy: Record<string, { text: string; level: RiskLevel }> = {
  likely_real: { text: 'Sounds real', level: 'low' },
  uncertain: { text: 'Unclear', level: 'medium' },
  likely_synthetic: { text: 'Sounds AI-generated', level: 'high' },
};
const levelForBand: Record<string, RiskLevel> = { low: 'low', elevated: 'medium', high: 'high' };

const verdictCopy: Record<RiskLevel, { title: string; body: string }> = {
  high: { title: 'Likely an AI-generated voice', body: 'The voice sounded synthetic across sustained stretches of speech.' },
  medium: { title: 'Possibly AI-generated', body: 'Some stretches sounded synthetic or unclear. Verify the speaker another way.' },
  low: { title: 'No sign of an AI-generated voice', body: 'Every scored stretch of speech sounded like a real person.' },
};

const TICK_STEPS_S = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
const formatBytes = (n: number) => (n > 1_048_576 ? `${(n / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

function Timeline({
  durationMs,
  segments,
  windows,
  positionMs,
  onSeek,
}: {
  durationMs: number;
  segments: AudioSegment[];
  windows: AudioWindowResult[];
  positionMs: number;
  onSeek: (ms: number) => void;
}) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const height = 84;
  const x = (ms: number) => (durationMs > 0 ? (ms / durationMs) * width : 0);
  const durationS = durationMs / 1000;
  const step = TICK_STEPS_S.find((s) => durationS / s <= 8) ?? 600;
  const ticks = Array.from({ length: Math.floor(durationS / step) + 1 }, (_, i) => i * step);

  return (
    <div className="audio-timeline" ref={ref}>
      <svg
        width={width}
        height={height}
        role="slider"
        tabIndex={0}
        aria-label="Recording position"
        aria-valuemin={0}
        aria-valuemax={Math.round(durationS)}
        aria-valuenow={Math.round(positionMs / 1000)}
        aria-valuetext={formatClock(positionMs / 1000)}
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          onSeek(((e.clientX - rect.left) / rect.width) * durationMs);
        }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowRight') onSeek(Math.min(durationMs, positionMs + 5000));
          if (e.key === 'ArrowLeft') onSeek(Math.max(0, positionMs - 5000));
        }}
      >
        <text x={0} y={11} className="audio-timeline__lane">Verdict per window</text>
        {windows.map((w) => {
          const level = labelCopy[w.label]?.level ?? 'low';
          return (
            <rect
              key={w.index}
              x={x(w.start_ms)}
              y={16}
              width={Math.max(3, x(w.end_ms) - x(w.start_ms))}
              height={20}
              rx={3}
              style={{ fill: riskColor[level] }}
              className="audio-timeline__window"
            >
              <title>
                {formatClock(w.start_ms / 1000)}–{formatClock(w.end_ms / 1000)}: {labelCopy[w.label]?.text ?? w.label}, P(real) {w.p_bonafide.toFixed(3)}
              </title>
            </rect>
          );
        })}
        <text x={0} y={51} className="audio-timeline__lane">Speech found</text>
        <rect x={0} y={56} width={width} height={8} rx={4} className="audio-timeline__track" />
        {segments.map((s, i) => (
          <rect key={i} x={x(s.start_ms)} y={56} width={Math.max(2, x(s.end_ms) - x(s.start_ms))} height={8} rx={4} className="audio-timeline__speech" />
        ))}
        <line x1={x(positionMs)} x2={x(positionMs)} y1={14} y2={66} className="audio-timeline__playhead" />
        {ticks.map((t) => (
          <text key={t} x={Math.min(width - 16, x(t * 1000))} y={height - 2} className="audio-timeline__tick" textAnchor={t === 0 ? 'start' : 'middle'}>
            {formatClock(t)}
          </text>
        ))}
      </svg>
    </div>
  );
}

export function AudioCheck() {
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [durationMs, setDurationMs] = useState(0);
  const [processedMs, setProcessedMs] = useState(0);
  const [detector, setDetector] = useState<string | null>(null);
  const [windows, setWindows] = useState<AudioWindowResult[]>([]);
  const [summary, setSummary] = useState<AudioCheckSummary | null>(null);
  const [positionMs, setPositionMs] = useState(0);
  const [dragging, setDragging] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => () => abortRef.current?.abort(), []);
  useEffect(() => () => {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
  }, [audioUrl]);

  const check = async (next: File) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setFile(next);
    setAudioUrl(URL.createObjectURL(next));
    setWindows([]);
    setSummary(null);
    setError(null);
    setDetector(null);
    setProcessedMs(0);
    setPositionMs(0);
    setDurationMs(0);
    setPhase('decoding');

    try {
      const { pcm, durationSec } = await decodeToPcm16(next);
      if (controller.signal.aborted) return;
      setDurationMs(durationSec * 1000);
      setPhase('analysing');
      await analyseAudio(
        pcm,
        next.name,
        (event) => {
          if (controller.signal.aborted) return;
          switch (event.type) {
            case 'start':
              setDetector(event.detector);
              break;
            case 'progress':
              setProcessedMs(event.processed_ms);
              break;
            case 'window':
              setWindows((prev) => [...prev, event]);
              break;
            case 'summary':
              setSummary(event);
              setPhase('done');
              break;
            case 'error':
              setError(event.message);
              setPhase('error');
              break;
          }
        },
        controller.signal,
      );
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : String(err));
      setPhase('error');
    }
  };

  const reset = () => {
    abortRef.current?.abort();
    setFile(null);
    setAudioUrl(null);
    setPhase('idle');
    setError(null);
  };

  const seek = (ms: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = ms / 1000;
    setPositionMs(ms);
    void audio.play();
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) void check(dropped);
  };

  const last = windows.at(-1);
  const band = summary?.risk.risk_band ?? last?.risk_band;
  const level: RiskLevel = band ? (levelForBand[band] ?? 'low') : 'low';
  const score = Math.round((summary?.risk.session_risk ?? last?.session_risk ?? 0) * 100);
  const count = (label: string) => windows.filter((w) => w.label === label).length;
  const busy = phase === 'decoding' || phase === 'analysing';
  const progress = durationMs > 0 ? Math.min(1, processedMs / durationMs) : 0;

  return (
    <div className="page">
      <PageHeader
        title="Audio check"
        description="Upload a recording to check whether the voice in it is AI-generated. It is scored by the same model and rules as live calls."
      />

      {!file ? (
        <Panel>
          <div
            className={`audio-drop ${dragging ? 'is-dragging' : ''}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <span className="audio-drop__icon"><Icon name="voice" size={24} /></span>
            <p className="audio-drop__title">Drop a recording here</p>
            <p className="audio-drop__sub">WAV, MP3, M4A, OGG or WebM, up to 30 minutes. Only the speech is scored.</p>
            <Button variant="primary" icon="upload" onClick={() => fileInput.current?.click()}>
              Choose file
            </Button>
            <input
              ref={fileInput}
              type="file"
              className="visually-hidden"
              accept="audio/*,.wav,.mp3,.m4a,.ogg,.opus,.webm,.flac,.aac"
              onChange={(e) => {
                const chosen = e.target.files?.[0];
                if (chosen) void check(chosen);
                e.target.value = '';
              }}
            />
          </div>
        </Panel>
      ) : (
        <>
          <div className="grid grid--main-side">
            <Panel
              title={file.name}
              subtitle={`${formatBytes(file.size)}${durationMs ? `, ${formatClock(durationMs / 1000)}` : ''}`}
              actions={
                <Button variant="ghost" icon="refresh" onClick={reset}>
                  Check another file
                </Button>
              }
            >
              {audioUrl && (
                <audio
                  ref={audioRef}
                  className="audio-player"
                  src={audioUrl}
                  controls
                  onTimeUpdate={(e) => setPositionMs(e.currentTarget.currentTime * 1000)}
                />
              )}
              {durationMs > 0 && (
                <Timeline durationMs={durationMs} segments={summary?.segments ?? []} windows={windows} positionMs={positionMs} onSeek={seek} />
              )}
              {busy && (
                <div className="audio-progress" role="status">
                  <span className="spinner spinner--sm" aria-hidden="true" />
                  <span>
                    {phase === 'decoding'
                      ? 'Decoding the recording in your browser…'
                      : `Analysing ${formatClock(processedMs / 1000)} of ${formatClock(durationMs / 1000)}, ${windows.length} ${windows.length === 1 ? 'window' : 'windows'} scored`}
                  </span>
                  <span className="audio-progress__bar" aria-hidden="true">
                    <span style={{ transform: `scaleX(${phase === 'decoding' ? 0 : progress})` }} />
                  </span>
                </div>
              )}
              {error && (
                <p className="audio-error" role="alert">
                  <Icon name="alert" size={16} />
                  {error}
                </p>
              )}
            </Panel>

            <Panel title="Result" actions={detector && <Pill tone={detector === 'placeholder' ? 'warn' : 'analysis'}>{detector}</Pill>}>
              {windows.length === 0 ? (
                <p className="muted">
                  {phase === 'done'
                    ? `Not enough continuous speech to score. The model needs at least ${summary?.analysis.utterance_min_seconds ?? 3} seconds of someone speaking without a pause.`
                    : phase === 'error'
                      ? 'No result.'
                      : 'Waiting for the first stretch of speech to be scored.'}
                </p>
              ) : (
                <>
                  <div className="audio-verdict">
                    <RiskRing score={score} level={level} size={76} />
                    <div>
                      <p className="audio-verdict__title">{phase === 'done' ? verdictCopy[level].title : 'Analysing…'}</p>
                      <p className="muted">{phase === 'done' ? verdictCopy[level].body : 'The result updates as each stretch of speech is scored.'}</p>
                    </div>
                  </div>
                  <dl className="audio-stats">
                    <div><dt>Speech found</dt><dd className="tabular">{summary ? `${summary.analysis.speech_seconds.toFixed(1)} s` : '…'}</dd></div>
                    <div><dt>Windows scored</dt><dd className="tabular">{windows.length}</dd></div>
                    <div><dt>Sounded AI-generated</dt><dd className="tabular">{count('likely_synthetic')}</dd></div>
                    <div><dt>Unclear</dt><dd className="tabular">{count('uncertain')}</dd></div>
                    <div><dt>Sounded real</dt><dd className="tabular">{count('likely_real')}</dd></div>
                    <div><dt>Too short to score</dt><dd className="tabular">{summary ? `${summary.analysis.unscored_speech_seconds.toFixed(1)} s` : '…'}</dd></div>
                  </dl>
                  {summary && <p className="audio-recommend">{summary.risk.recommendation}</p>}
                  {phase === 'done' && summary && file && score >= REPORT_THRESHOLD && (
                    <div className="audio-report">
                      <p className="muted">This recording is at or above the {REPORT_THRESHOLD}% risk threshold.</p>
                      <Button
                        variant="primary"
                        block
                        icon="fileText"
                        onClick={() => {
                          stageReportEvidence(evidenceFromAudioCheck(file.name, detector ?? 'unknown', durationMs, windows, summary));
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

          {windows.length > 0 && (
            <Panel flush title="Scored windows" subtitle="Each window is up to 4 seconds of one continuous stretch of speech. Click one to listen to it.">
              <div className="table-wrap">
                <table className="table">
                  <caption className="visually-hidden">Scored windows</caption>
                  <thead>
                    <tr>
                      <th scope="col">Time</th>
                      <th scope="col">Verdict</th>
                      <th scope="col" className="num">P(real)</th>
                      <th scope="col" className="num">Running risk</th>
                      <th scope="col">Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    {windows.map((w) => {
                      const copy = labelCopy[w.label] ?? { text: w.label, level: 'low' as RiskLevel };
                      const playing = positionMs >= w.start_ms && positionMs <= w.end_ms;
                      return (
                        <tr key={w.index} className={`table__row--link ${playing ? 'is-current' : ''}`} onClick={() => seek(w.start_ms)}>
                          <td className="tabular">
                            <span className="audio-time">
                              <Icon name="play" size={12} />
                              {formatClock(w.start_ms / 1000)}–{formatClock(w.end_ms / 1000)}
                            </span>
                          </td>
                          <td><Pill tone={riskLevelTone[copy.level]}>{copy.text}</Pill></td>
                          <td className="num tabular">{w.p_bonafide.toFixed(3)}</td>
                          <td className="num tabular">{Math.round(w.session_risk * 100)}%</td>
                          <td className="muted">{w.padded ? 'Short stretch, repeated to fill the window' : ''}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}
