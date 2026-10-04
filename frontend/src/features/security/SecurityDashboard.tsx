import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ORG_NAME } from '../../app/brand';
import { BarList, StackedBars } from '../../components/charts/Charts';
import { CatchJourney } from '../../components/incident/CatchJourney';
import { IncidentTable } from '../../components/incident/IncidentTable';
import { attackTypeLabel, outcomeLabel, signalColor, signalShortLabel } from '../../components/incident/labels';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { KpiStrip } from '../../components/metrics/KpiStrip';
import { Button } from '../../components/ui/Button';
import { Segmented } from '../../components/ui/Controls';
import { Icon } from '../../components/ui/Icon';
import { dailyCallStats } from '../../data/callStats';
import { formatCount, formatDateIst, formatInr, formatRelative, formatTimeIst, DEMO_NOW } from '../../domain/format';
import { byAttackType, computeKpis, dailySeries, incidentsInRange, isActive, type RangeDays } from '../../domain/metrics';
import type { SignalId } from '../../domain/types';
import { useDemo } from '../../state/DemoProvider';

export function SecurityDashboard() {
  const { state, actions } = useDemo();
  const [range, setRange] = useState<RangeDays>(30);
  const { incidents } = state;
  const live = incidents.find((i) => i.live);

  const kpis = computeKpis(dailyCallStats, incidents, range);
  const series = dailySeries(dailyCallStats, incidents, range);
  const inRange = incidentsInRange(incidents, range);
  const attack = byAttackType(inRange);
  const needsAttention = incidents.filter(isActive).slice(0, 4);

  const signalHits = useMemo(() => {
    const counts = new Map<SignalId, number>();
    inRange.forEach((i) => i.signals.filter((s) => s.weight > 0 && s.conclusive && s.risk >= 70).forEach((s) => counts.set(s.id, (counts.get(s.id) ?? 0) + 1)));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [inRange]);

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${ORG_NAME} · All offices`}
        title="Security overview"
        description={`Voice impersonation activity across the organisation. Updated ${formatTimeIst(DEMO_NOW)} IST.`}
        actions={<Segmented label="Time range" value={range} onChange={setRange} options={[{ value: 7, label: '7 days' }, { value: 30, label: '30 days' }]} />}
      />

      {live && (
        <section className="live-banner" aria-label="New incident">
          <span className="live-banner__pulse" aria-hidden="true" />
          <div className="live-banner__text">
            <p className="live-banner__title">
              Incident #{live.id} · {live.claimedIdentity.name} ({live.claimedIdentity.roleShort}) impersonation
            </p>
            <p className="live-banner__sub">
              {outcomeLabel[live.outcome]}. Reported by {live.receiver.name}, {formatRelative(live.createdAt)}.
              {live.request.amountInr ? ` ${formatInr(live.request.amountInr)} requested.` : ''}
            </p>
          </div>
          <Link to={`/security/incidents/${live.id}`} className="btn btn--primary btn--md">
            <span>Open incident</span>
            <Icon name="arrowRight" size={16} />
          </Link>
        </section>
      )}

      {live && (
        <Panel title="How this call was caught">
          <CatchJourney incident={live} />
        </Panel>
      )}

      <KpiStrip
        items={[
          { label: 'Calls analysed', value: formatCount(kpis.callsAnalysed), spark: series.map((d) => d.calls) },
          { label: 'High-risk incidents', value: kpis.highRisk, tone: 'risk', spark: series.map((d) => d.high) },
          { label: 'Medium-risk calls', value: kpis.mediumRisk, tone: 'warn', spark: series.map((d) => d.medium) },
          { label: 'Genuine calls', value: formatCount(kpis.genuine), sub: `${((kpis.genuine / kpis.callsAnalysed) * 100).toFixed(1)}% of calls` },
          { label: 'Active investigations', value: kpis.activeInvestigations, sub: 'New or investigating' },
          { label: 'Prevented attempts', value: kpis.prevented, tone: 'safe', spark: series.map((d) => d.prevented) },
        ]}
      />

      <div className="grid grid--main-side">
        <Panel title="Risk trend" subtitle="High-risk incidents and medium-risk calls per day">
          <StackedBars
            label="Daily high-risk incidents and medium-risk calls"
            height={230}
            labelEvery={range === 30 ? 5 : 1}
            data={series.map((d) => ({ label: formatDateIst(`${d.date}T12:00:00+05:30`), values: { high: d.high, medium: d.medium } }))}
            series={[
              { key: 'high', label: 'High risk', color: 'var(--risk)' },
              { key: 'medium', label: 'Medium risk', color: 'var(--warn)' },
            ]}
          />
        </Panel>
        <Panel title="Attack types" subtitle={`${inRange.length} incidents, last ${range} days`}>
          <BarList items={attack.map((a) => ({ key: a.key, label: attackTypeLabel[a.key], value: a.count }))} />
        </Panel>
      </div>

      <Panel
        flush
        title="Recent incidents"
        actions={
          <Link to="/security/incidents" className="text-link">
            View all <Icon name="arrowRight" size={14} />
          </Link>
        }
      >
        <IncidentTable caption="Recent incidents" incidents={incidents.slice(0, 6)} relativeTime />
      </Panel>

      <div className="grid grid--2">
        <Panel title="Needs attention" subtitle="Incidents without a resolution">
          {needsAttention.length === 0 ? (
            <p className="subtle">Nothing open.</p>
          ) : (
            <ul className="attention">
              {needsAttention.map((i) => (
                <li key={i.id} className="attention__row">
                  <div>
                    <Link to={`/security/incidents/${i.id}`} className="attention__id tabular">
                      #{i.id}
                    </Link>
                    <p className="attention__text">
                      {i.claimedIdentity.name} to {i.receiver.name}, {formatRelative(i.createdAt)}
                    </p>
                  </div>
                  {i.assignee ? (
                    <span className="subtle attention__who">{i.assignee.split(',')[0]}</span>
                  ) : (
                    <Button variant="secondary" onClick={() => actions.assignIncident(i.id)}>
                      Assign to me
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Signals driving high risk" subtitle="Conclusive signals scoring 70 or above">
          <BarList
            items={signalHits.map(([id, count]) => ({ key: id, label: signalShortLabel[id], value: count, color: signalColor[id] }))}
            total={inRange.length}
          />
        </Panel>
      </div>
    </div>
  );
}
