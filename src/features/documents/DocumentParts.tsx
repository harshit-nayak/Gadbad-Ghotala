/** Pieces shared by the analysis view and the report. */
import type { ReactNode } from 'react';
import { riskLevelTone } from '../../components/incident/labels';
import { Icon } from '../../components/ui/Icon';
import { Pill } from '../../components/ui/Pill';
import type { DocumentAnalysis, ExtractedEntity } from '../../domain/types';

export const entityKindLabel: Record<ExtractedEntity['kind'], string> = {
  amount: 'Amount',
  organisation: 'Organisation',
  person: 'Person',
  bank_account: 'Bank account',
  ifsc: 'IFSC',
  email: 'Email',
  url: 'Website',
  deadline: 'Deadline',
  phone: 'Phone',
};

function markLine(line: string, doc: DocumentAnalysis): ReactNode {
  const values = doc.entities.filter((e) => e.flagged).map((e) => e.value).filter((v) => line.includes(v));
  if (!values.length) return line;
  const parts: ReactNode[] = [];
  let rest = line;
  let key = 0;
  while (rest) {
    const hit = values.map((v) => ({ v, i: rest.indexOf(v) })).filter((h) => h.i >= 0).sort((a, b) => a.i - b.i)[0];
    if (!hit) {
      parts.push(rest);
      break;
    }
    if (hit.i > 0) parts.push(rest.slice(0, hit.i));
    parts.push(<span key={key++} className="entity-mark">{hit.v}</span>);
    rest = rest.slice(hit.i + hit.v.length);
  }
  return parts;
}

export function DocumentPreview({ doc, revealFlags }: { doc: DocumentAnalysis; revealFlags: boolean }) {
  const norm = (s: string) => s.replace(/…$/, '').trim();
  return (
    <div className="doc-preview">
      {doc.excerpt.map((line, i) => {
        const instruction = revealFlags
          ? doc.instructions.find((ins) => line.includes(norm(ins.quote)) || norm(ins.quote).includes(line))
          : undefined;
        return (
          <p key={i} className={`doc-preview__line ${instruction ? `is-flagged is-${instruction.level}` : ''}`}>
            {revealFlags ? markLine(line, doc) : line}
            {instruction && <span className="doc-preview__note">{instruction.reason}</span>}
          </p>
        );
      })}
    </div>
  );
}

export function EntityTable({ entities }: { entities: ExtractedEntity[] }) {
  if (!entities.length) return <p className="subtle">No entities found.</p>;
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="visually-hidden">Extracted entities</caption>
        <thead>
          <tr>
            <th scope="col">Type</th>
            <th scope="col">Value</th>
            <th scope="col">Finding</th>
          </tr>
        </thead>
        <tbody>
          {entities.map((e) => (
            <tr key={`${e.kind}-${e.value}`}>
              <td className="muted nowrap">{entityKindLabel[e.kind]}</td>
              <td className="td-strong tabular">{e.value}</td>
              <td>
                {e.flagged ? (
                  <span className="entity-finding is-flagged"><Icon name="alert" size={13} />{e.note ?? 'Needs verification'}</span>
                ) : (
                  <span className="entity-finding">{e.note ?? 'No issue'}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function InstructionList({ doc }: { doc: DocumentAnalysis }) {
  if (!doc.instructions.length) return <p className="subtle">No suspicious instructions found.</p>;
  return (
    <ul className="instructions">
      {doc.instructions.map((ins) => (
        <li key={`${ins.quote}-${ins.reason}`} className="instruction">
          <Pill tone={riskLevelTone[ins.level]}>{ins.level === 'high' ? 'High' : 'Medium'}</Pill>
          <div>
            <p className="instruction__quote">“{ins.quote}”</p>
            <p className="instruction__reason">{ins.reason}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function ConsistencyList({ doc }: { doc: DocumentAnalysis }) {
  return (
    <ul className="checks-list">
      {doc.consistency.map((c) => (
        <li key={c.label} className={`check-row is-${c.result}`}>
          <span className="check-row__icon">
            <Icon name={c.result === 'pass' ? 'check' : c.result === 'fail' ? 'close' : 'alert'} size={13} strokeWidth={2.8} />
          </span>
          <span className="check-row__label">{c.label}</span>
          <span className="check-row__detail">{c.detail}</span>
        </li>
      ))}
    </ul>
  );
}
