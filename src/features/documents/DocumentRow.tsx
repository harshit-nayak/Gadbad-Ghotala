import { Link } from 'react-router-dom';
import { documentSourceLabel, riskLevelLabel, riskLevelTone } from '../../components/incident/labels';
import { Icon } from '../../components/ui/Icon';
import { Pill } from '../../components/ui/Pill';
import { formatRelative } from '../../domain/format';
import type { DocumentAnalysis } from '../../domain/types';

export function DocumentRow({ doc }: { doc: DocumentAnalysis }) {
  const source = documentSourceLabel[doc.source];
  const to = doc.state === 'analysing' ? `/documents/${doc.id}/analysis` : `/documents/${doc.id}`;
  return (
    <li>
      <Link to={to} className="doc-row">
        <span className={`doc-row__icon doc-row__icon--${doc.riskLevel}`}>
          <Icon name={doc.source === 'website' ? 'globe' : 'fileText'} size={18} />
        </span>
        <span className="doc-row__main">
          <span className="doc-row__name">{doc.name}</span>
          <span className="doc-row__meta">
            <Icon name={source.icon} size={12} />
            {source.text} · {doc.submittedBy}
          </span>
        </span>
        {doc.state === 'analysing' ? (
          <Pill tone="analysis" dot="live">Analysing</Pill>
        ) : (
          <Pill tone={riskLevelTone[doc.riskLevel]} dot>
            {riskLevelLabel[doc.riskLevel]} risk
          </Pill>
        )}
        <span className="doc-row__time">{doc.state === 'analysing' ? 'In progress' : `Analysed ${formatRelative(doc.analysedAt).replace(/^(Just|Yesterday)/, (w) => w.toLowerCase())}`}</span>
        <Icon name="chevronRight" size={16} className="doc-row__chevron" />
      </Link>
    </li>
  );
}
