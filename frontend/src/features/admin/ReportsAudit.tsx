import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { PRODUCT_NAME } from '../../app/brand';
import { auditCategoryLabel, incidentStatusLabel, incidentStatusTone, outcomeShort } from '../../components/incident/labels';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { Button } from '../../components/ui/Button';
import { EmptyState, SearchField, Tabs } from '../../components/ui/Controls';
import { Icon } from '../../components/ui/Icon';
import { Pill } from '../../components/ui/Pill';
import { useToast } from '../../components/ui/Toast';
import { auditFromIncidents, organisationAudit } from '../../data/audit';
import { dailyCallStats } from '../../data/callStats';
import { currentAdmin } from '../../data/people';
import { formatDateTimeIst, formatInr } from '../../domain/format';
import { computeKpis } from '../../domain/metrics';
import type { AuditCategory, AuditEvent, VerificationMethod } from '../../domain/types';
import { downloadFile, toCsv } from '../../lib/download';
import { useDemo } from '../../state/DemoProvider';

type TabId = 'reports' | 'verification' | 'employee' | 'security' | 'audit';

const methodLabel: Record<VerificationMethod, string> = {
  claimed_person_device: 'Registered device',
  official_callback: 'Official call-back',
  security_team: 'Security team',
  none: 'Not attempted',
};

const categoryTone: Record<AuditCategory, 'analysis' | 'neutral' | 'safe' | 'warn' | 'brand'> = {
  verification: 'analysis',
  employee_action: 'brand',
  security_response: 'warn',
  profile: 'safe',
  report: 'neutral',
  system: 'neutral',
};

