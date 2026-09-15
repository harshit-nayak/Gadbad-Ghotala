import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { documentSourceLabel, riskLevelLabel } from '../../components/incident/labels';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { EmptyState } from '../../components/ui/Controls';
import { Icon } from '../../components/ui/Icon';
import { RiskRing } from '../../components/viz/RiskRing';
import { formatDateTimeIst } from '../../domain/format';
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion';
import { useDemo } from '../../state/DemoProvider';
import { ConsistencyList, DocumentPreview, EntityTable, InstructionList } from './DocumentParts';
import { useDocumentFromRoute } from './useDocuments';

const STEPS = [
  'Extracting text',
  'Identifying entities',
  'Analysing context',
  'Checking instructions',
  'Checking identity and consistency',
  'Scoring risk',
];
const STEP_MS = 700;

export function DocumentAnalysisView() {
  const doc = useDocumentFromRoute();
  const { actions } = useDemo();
  const reducedMotion = usePrefersReducedMotion();
  const finished = doc?.state === 'complete';
  const [step, setStep] = useState(finished ? STEPS.length : 0);

  useEffect(() => {
    if (!doc || doc.state === 'complete') return;
    if (step >= STEPS.length) {
      actions.updateDocument(doc.id, { state: 'complete' });
      return;
    }
    const id = window.setTimeout(() => setStep((s) => s + 1), reducedMotion ? 120 : STEP_MS);
    return () => window.clearTimeout(id);
  }, [doc, step, actions, reducedMotion]);

  if (!doc) {
    return (
      <div className="page">
        <Panel>
          <EmptyState icon="fileText" title="Analysis not found">
            <Link to="/documents" className="text-link">Back to document security</Link>
          </EmptyState>
        </Panel>
      </div>
    );
  }

  const shown = (index: number) => step > index;
  const done = step >= STEPS.length;
  const source = documentSourceLabel[doc.source];

  return (
    <div className="page">
      <PageHeader
        eyebrow={
          <>
            <Link to="/documents">Document security</Link>
            <Icon name="chevronRight" size={14} />
            <span>Analysis</span>
          </>
        }
        title={doc.name}
        description={`${doc.meta} · ${source.text} · ${doc.submittedBy} · ${formatDateTimeIst(doc.analysedAt)} IST`}
        actions={
          done ? (
            <Link to={`/documents/${doc.id}`} className="btn btn--primary btn--md">
              <Icon name="fileText" size={18} />
              <span>View report</span>
            </Link>
          ) : undefined
        }
      />

      <div className="grid grid--main-side">
        <Panel title="Document" subtitle={shown(3) ? 'Suspicious instructions and flagged values highlighted' : 'Extracted content'}>
          {shown(0) ? <DocumentPreview doc={doc} revealFlags={shown(3)} /> : <div className="skeleton-lines" aria-hidden="true"><span /><span /><span /><span /></div>}
        </Panel>

        <Panel title={done ? 'Analysis complete' : 'Analysing'}>
          <div className="analysis-score">
            <RiskRing score={shown(5) ? doc.riskScore : 0} level={shown(5) ? doc.riskLevel : 'low'} size={96} stroke={8} />
            <div>
              <p className="analysis-score__label">Risk score</p>
              <p className="analysis-score__value">{shown(5) ? `${riskLevelLabel[doc.riskLevel]} risk` : 'Calculating'}</p>
            </div>
          </div>
          <ol className="progress-steps" aria-live="polite">
            {STEPS.map((label, index) => {
              const status = step > index ? 'done' : step === index && !done ? 'active' : 'waiting';
              return (
                <li key={label} className={`progress-step is-${status}`}>
                  <span className="progress-step__marker" aria-hidden="true">
                    {status === 'done' ? <Icon name="check" size={12} strokeWidth={3} /> : status === 'active' ? <span className="spinner spinner--sm" /> : null}
                  </span>
                  {label}
                </li>
              );
            })}
          </ol>
        </Panel>
      </div>

      {shown(1) && (
        <Panel title="Extracted entities" subtitle={`${doc.entities.length} found, ${doc.entities.filter((e) => e.flagged).length} need attention`}>
          <EntityTable entities={doc.entities} />
        </Panel>
      )}

      {shown(2) && (
        <div className="grid grid--2">
          <Panel title="Context analysis">
            <p className="context-summary">{doc.contextSummary}</p>
            <dl className="meta-list">
              <div><dt>Requested action</dt><dd>{doc.requestedAction}</dd></div>
            </dl>
          </Panel>
          {shown(3) && (
            <Panel title="Suspicious instructions">
              <InstructionList doc={doc} />
            </Panel>
          )}
        </div>
      )}

      {shown(4) && (
        <Panel title="Identity and content consistency">
          <ConsistencyList doc={doc} />
        </Panel>
      )}
    </div>
  );
}
