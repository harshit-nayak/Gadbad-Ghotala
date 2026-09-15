import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { CallAudio } from '../../components/incident/CallAudio';
import { IncidentTable } from '../../components/incident/IncidentTable';
import { attackTypeLabel, incidentStatusLabel, incidentStatusTone, outcomeLabel, outcomeShort, requestKindLabel, riskLevelLabel, riskLevelTone } from '../../components/incident/labels';
import { SignalBreakdown } from '../../components/incident/SignalBreakdown';
import { Timeline } from '../../components/incident/Timeline';
import { Transcript } from '../../components/incident/Transcript';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/Controls';
import { Icon } from '../../components/ui/Icon';
import { Pill } from '../../components/ui/Pill';
import { useToast } from '../../components/ui/Toast';
import { RiskRing } from '../../components/viz/RiskRing';
import { currentAnalyst } from '../../data/people';
import { profileFor } from '../../data/voiceProfiles';
import { formatClock, formatDateTimeIst, formatInr, formatTimeSecIst } from '../../domain/format';
import { relatedIncidents } from '../../domain/metrics';
import type { Incident } from '../../domain/types';
import { downloadFile } from '../../lib/download';
import { generateIncidentReport } from '../../services/reportService';
import { demoNowIso } from '../../state/clock';
import { useDemo } from '../../state/DemoProvider';
import { useIncidentFromRoute } from './useIncident';

function StatusActions({ incident }: { incident: Incident }) {
  const { actions } = useDemo();
  const notify = useToast();
  const run = (fn: () => void, text: string) => {
    fn();
    notify(text);
  };
  switch (incident.status) {
    case 'new':
      return (
        <Button variant="secondary" icon="userCheck" onClick={() => run(() => actions.assignIncident(incident.id), `Incident #${incident.id} assigned to you`)}>
          Assign to me
        </Button>
      );
    case 'investigating':
      return (
        <Button variant="secondary" icon="shield" onClick={() => run(() => actions.setIncidentStatus(incident.id, 'contained', 'Marked contained'), 'Marked contained')}>
          Mark contained
        </Button>
      );
    case 'contained':
      return (
        <Button variant="secondary" icon="check" onClick={() => run(() => actions.setIncidentStatus(incident.id, 'closed', 'Incident closed'), `Incident #${incident.id} closed`)}>
          Close incident
        </Button>
      );
    case 'closed':
      return (
        <Button variant="ghost" icon="refresh" onClick={() => run(() => actions.setIncidentStatus(incident.id, 'investigating', 'Reopened'), 'Incident reopened')}>
          Reopen
        </Button>
      );
  }
}