export function ReportsAudit() {
  const { state, actions } = useDemo();
  const notify = useToast();
  const [tab, setTab] = useState<TabId>('reports');
  const [query, setQuery] = useState('');

  const audit = useMemo<AuditEvent[]>(
    () => [...auditFromIncidents(state.incidents), ...organisationAudit, ...state.sessionAudit].sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime()),
    [state.incidents, state.sessionAudit],
  );
  const q = query.trim().toLowerCase();
  const matches = (...fields: (string | undefined)[]) => !q || fields.join(' ').toLowerCase().includes(q);

  const reports = state.incidents.filter((i) => matches(i.id, i.claimedIdentity.name, i.receiver.name, outcomeShort[i.outcome]));
  const verifications = state.incidents.filter((i) => matches(i.id, i.claimedIdentity.name, i.verification.summary));
  const byCategory = (c: AuditCategory) => audit.filter((e) => e.category === c && matches(e.actor, e.action, e.target));
  const employee = byCategory('employee_action');
  const security = byCategory('security_response');
  const history = audit.filter((e) => matches(e.actor, e.action, e.target, auditCategoryLabel[e.category]));

  const rowsForTab = (): Record<string, unknown>[] => {
    switch (tab) {
      case 'reports':
        return reports.map((i) => ({ incident: i.id, created_ist: formatDateTimeIst(i.createdAt), claimed: i.claimedIdentity.name, employee: i.receiver.name, outcome: outcomeShort[i.outcome], status: incidentStatusLabel[i.status], risk: i.riskScore }));
      case 'verification':
        return verifications.map((i) => ({ incident: i.id, at_ist: i.verification.at ? formatDateTimeIst(i.verification.at) : '', method: methodLabel[i.verification.method], result: i.verification.result, summary: i.verification.summary }));
      case 'employee':
      case 'security':
      case 'audit':
        return (tab === 'employee' ? employee : tab === 'security' ? security : history).map((e) => ({ at_ist: formatDateTimeIst(e.at), category: auditCategoryLabel[e.category], actor: e.actor, action: e.action, target: e.target }));
    }
  };

  const exportTab = () => {
    const rows = rowsForTab();
    const name = { reports: 'incident-reports', verification: 'verification-log', employee: 'employee-actions', security: 'security-responses', audit: 'audit-history' }[tab];
    downloadFile(`gg-${name}.csv`, toCsv(rows), 'text/csv');
    actions.logAudit('report', currentAdmin, `Exported ${rows.length} rows from ${name.replace('-', ' ')}`, 'Reports & audit');
    notify(`Exported ${rows.length} rows`);
  };

  const generateSummary = () => {
    const k = computeKpis(dailyCallStats, state.incidents, 30);
    const summary = [
      { metric: 'Calls analysed (30 days)', value: k.callsAnalysed },
      { metric: 'High-risk incidents', value: k.highRisk },
      { metric: 'Medium-risk calls', value: k.mediumRisk },
      { metric: 'Genuine calls', value: k.genuine },
      { metric: 'Prevented attempts', value: k.prevented },
      { metric: 'Active investigations', value: k.activeInvestigations },
    ];
    downloadFile('gg-organisation-summary-30d.csv', toCsv(summary), 'text/csv');
    actions.logAudit('report', currentAdmin, 'Generated 30-day organisation summary', 'Reports');
    notify('Organisation summary generated');
  };

  const downloadIncident = (id: string) => {
    const incident = state.incidents.find((i) => i.id === id);
    if (!incident) return;
    downloadFile(`gg-incident-${id}.json`, JSON.stringify(incident, null, 2), 'application/json');
    actions.logAudit('report', currentAdmin, 'Downloaded incident report', `Incident #${id}`);
    notify(`Report #${id} downloaded`);
  };

  const auditTable = (events: AuditEvent[]) =>
    events.length ? (
      <div className="table-wrap">
        <table className="table">
          <caption className="visually-hidden">Audit events</caption>
          <thead><tr><th>Time (IST)</th><th>Category</th><th>Actor</th><th>Action</th><th>Target</th></tr></thead>
          <tbody>
            {events.slice(0, 80).map((e) => (
              <tr key={e.id}>
                <td className="tabular muted nowrap">{formatDateTimeIst(e.at)}</td>
                <td><Pill tone={categoryTone[e.category]}>{auditCategoryLabel[e.category]}</Pill></td>
                <td className="nowrap">{e.actor}</td>
                <td>{e.action}</td>
                <td className="nowrap">
                  {e.incidentId ? <Link to={`/security/incidents/${e.incidentId}`} className="fact-link tabular">{e.target}</Link> : <span className="muted">{e.target}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ) : (
      <EmptyState title="No matching events" />
    );

  return (
    <div className="page">
      <PageHeader
        title="Reports & audit"
        description={`Incident reports, verification records and a complete audit trail of actions across ${PRODUCT_NAME}.`}
        actions={<Button variant="primary" icon="fileText" onClick={generateSummary}>Generate 30-day summary</Button>}
      />

      <div className="grid grid--3">
        <div className="report-card">
          <span className="report-card__icon"><Icon name="fileText" size={18} /></span>
          <p className="report-card__title">Monthly board report</p>
          <p className="report-card__meta">Scheduled on the 1st · Board Risk Committee</p>
          <p className="report-card__foot">Last sent 1 Sept 2026</p>
        </div>
        <div className="report-card">
          <span className="report-card__icon"><Icon name="calendar" size={18} /></span>
          <p className="report-card__title">Weekly security digest</p>
          <p className="report-card__meta">Mondays 09:00 IST · Security and Finance leads</p>
          <p className="report-card__foot">Next on 14 Sept 2026</p>
        </div>
        <div className="report-card">
          <span className="report-card__icon"><Icon name="shieldCheck" size={18} /></span>
          <p className="report-card__title">Audit log retention</p>
          <p className="report-card__meta">Events kept for 7 years, write-once storage</p>
          <p className="report-card__foot tabular">{audit.length} events in view</p>
        </div>
      </div>

      <Tabs<TabId>
        label="Report type"
        active={tab}
        onChange={setTab}
        tabs={[
          { id: 'reports', label: 'Incident reports', count: reports.length },
          { id: 'verification', label: 'Verification logs', count: verifications.length },
          { id: 'employee', label: 'Employee actions', count: employee.length },
          { id: 'security', label: 'Security responses', count: security.length },
          { id: 'audit', label: 'Audit history', count: history.length },
        ]}
      />

      <div className="toolbar toolbar--spread">
        <SearchField label="Search records" value={query} onChange={setQuery} placeholder="Search people, incidents, actions" />
        <Button variant="secondary" icon="download" onClick={exportTab}>Export CSV</Button>
      </div>

      <Panel flush>
        <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
          {tab === 'reports' && (
            <div className="table-wrap">
              <table className="table">
                <caption className="visually-hidden">Incident reports</caption>
                <thead><tr><th>Incident</th><th>Created (IST)</th><th>Claimed caller</th><th>Employee</th><th>Outcome</th><th>Status</th><th className="num">Amount</th><th /></tr></thead>
                <tbody>
                  {reports.map((i) => (
                    <tr key={i.id} className={i.live ? 'table__row--live' : ''}>
                      <td><Link to={`/security/incidents/${i.id}`} className="table__id tabular">#{i.id}</Link></td>
                      <td className="tabular muted nowrap">{formatDateTimeIst(i.createdAt)}</td>
                      <td>{i.claimedIdentity.name}</td>
                      <td>{i.receiver.name}</td>
                      <td>{outcomeShort[i.outcome]}</td>
                      <td><Pill tone={incidentStatusTone[i.status]}>{incidentStatusLabel[i.status]}</Pill></td>
                      <td className="num tabular">{i.request.amountInr ? formatInr(i.request.amountInr) : 'None'}</td>
                      <td className="num"><Button variant="ghost" icon="download" onClick={() => downloadIncident(i.id)} aria-label={`Download report for incident ${i.id}`}>Report</Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {tab === 'verification' && (
            <div className="table-wrap">
              <table className="table">
                <caption className="visually-hidden">Verification logs</caption>
                <thead><tr><th>Time (IST)</th><th>Incident</th><th>Method</th><th>Result</th><th>Record</th></tr></thead>
                <tbody>
                  {verifications.map((i) => (
                    <tr key={i.id}>
                      <td className="tabular muted nowrap">{i.verification.at ? formatDateTimeIst(i.verification.at) : 'n/a'}</td>
                      <td><Link to={`/security/incidents/${i.id}`} className="table__id tabular">#{i.id}</Link></td>
                      <td>{methodLabel[i.verification.method]}</td>
                      <td>
                        <Pill tone={i.verification.result === 'denied' ? 'risk' : i.verification.result === 'confirmed' ? 'safe' : 'warn'}>
                          {{ denied: 'Denied', confirmed: 'Confirmed', pending: 'Pending', not_attempted: 'Not attempted' }[i.verification.result]}
                        </Pill>
                      </td>
                      <td className="muted">{i.verification.summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {tab === 'employee' && auditTable(employee)}
          {tab === 'security' && auditTable(security)}
          {tab === 'audit' && auditTable(history)}
        </div>
      </Panel>
    </div>
  );
}
