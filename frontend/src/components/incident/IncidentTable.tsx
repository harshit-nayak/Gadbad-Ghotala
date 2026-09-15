import { useNavigate } from 'react-router-dom';
import { formatDateTimeIst, formatInrCompact, formatRelative } from '../../domain/format';
import type { Incident } from '../../domain/types';
import { Pill } from '../ui/Pill';
import { incidentStatusLabel, incidentStatusTone, requestKindLabel } from './labels';
import { RiskScore } from './RiskScore';
import './incident.css';

export type IncidentColumn = 'id' | 'time' | 'claimed' | 'employee' | 'request' | 'risk' | 'status';

interface IncidentTableProps {
  incidents: Incident[];
  columns?: IncidentColumn[];
  relativeTime?: boolean;
  caption: string;
}

const allColumns: IncidentColumn[] = ['id', 'time', 'claimed', 'employee', 'request', 'risk', 'status'];

/** Shared incident table. Rows open the incident detail. */
export function IncidentTable({ incidents, columns = allColumns, relativeTime = false, caption }: IncidentTableProps) {
  const navigate = useNavigate();
  const show = (c: IncidentColumn) => columns.includes(c);
  const open = (id: string) => navigate(`/security/incidents/${id}`);

  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {show('id') && <th scope="col">Incident</th>}
            {show('time') && <th scope="col">Time (IST)</th>}
            {show('claimed') && <th scope="col">Claimed caller</th>}
            {show('employee') && <th scope="col">Employee</th>}
            {show('request') && <th scope="col">Request</th>}
            {show('risk') && <th scope="col">Risk</th>}
            {show('status') && <th scope="col">Status</th>}
          </tr>
        </thead>
        <tbody>
          {incidents.map((i) => (
            <tr key={i.id} className={`table__row--link ${i.live ? 'table__row--live' : ''}`} onClick={() => open(i.id)}>
              {show('id') && (
                <td>
                  <a
                    href={`#/security/incidents/${i.id}`}
                    className="table__id tabular"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      open(i.id);
                    }}
                  >
                    #{i.id}
                  </a>
                  {i.live && <span className="table__new">New</span>}
                </td>
              )}
              {show('time') && <td className="tabular muted nowrap">{relativeTime ? formatRelative(i.createdAt) : formatDateTimeIst(i.createdAt)}</td>}
              {show('claimed') && (
                <td>
                  <span className="cell-strong">{i.claimedIdentity.name}</span>
                  <span className="cell-sub">{i.claimedIdentity.roleShort}</span>
                </td>
              )}
              {show('employee') && (
                <td>
                  <span className="cell-strong">{i.receiver.name}</span>
                  <span className="cell-sub">{i.receiver.department}, {i.office}</span>
                </td>
              )}
              {show('request') && (
                <td>
                  <span className="cell-strong">{requestKindLabel[i.request.kind]}</span>
                  <span className="cell-sub tabular">{i.request.amountInr ? formatInrCompact(i.request.amountInr) : i.request.counterparty}</span>
                </td>
              )}
              {show('risk') && (
                <td>
                  <RiskScore score={i.riskScore} level={i.riskLevel} />
                </td>
              )}
              {show('status') && (
                <td>
                  <Pill tone={incidentStatusTone[i.status]}>{incidentStatusLabel[i.status]}</Pill>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
