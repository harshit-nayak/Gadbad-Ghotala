import { useMemo, useState } from 'react';
import { BarList, Donut, LineChart, SegmentBar, StackedBars } from '../../components/charts/Charts';
import { OfficeMap } from '../../components/charts/OfficeMap';
import { attackTypeLabel, requestKindLabel } from '../../components/incident/labels';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { KpiStrip } from '../../components/metrics/KpiStrip';
import { Segmented, SelectField } from '../../components/ui/Controls';
import { dailyCallStats } from '../../data/callStats';
import { formatDateIst, formatInrCompact } from '../../domain/format';
import {
  blockedValue,
  byAttackType,
  byDepartment,
  byLanguage,
  byOffice,
  byRequestKind,
  dailySeries,
  incidentsInRange,
  outcomeBreakdown,
  type RangeDays,
} from '../../domain/metrics';
import type { Incident, Office } from '../../domain/types';
import { useDemo } from '../../state/DemoProvider';
import { attackColor, lavender } from './adminPalette';

const OFFICES: Office[] = ['Mumbai', 'Bengaluru', 'Delhi NCR', 'Hyderabad', 'Chennai', 'Pune', 'Kolkata'];

function verificationSeconds(list: Incident[]) {
  const times = list
    .filter((i) => i.verification.at)
    .map((i) => (new Date(i.verification.at!).getTime() - new Date(i.metadata.startedAt).getTime()) / 1000);
  if (!times.length) return null;
  return Math.round(times.reduce((a, b) => a + b, 0) / times.length);
}

export function Analytics() {
  const { state } = useDemo();
  const [range, setRange] = useState<RangeDays>(30);
  const [office, setOffice] = useState<'all' | Office>('all');

  const scoped = useMemo(
    () => (office === 'all' ? state.incidents : state.incidents.filter((i) => i.office === office)),
    [state.incidents, office],
  );
  const inRange = incidentsInRange(scoped, range);
  const series = dailySeries(dailyCallStats, scoped, range);
  const outcomes = outcomeBreakdown(inRange);
  const avgVerify = verificationSeconds(inRange);

  // Weekly buckets read better than daily points for 30 days.
  const trend = useMemo(() => {
    if (range === 7) return series.map((d) => ({ label: formatDateIst(`${d.date}T12:00:00+05:30`), values: { incidents: d.incidents, prevented: d.prevented } }));
    const weeks: { label: string; detail: string; values: { incidents: number; prevented: number } }[] = [];
    // Count back from today so the latest bucket is a full week.
    for (let end = series.length; end > 0; end -= 7) {
      const chunk = series.slice(Math.max(0, end - 7), end);
      if (chunk.length < 7) break;
      const from = formatDateIst(`${chunk[0].date}T12:00:00+05:30`);
      weeks.unshift({
        label: from,
        detail: `Week from ${from}`,
        values: { incidents: chunk.reduce((s, d) => s + d.incidents, 0), prevented: chunk.reduce((s, d) => s + d.prevented, 0) },
      });
    }
    return weeks;
  }, [series, range]);

  return (
    <div className="page">
      <PageHeader
        title="Analytics"
        description="Trends in who is targeted, how, and what the response achieved."
        actions={
          <>
            <SelectField<'all' | Office>
              label="Office"
              value={office}
              onChange={setOffice}
              options={[{ value: 'all', label: 'All offices' }, ...OFFICES.map((o) => ({ value: o, label: o }))]}
            />
            <Segmented label="Time range" value={range} onChange={setRange} options={[{ value: 7, label: '7 days' }, { value: 30, label: '30 days' }]} />
          </>
        }
      />

      <KpiStrip
        items={[
          { label: 'Incidents', value: inRange.length },
          { label: 'Prevented', value: outcomes.prevented, tone: 'safe' },
          { label: 'Prevention rate', value: inRange.length ? `${Math.round((outcomes.prevented / inRange.length) * 100)}%` : 'n/a', sub: 'Of all incidents' },
          { label: 'Transfers blocked', value: formatInrCompact(blockedValue(inRange)) },
          { label: 'Avg. time to verification', value: avgVerify ? `${avgVerify}s` : 'n/a', sub: 'From call start' },
        ]}
      />

      <div className="grid grid--2">
        <Panel title="Risk trends over time" subtitle="Incidents per day by risk level">
          <StackedBars
            label="Incidents per day by risk level"
            height={220}
            labelEvery={range === 30 ? 5 : 1}
            data={series.map((d) => ({ label: formatDateIst(`${d.date}T12:00:00+05:30`), values: { high: d.high, medium: d.incidents - d.high } }))}
            series={[
              { key: 'high', label: 'High risk', color: lavender[0] },
              { key: 'medium', label: 'Medium risk', color: lavender[2] },
            ]}
          />
        </Panel>
        <Panel title="Incident trends" subtitle={range === 30 ? 'Incidents and prevented attempts per week' : 'Incidents and prevented attempts per day'}>
          <LineChart
            label="Incidents and prevented attempts over time"
            height={220}
            data={trend}
            series={[
              { key: 'incidents', label: 'Incidents', color: lavender[0] },
              { key: 'prevented', label: 'Prevented', color: 'var(--safe)' },
            ]}
          />
        </Panel>
      </div>

      <div className="grid grid--3">
        <Panel title="Attack types">
          <Donut
            label="Incidents by attack type"
            size={132}
            centre={<><span className="donut-total tabular">{inRange.length}</span><span className="donut-caption">total</span></>}
            slices={byAttackType(inRange).map((a) => ({ key: a.key, label: attackTypeLabel[a.key], value: a.count, color: attackColor[a.key] }))}
          />
        </Panel>
        <Panel title="Targeted departments">
          <BarList items={byDepartment(inRange).map((d) => ({ key: d.key, label: d.key, value: d.count, color: lavender[0] }))} emptyText="No incidents in this scope" />
        </Panel>
        <Panel title="Requested actions">
          <BarList items={byRequestKind(inRange).map((d) => ({ key: d.key, label: requestKindLabel[d.key], value: d.count, color: lavender[1] }))} emptyText="No incidents in this scope" />
        </Panel>
      </div>

      <div className="grid grid--3">
        <Panel title="Languages">
          <BarList items={byLanguage(inRange).map((d) => ({ key: d.key, label: d.key, value: d.count, color: lavender[2] }))} emptyText="No incidents in this scope" />
        </Panel>
        <Panel title="Regions">
          <OfficeMap label="Incidents by office" counts={byOffice(inRange)} />
        </Panel>
        <Panel title="Prevention outcomes" subtitle="What happened after the alert">
          <SegmentBar
            label="Incident outcomes"
            slices={[
              { key: 'prevented', label: 'Fraud confirmed, blocked', value: outcomes.prevented, color: 'var(--safe)' },
              { key: 'escalated', label: 'Escalated to Security', value: outcomes.escalated, color: lavender[1] },
              { key: 'genuine', label: 'Verified genuine', value: outcomes.genuine, color: lavender[3] },
              { key: 'unverified', label: 'Ended unverified', value: outcomes.unverified, color: 'var(--warn)' },
            ]}
          />
          <dl className="outcome-stats">
            <div><dt>Fraud confirmed</dt><dd className="tabular">{outcomes.prevented}</dd></div>
            <div><dt>Escalated</dt><dd className="tabular">{outcomes.escalated}</dd></div>
            <div><dt>Verified genuine</dt><dd className="tabular">{outcomes.genuine}</dd></div>
            <div><dt>Ended unverified</dt><dd className="tabular">{outcomes.unverified}</dd></div>
          </dl>
        </Panel>
      </div>
    </div>
  );
}
