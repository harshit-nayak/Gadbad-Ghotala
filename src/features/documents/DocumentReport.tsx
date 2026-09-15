import { Link } from 'react-router-dom';
import { documentSourceLabel, riskLevelLabel, riskLevelTone } from '../../components/incident/labels';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/Controls';
import { Icon } from '../../components/ui/Icon';
import { Pill } from '../../components/ui/Pill';
import { useToast } from '../../components/ui/Toast';
import { RiskRing } from '../../components/viz/RiskRing';
import { formatDateTimeIst } from '../../domain/format';
import { downloadFile, toCsv } from '../../lib/download';
import { useDemo } from '../../state/DemoProvider';
import { ConsistencyList, EntityTable, InstructionList, entityKindLabel } from './DocumentParts';
import { documentsUser, useDocumentFromRoute } from './useDocuments';

export function DocumentReport() {
  const doc = useDocumentFromRoute();
  const { state, actions } = useDemo();
  const notify = useToast();

  if (!doc) {
    return (
      <div className="page">
        <Panel>
          <EmptyState icon="fileText" title="Report not found">
            <Link to="/documents" className="text-link">Back to document security</Link>
          </EmptyState>
        </Panel>
      </div>
    );
  }

  const linkedIncident = doc.counterparty ? state.incidents.find((i) => i.request.counterparty === doc.counterparty) : undefined;
  const source = documentSourceLabel[doc.source];
  const slug = doc.name.replace(/[^\w.-]+/g, '_');

  const exportJson = () => {
    downloadFile(`pehchaan-ai-document-report-${slug}.json`, JSON.stringify(doc, null, 2), 'application/json');
    actions.logAudit('report', documentsUser, 'Exported document report', doc.name);
    notify('Report exported');
  };
  const exportCsv = () => {
    downloadFile(`pehchaan-ai-entities-${slug}.csv`, toCsv(doc.entities.map((e) => ({ type: entityKindLabel[e.kind], value: e.value, flagged: e.flagged ? 'yes' : 'no', finding: e.note ?? '' }))), 'text/csv');
    notify('Entities exported');
  };
  const share = () => {
    actions.updateDocument(doc.id, { sharedWithSecurity: true });
    actions.logAudit('security_response', documentsUser, 'Shared document analysis with Security', doc.name);
    notify('Sent to the Security team');
  };
  const markReviewed = () => {
    actions.updateDocument(doc.id, { reviewed: true });
    actions.logAudit('employee_action', documentsUser, 'Marked document analysis reviewed', doc.name);
    notify('Marked as reviewed');
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow={
          <>
            <Link to="/documents">Document security</Link>
            <Icon name="chevronRight" size={14} />
            <span>Report</span>
          </>
        }
        title={doc.name}
        description={`${doc.meta} · ${source.text} · ${doc.submittedBy} · Analysed ${formatDateTimeIst(doc.analysedAt)} IST`}
        actions={
          <>
            <Button variant="secondary" icon="download" onClick={exportJson}>Download report</Button>
            <Button variant="secondary" icon="printer" onClick={() => window.print()}>Print</Button>
            <Link to={`/documents/${doc.id}/analysis`} className="btn btn--ghost btn--md"><span>View analysis</span></Link>
          </>
        }
      />

      <section className={`report-hero report-hero--${doc.riskLevel}`}>
        <RiskRing score={doc.riskScore} level={doc.riskLevel} size={104} stroke={9} />
        <div className="report-hero__text">
          <Pill tone={riskLevelTone[doc.riskLevel]} dot>{riskLevelLabel[doc.riskLevel]} risk</Pill>
          <h2 className="report-hero__title">{doc.recommendation}</h2>
          <p className="report-hero__sub">{doc.contextSummary}</p>
        </div>
        <div className="report-hero__actions">
          {doc.riskLevel !== 'low' && (
            <Button variant="primary" icon="send" onClick={share} disabled={doc.sharedWithSecurity}>
              {doc.sharedWithSecurity ? 'Sent to Security' : 'Send to Security'}
            </Button>
          )}
          <Button variant="secondary" icon="check" onClick={markReviewed} disabled={doc.reviewed}>
            {doc.reviewed ? 'Reviewed' : 'Mark reviewed'}
          </Button>
        </div>
      </section>

      {linkedIncident && (
        <Link to={`/security/incidents/${linkedIncident.id}`} className="linked-incident">
          <Icon name="link" size={16} />
          <span>
            <strong>{doc.counterparty}</strong> is also the counterparty in call incident <span className="tabular">#{linkedIncident.id}</span> ({linkedIncident.claimedIdentity.name} impersonation)
          </span>
          <Icon name="arrowRight" size={16} />
        </Link>
      )}

      <div className="grid grid--2">
        <Panel title="Requested action">
          <p className="requested-action">{doc.requestedAction}</p>
        </Panel>
        <Panel title="Reasons for flagging">
          {doc.reasons.length ? (
            <ul className="reason-list">
              {doc.reasons.map((r) => <li key={r}><Icon name="alert" size={14} />{r}</li>)}
            </ul>
          ) : (
            <p className="subtle">Nothing was flagged.</p>
          )}
        </Panel>
      </div>

      <Panel title="Detected entities" actions={<Button variant="ghost" icon="download" onClick={exportCsv}>CSV</Button>}>
        <EntityTable entities={doc.entities} />
      </Panel>

      <div className="grid grid--2">
        <Panel title="Suspicious instructions"><InstructionList doc={doc} /></Panel>
        <Panel title="Identity and content consistency"><ConsistencyList doc={doc} /></Panel>
      </div>
    </div>
  );
}
