import { useEffect } from 'react';
import { Avatar } from '../../components/ui/Avatar';
import { Button } from '../../components/ui/Button';
import { Icon, type IconName } from '../../components/ui/Icon';
import { Pill } from '../../components/ui/Pill';
import { RiskRing } from '../../components/viz/RiskRing';
import { Waveform, type WaveTone } from '../../components/viz/Waveform';
import { formatClock, formatInr } from '../../domain/format';
import { useElapsedSeconds } from '../../hooks/useElapsedSeconds';
import { useLiveAnalysis, type LiveAnalysis as Analysis, type LiveSignalReading } from '../../hooks/useLiveAnalysis';
import { incidentService } from '../../services/incidentService';
import { useDemo } from '../../state/DemoProvider';
import { employeeSignalCopy, firstName, type EmployeeStatus } from './signalCopy';
import { PRODUCT_NAME } from '../../app/brand';

const ALERT_DELAY_MS = 1500;

function headline(analysis: Analysis, alerting: boolean) {
  if (analysis.level === 'high') {
    return {
      title: 'This call looks risky',
      body: alerting ? 'Opening your risk alert.' : "Don't act on the request until it is verified.",
    };
  }
  if (analysis.level === 'medium') {
    return { title: 'Some signals look unusual', body: "Keep listening, but don't act on any request yet." };
  }
  if (analysis.progress < 0.25) {
    return { title: 'Checking the call', body: 'Listening to the voice and the conversation.' };
  }
  return { title: 'Nothing unusual yet', body: `${PRODUCT_NAME} is still checking.` };
}

const markerIcon: Partial<Record<EmployeeStatus['tone'], IconName>> = {
  safe: 'check',
  warn: 'alert',
  risk: 'alert',
};

function CheckRow({ reading, claimedFirstName }: { reading: LiveSignalReading; claimedFirstName: string }) {
  const copy = employeeSignalCopy[reading.id];
  if (!copy) return null;

  const status: EmployeeStatus =
    reading.state === 'waiting'
      ? { text: 'Waiting', tone: 'neutral' }
      : reading.state === 'checking'
        ? { text: 'Checking', tone: 'analysis' }
        : copy.status(reading.risk);
  const icon = reading.state === 'settled' ? markerIcon[status.tone] : undefined;

  return (
    <li className={`check check--${reading.state} check--${status.tone}`}>
      <span className="check__marker" aria-hidden="true">
        {reading.state === 'checking' ? (
          <span className="spinner spinner--sm" />
        ) : icon ? (
          <Icon name={icon} size={12} strokeWidth={2.6} />
        ) : (
          <span className="check__dot" />
        )}
      </span>
      <span className="check__text">
        <span className="check__label">{copy.label}</span>
        <span className="check__hint">{copy.hint(claimedFirstName)}</span>
      </span>
      <span className="check__status">{status.text}</span>
      <span className="check__bar" aria-hidden="true">
        <span style={{ transform: `scaleX(${reading.risk / 100})` }} />
      </span>
    </li>
  );
}

export function LiveAnalysis() {
  const { state, actions } = useDemo();
  const call = incidentService.getActiveCall();
  const analysis = useLiveAnalysis();
  const elapsed = useElapsedSeconds(state.acceptedAt);
  const alerting = analysis.complete && analysis.level === 'high';
  const caller = call.claimedIdentity;

  useEffect(() => {
    if (!alerting) return;
    const id = window.setTimeout(actions.showAlert, ALERT_DELAY_MS);
    return () => window.clearTimeout(id);
  }, [alerting, actions]);

  const waveTone: WaveTone = analysis.level === 'high' ? 'risk' : analysis.level === 'medium' ? 'rising' : 'calm';
  const { title, body } = headline(analysis, alerting);
  const endCall = () => actions.resolveCall('ended_unverified', 'none');

  return (
    <div className="screen live">
      <header className="call-strip">
        <Avatar initials={caller.initials} size="sm" />
        <div className="call-strip__who">
          <p className="call-strip__name">{caller.name}</p>
          <p className="call-strip__meta">{caller.roleShort}, {call.metadata.direction} line</p>
        </div>
        <span className="call-strip__timer tabular" aria-label={`Call duration ${formatClock(elapsed)}`}>
          {formatClock(elapsed)}
        </span>
      </header>

      <section className={`risk-panel risk-panel--${analysis.level} ${alerting ? 'risk-panel--alerting' : ''}`}>
        <Waveform label="Live call audio" tone={waveTone} height={64} />
        <div className="risk-panel__body" aria-live="polite">
          <div>
            <p className="risk-panel__label">Call risk</p>
            <p className="risk-panel__title">{title}</p>
            <p className="risk-panel__text">{body}</p>
          </div>
          <RiskRing score={analysis.score} level={analysis.level} size={68} />
        </div>
      </section>

      {analysis.requestDetected && call.request.amountInr && (
        <div className="request-chip" role="status">
          <span className="request-chip__icon">
            <Icon name="money" size={18} />
          </span>
          <span className="request-chip__text">
            <span className="request-chip__label">Request detected</span>
            <span className="request-chip__value">
              {formatInr(call.request.amountInr)} transfer to a new vendor
            </span>
          </span>
          <Pill tone="warn">Urgent</Pill>
        </div>
      )}

      <section className="checks" aria-labelledby="checks-heading">
        <h3 id="checks-heading" className="checks__heading">
          What {PRODUCT_NAME} is checking
        </h3>
        <ul>
          {analysis.readings.map((reading) => (
            <CheckRow key={reading.id} reading={reading} claimedFirstName={firstName(caller.name)} />
          ))}
        </ul>
      </section>

      <footer className="screen__footer">
        <Button variant="danger-outline" block icon="phone" onClick={endCall}>
          End call
        </Button>
      </footer>
    </div>
  );
}