export function IncidentDetail() {
  const incident = useIncidentFromRoute();
  const { state, actions } = useDemo();
  const notify = useToast();
  const [position, setPosition] = useState(0);
  const seek = useCallback((s: number) => setPosition(s), []);
  const [report, setReport] = useState<{ url: string; filename: string; pages: number; at: string } | null>(null);
  const [building, setBuilding] = useState(false);
  const reportUrl = useRef<string | null>(null);

  // Release the previous object URL when a report is replaced or the view closes.
  useEffect(() => {
    reportUrl.current = report?.url ?? null;
    return () => {
      if (reportUrl.current) URL.revokeObjectURL(reportUrl.current);
    };
  }, [report]);

  if (!incident) {
    return (
      <div className="page">
        <Panel>
          <EmptyState icon="shield" title="Incident not found">
            <Link to="/security/incidents" className="text-link">
              Back to incidents
            </Link>
          </EmptyState>
        </Panel>
      </div>
    );
  }

  const { claimedIdentity: claimed, receiver, request, metadata, verification } = incident;
  const profile = profileFor(claimed.id);
  const related = relatedIncidents(incident, state.incidents);

  const exportJson = () => {
    downloadFile(`pehchaan-ai-incident-${incident.id}.json`, JSON.stringify(incident, null, 2), 'application/json');
    actions.logAudit('report', currentAnalyst, 'Exported incident data as JSON', `Incident #${incident.id}`);
    notify(`Incident #${incident.id} data exported`);
  };

  /** Builds the PDF from the incident's CURRENT state, so status changes are reflected. */
  const buildReport = () => {
    setBuilding(true);
    const at = demoNowIso();
    // Yield a frame so the button can show its working state.
    window.setTimeout(() => {
      try {
        const result = generateIncidentReport(incident, { generatedBy: currentAnalyst, generatedAtIso: at });
        if (report?.url) URL.revokeObjectURL(report.url);
        setReport({ url: result.url, filename: result.filename, pages: result.pages, at });
        actions.logAudit('report', currentAnalyst, 'Generated incident report (PDF)', `Incident #${incident.id}`);
        notify('Report generated successfully');
      } catch {
        notify('Report generation failed');
      } finally {
        setBuilding(false);
      }
    }, 30);
  };

  const downloadReport = () => {
    if (!report) return;
    const link = document.createElement('a');
    link.href = report.url;
    link.download = report.filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    actions.logAudit('report', currentAnalyst, 'Downloaded incident report (PDF)', `Incident #${incident.id}`);
  };

  const facts: [string, ReactNode][] = [
    [
      'Claimed identity',
      <>
        {profile ? (
          <Link to={`/security/profiles/${claimed.id}`} className="fact-link">
            {claimed.name}
          </Link>
        ) : (
          claimed.name
        )}
        <span className="fact-sub">{claimed.role}</span>
      </>,
    ],
    ['Employee', <>{receiver.name}<span className="fact-sub">{receiver.role}, {incident.office}</span></>],
    ['Request', <>{requestKindLabel[request.kind]}<span className="fact-sub">{request.description}</span></>],
    ['Amount', request.amountInr ? <span className="tabular">{formatInr(request.amountInr)}</span> : 'None'],
    ['Counterparty', <>{request.counterparty}<span className="fact-sub">{request.counterpartyNote}</span></>],
    ['Attack type', attackTypeLabel[incident.attackType]],
    ['Language', metadata.language],
    ['Network', <>{metadata.network}<span className="fact-sub">{metadata.callerIdNote}</span></>],
    ['Codec', metadata.codec],
    ['Call duration', <><span className="tabular">{formatClock(metadata.durationSec)}</span><span className="fact-sub tabular">Started {formatTimeSecIst(metadata.startedAt)} IST, {formatClock(metadata.analysedSec)} analysed</span></>],
    ['Audio quality', metadata.audioQuality],
    ['Background noise', metadata.backgroundNoise],
    ['Caller number', <span className="tabular">{incident.callerNumber}</span>],
    ['Assignee', incident.assignee ?? 'Unassigned'],
    ['Incident status', `${incidentStatusLabel[incident.status]}, ${outcomeShort[incident.outcome].toLowerCase()}`],
  ];

  const verificationTone = verification.result === 'denied' ? 'risk' : verification.result === 'confirmed' ? 'safe' : 'warn';

  return (
    <div className="page">
      <PageHeader
        eyebrow={
          <>
            <Link to="/security/incidents">Incidents</Link>
            <Icon name="chevronRight" size={14} />
            <span className="tabular">#{incident.id}</span>
          </>
        }
        title={
          <span className="title-with-pills">
            Incident #{incident.id}
            <Pill tone={riskLevelTone[incident.riskLevel]} dot>
              {riskLevelLabel[incident.riskLevel]} risk
            </Pill>
            {incident.outcome === 'impersonation_confirmed' && <Pill tone="risk">Confirmed</Pill>}
            <Pill tone={incidentStatusTone[incident.status]}>{incidentStatusLabel[incident.status]}</Pill>
          </span>
        }
        description={`${outcomeLabel[incident.outcome]}. Created ${formatDateTimeIst(incident.createdAt)} IST.`}
        actions={
          <>
            <StatusActions incident={incident} />
            <Button variant="secondary" icon="fileText" onClick={buildReport} loading={building}>
              {report ? 'Regenerate report' : 'Generate report'}
            </Button>
            <Link to={`/security/incidents/${incident.id}/analysis`} className="btn btn--primary btn--md">
              <Icon name="activity" size={18} />
              <span>Open analysis</span>
            </Link>
          </>
        }
      />

      <div className="grid grid--main-side">
        <Panel title="Summary">
          <div className="summary-head">
            <RiskRing score={incident.riskScore} level={incident.riskLevel} size={92} stroke={8} />
            <div>
              <p className="summary-head__label">Weighted risk score</p>
              <p className="summary-head__value">
                {riskLevelLabel[incident.riskLevel]} risk, {incident.riskScore}/100
              </p>
              <p className="summary-head__sub">{incident.reasons[0]}</p>
            </div>
          </div>
          <dl className="facts-grid">
            {facts.map(([term, value]) => (
              <div key={term}>
                <dt>{term}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </Panel>

        <div className="stack">
          <Panel title="Verification result">
            <div className={`verify-result verify-result--${verificationTone}`}>
              <Icon name={verification.result === 'denied' ? 'close' : verification.result === 'confirmed' ? 'check' : 'clock'} size={18} strokeWidth={2.4} />
              <div>
                <p className="verify-result__title">{verification.summary}</p>
                {verification.at && <p className="verify-result__sub tabular">{formatDateTimeIst(verification.at)} IST</p>}
              </div>
            </div>
          </Panel>
          <Panel title="Voice profile">
            <p className="profile-impact">
              <Icon name="lock" size={16} />
              <span>
                {incident.voiceProfileUpdate === 'excluded'
                  ? `Excluded from ${claimed.name}'s profile updates. Only verified genuine calls update a trusted profile.`
                  : `Eligible to update ${claimed.name}'s profile after verification.`}
              </span>
            </p>
            {profile && (
              <Link to={`/security/profiles/${claimed.id}`} className="text-link">
                View {claimed.name.split(' ')[0]}'s voice profile <Icon name="arrowRight" size={14} />
              </Link>
            )}
          </Panel>
        </div>
      </div>

      {report && (
        <section className="report-ready" aria-live="polite">
          <span className="report-ready__icon">
            <Icon name="check" size={16} strokeWidth={2.8} />
          </span>
          <div className="report-ready__text">
            <p className="report-ready__title">Report generated</p>
            <p className="report-ready__meta">
              {report.filename} · {report.pages} pages · reflects status {incidentStatusLabel[incident.status].toLowerCase()} at {formatDateTimeIst(report.at)} IST
            </p>
          </div>
          <div className="report-ready__actions">
            <Button variant="primary" icon="download" onClick={downloadReport}>
              Download PDF
            </Button>
            <Button variant="ghost" icon="external" onClick={() => window.open(report.url, '_blank', 'noopener')}>
              Open
            </Button>
            <Button variant="ghost" icon="code" onClick={exportJson}>
              JSON
            </Button>
          </div>
        </section>
      )}

      <Panel title="Detection signals" subtitle="Contribution = signal risk × weight, normalised by total weight">
        <SignalBreakdown signals={incident.signals} score={incident.riskScore} />
      </Panel>

      <div className="grid grid--main-side">
        <div className="stack">
          <Panel
            title="Call audio"
            subtitle="Shaded regions show where signals fired"
            actions={
              <Link to={`/security/incidents/${incident.id}/analysis?tab=audio`} className="text-link">
                Full analysis <Icon name="arrowRight" size={14} />
              </Link>
            }
          >
            <CallAudio incident={incident} position={position} onSeek={seek} height={104} />
          </Panel>
          <Panel title="Transcript" subtitle={`${metadata.language}, high-risk phrases highlighted`}>
            <Transcript incident={incident} activeAt={position} onSeek={seek} />
          </Panel>
        </div>
        <div className="stack">
          <Panel title="Timeline">
            <Timeline events={incident.timeline} />
          </Panel>
          <Panel flush title="Related incidents">
            {related.length ? (
              <>
                <IncidentTable caption="Related incidents" incidents={related.map((r) => r.incident)} columns={['id', 'time', 'risk', 'status']} relativeTime />
                <p className="table-foot">Linked by same {[...new Set(related.flatMap((r) => r.reasons))].join(' or ')}</p>
              </>
            ) : (
              <EmptyState title="No related incidents" />
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
