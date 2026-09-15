import { useMemo, useState } from 'react';
import { IncidentTable } from '../../components/incident/IncidentTable';
import { attackTypeLabel, incidentStatusLabel, outcomeShort, requestKindLabel } from '../../components/incident/labels';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { Button } from '../../components/ui/Button';
import { EmptyState, SearchField, Segmented, SelectField } from '../../components/ui/Controls';
import { useToast } from '../../components/ui/Toast';
import { currentAnalyst } from '../../data/people';
import { formatDateTimeIst } from '../../domain/format';
import type { IncidentStatus, RequestKind, RiskLevel } from '../../domain/types';
import { downloadFile, toCsv } from '../../lib/download';
import { useDemo } from '../../state/DemoProvider';

type RiskFilter = 'all' | Exclude<RiskLevel, 'low'>;
type StatusFilter = 'all' | IncidentStatus;
type KindFilter = 'all' | RequestKind;

export function IncidentList() {
  const { state, actions } = useDemo();
  const notify = useToast();
  const [query, setQuery] = useState('');
  const [risk, setRisk] = useState<RiskFilter>('all');
  const [status, setStatus] = useState<StatusFilter>('all');
  const [kind, setKind] = useState<KindFilter>('all');

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return state.incidents.filter((i) => {
      if (risk !== 'all' && i.riskLevel !== risk) return false;
      if (status !== 'all' && i.status !== status) return false;
      if (kind !== 'all' && i.request.kind !== kind) return false;
      if (!q) return true;
      return [i.id, i.claimedIdentity.name, i.receiver.name, i.request.counterparty, i.office, i.receiver.department]
        .join(' ')
        .toLowerCase()
        .includes(q);
    });
  }, [state.incidents, query, risk, status, kind]);

  const clear = () => {
    setQuery('');
    setRisk('all');
    setStatus('all');
    setKind('all');
  };

  const exportCsv = () => {
    const rows = filtered.map((i) => ({
      incident: i.id,
      created_ist: formatDateTimeIst(i.createdAt),
      claimed_caller: `${i.claimedIdentity.name} (${i.claimedIdentity.roleShort})`,
      employee: i.receiver.name,
      office: i.office,
      request_type: requestKindLabel[i.request.kind],
      amount_inr: i.request.amountInr ?? '',
      attack_type: attackTypeLabel[i.attackType],
      risk_score: i.riskScore,
      risk_level: i.riskLevel,
      status: incidentStatusLabel[i.status],
      outcome: outcomeShort[i.outcome],
    }));
    downloadFile('pehchaan-ai-incidents.csv', toCsv(rows), 'text/csv');
    actions.logAudit('report', currentAnalyst, `Exported ${rows.length} incidents as CSV`, 'Incident list');
    notify(`Exported ${rows.length} incidents`);
  };

  const filtersActive = query || risk !== 'all' || status !== 'all' || kind !== 'all';

  return (
    <div className="page">
      <PageHeader
        title="Incidents"
        description="Every call that reached high risk or was escalated by an employee."
        actions={
          <Button variant="secondary" icon="download" onClick={exportCsv} disabled={filtered.length === 0}>
            Export CSV
          </Button>
        }
      />

      <div className="toolbar">
        <SearchField label="Search incidents" value={query} onChange={setQuery} placeholder="Search ID, person, vendor, office" />
        <Segmented<RiskFilter>
          label="Risk level"
          value={risk}
          onChange={setRisk}
          options={[
            { value: 'all', label: 'All risk' },
            { value: 'high', label: 'High' },
            { value: 'medium', label: 'Medium' },
          ]}
        />
        <SelectField<StatusFilter>
          label="Status"
          value={status}
          onChange={setStatus}
          options={[
            { value: 'all', label: 'All' },
            ...(['new', 'investigating', 'contained', 'closed'] as IncidentStatus[]).map((s) => ({ value: s, label: incidentStatusLabel[s] })),
          ]}
        />
        <SelectField<KindFilter>
          label="Request"
          value={kind}
          onChange={setKind}
          options={[
            { value: 'all', label: 'All types' },
            ...(Object.keys(requestKindLabel) as RequestKind[]).map((k) => ({ value: k, label: requestKindLabel[k] })),
          ]}
        />
        {filtersActive && (
          <Button variant="ghost" onClick={clear}>
            Clear filters
          </Button>
        )}
      </div>

      <Panel flush>
        {filtered.length ? (
          <IncidentTable caption="Incidents" incidents={filtered} />
        ) : (
          <EmptyState title="No incidents match these filters">Try a different search or clear the filters.</EmptyState>
        )}
        <p className="table-foot tabular">
          Showing {filtered.length} of {state.incidents.length} incidents
        </p>
      </Panel>
    </div>
  );
}
