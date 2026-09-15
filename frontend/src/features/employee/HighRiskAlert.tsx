import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { Pill } from '../../components/ui/Pill';
import { formatClock, formatInr } from '../../domain/format';
import { recommendationFor, type Recommendation } from '../../domain/risk';
import { useElapsedSeconds } from '../../hooks/useElapsedSeconds';
import { useNavigate } from 'react-router-dom';
import { isLiveFeed, readSession, useDetectionFeed } from '../../services/detectionFeed';
import { REPORT_THRESHOLD, evidenceFromLiveSession, stageReportEvidence } from '../../services/reportService';
import { incidentService } from '../../services/incidentService';
import { useDemo } from '../../state/DemoProvider';
import { firstName } from './signalCopy';
import { PRODUCT_NAME } from '../../app/brand';

const recommendationCopy: Record<Recommendation, { title: string; body: (name: string) => string }> = {
  stop: {
    title: 'Verify before proceeding',
    body: (name) => `Don't make the transfer yet. Ask ${name} to confirm this request through ${PRODUCT_NAME} first.`,
  },
  verify: {
    title: 'Verify before acting',
    body: (name) => `Confirm the request with ${name} through ${PRODUCT_NAME} before you act on it.`,
  },
  continue: {
    title: 'Safe to continue',
    body: () => 'No action needed. Follow your usual process.',
  },
};

export function HighRiskAlert() {
  const { state, actions } = useDemo();
  const call = incidentService.getActiveCall();
  const elapsed = useElapsedSeconds(state.acceptedAt);
  const feed = useDetectionFeed();
  const { claimedIdentity: caller, request } = call;

  // From the backend, only the voice was analysed: no request or urgency was detected, so none is shown.
  const live = isLiveFeed(feed) && feed.session !== null;
  const readout = live ? readSession(feed.session) : null;
  const recommendation = recommendationFor(readout?.level ?? call.riskLevel, true);
  const advice = recommendationCopy[recommendation];
  const reasons = readout?.reasons.length ? readout.reasons : call.reasons;
  const navigate = useNavigate();
  const reportEvidence = live && feed.session && readout && readout.score >= REPORT_THRESHOLD ? evidenceFromLiveSession(feed.session) : null;
  const openReport = () => {
    if (!reportEvidence) return;
    stageReportEvidence(reportEvidence);
    navigate('/report');
  };

  return (
    <div className="screen alert">
      <section className="alert__hero" role="alert">
        <div className="alert__hero-top">
          <span className="alert__badge">
            <Icon name="alert" size={24} />
          </span>
        </div>
        <p className="alert__level">HIGH RISK</p>
        <h2 className="alert__title">Possible voice impersonation detected</h2>
        <p className="alert__lead">
          This caller may not be {caller.name}. The call is still connected ({formatClock(elapsed)}).
        </p>
      </section>

      <dl className="facts">
        <div className="facts__row">
          <dt>Caller claims to be</dt>
          <dd>
            <strong>{caller.name}</strong>
            {caller.role}
          </dd>
        </div>
        {readout ? (
          <div className="facts__row">
            <dt>Synthetic voice risk</dt>
            <dd>
              <strong className="tabular">{readout.score}%</strong>
              {readout.synthetic} of {readout.windows} speech windows sounded computer-generated
            </dd>
          </div>
        ) : (
          <>
            <div className="facts__row">
              <dt>Request</dt>
              <dd>
                <strong>{request.amountInr ? `${formatInr(request.amountInr)} transfer` : request.description}</strong>
                To an external vendor, {request.counterparty}. {request.counterpartyNote}.
              </dd>
            </div>
            <div className="facts__row">
              <dt>Urgency</dt>
              <dd>
                <Pill tone="risk">High</Pill>
                Asked to pay {request.deadline}
              </dd>
            </div>
          </>
        )}
      </dl>

      <section>
        <h3 className="section-heading">Why was this flagged?</h3>
        <ul className="reasons">
          {reasons.map((reason) => (
            <li key={reason}>
              <Icon name="alert" size={14} />
              {reason}
            </li>
          ))}
        </ul>
      </section>

      <section className="recommend">
        <span className="recommend__icon">
          <Icon name="shield" size={20} />
        </span>
        <div>
          <p className="recommend__label">Recommended action</p>
          <h3 className="recommend__title">{advice.title}</h3>
          <p className="recommend__body">{readout?.recommendation ?? advice.body(firstName(caller.name))}</p>
        </div>
      </section>

      <footer className="screen__footer">
        <Button variant="primary" size="lg" block icon="shieldCheck" onClick={actions.startVerify}>
          Verify request
        </Button>
        {reportEvidence && (
          <Button variant="secondary" block icon="fileText" onClick={openReport}>
            Create incident report
          </Button>
        )}
        <Button variant="danger-outline" block icon="phone" onClick={() => actions.resolveCall('ended_unverified', 'none')}>
          End call
        </Button>
      </footer>
    </div>
  );
}
