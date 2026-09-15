import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ORG_NAME } from '../../app/brand';
import { BarList, Donut, SegmentBar, StackedBars } from '../../components/charts/Charts';
import { OfficeMap } from '../../components/charts/OfficeMap';
import { attackTypeLabel } from '../../components/incident/labels';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { KpiStrip } from '../../components/metrics/KpiStrip';
import { Segmented } from '../../components/ui/Controls';
import { Icon } from '../../components/ui/Icon';
import { dailyCallStats } from '../../data/callStats';
import { formatCount, formatDateIst, formatInr, formatInrCompact, formatRelative, DEMO_NOW } from '../../domain/format';
import {
  blockedValue,
  byAttackType,
  byDepartment,
  byLanguage,
  byOffice,
  computeKpis,
  dailySeries,
  dayKey,
  incidentsInRange,
  isPrevented,
  type RangeDays,
} from '../../domain/metrics';
import { useDemo } from '../../state/DemoProvider';
import { attackColor, dataScale } from './adminPalette';

export function OrganisationOverview() {
  const { state } = useDemo();
  const [range, setRange] = useState<RangeDays>(30);
  const { incidents } = state;
  const inRange = incidentsInRange(incidents, range);
  const kpis = computeKpis(dailyCallStats, incidents, range);
  const series = dailySeries(dailyCallStats, incidents, range);
  const today = incidents.filter((i) => dayKey(i.createdAt) === dayKey(DEMO_NOW));
  const preventedToday = today.filter(isPrevented);
  const prevented = inRange.filter(isPrevented);
  const attack = byAttackType(inRange);
  const languages = byLanguage(inRange);

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${ORG_NAME} · All offices`}
        title="Organisation overview"
        description="How voice impersonation is targeting the organisation, and how much is being stopped."
        actions={<Segmented label="Time range" value={range} onChange={setRange} options={[{ value: 7, label: '7 days' }, { value: 30, label: '30 days' }]} />}
      />

      <section className="today-card" aria-label="Today">
        <div className="today-card__main">
          <p className="today-card__eyebrow">Today, {formatDateIst(DEMO_NOW)}</p>
          <p className="today-card__headline">
            <span className="tabular">{preventedToday.length}</span> prevented impersonation {preventedToday.length === 1 ? 'attempt' : 'attempts'}
          </p>
          {preventedToday[0] ? (
            <p className="today-card__detail">
              <Icon name="shieldCheck" size={16} />
              <span>
                <Link to={`/security/incidents/${preventedToday[0].id}`} className="fact-link tabular">Incident #{preventedToday[0].id}</Link>: cloned voice of {preventedToday[0].claimedIdentity.name} ({preventedToday[0].claimedIdentity.roleShort}) targeted {preventedToday[0].receiver.department}, {preventedToday[0].office}.{' '}
                {preventedToday[0].request.amountInr ? `${formatInr(preventedToday[0].request.amountInr)} transfer blocked` : 'Request blocked'} {formatRelative(preventedToday[0].createdAt)}.
              </span>
            </p>
          ) : (
            <p className="today-card__detail today-card__detail--quiet">No impersonation attempts detected so far today.</p>
          )}
        </div>
        <dl className="today-card__stats">
          <div><dt>Calls analysed today</dt><dd className="tabular">{formatCount(series[series.length - 1].calls)}</dd></div>
          <div><dt>Incidents today</dt><dd className="tabular">{today.length}</dd></div>
          <div><dt>Security status</dt><dd>{today.some((i) => i.status === 'new') ? 'Awaiting review' : today.length ? 'Contained' : 'All clear'}</dd></div>
        </dl>
      </section>

      <KpiStrip
        items={[
          { label: 'Calls analysed', value: formatCount(kpis.callsAnalysed), spark: series.map((d) => d.calls) },
          { label: 'High-risk incidents', value: kpis.highRisk, tone: 'risk', spark: series.map((d) => d.high) },
          { label: 'Prevented attempts', value: kpis.prevented, tone: 'safe', spark: series.map((d) => d.prevented) },
          { label: 'Genuine calls', value: formatCount(kpis.genuine), sub: `${((kpis.genuine / kpis.callsAnalysed) * 100).toFixed(1)}% of calls` },
          { label: 'Active investigations', value: kpis.activeInvestigations },
          { label: 'Transfers blocked', value: formatInrCompact(blockedValue(inRange)), sub: `${prevented.length} requests` },
        ]}
      />

      <div className="grid grid--main-side">
        <Panel title="Risk trends" subtitle="Incidents per day by risk level">
          <StackedBars
            label="Daily incidents by risk level"
            height={236}
            labelEvery={range === 30 ? 5 : 1}
            data={series.map((d) => ({ label: formatDateIst(`${d.date}T12:00:00+05:30`), values: { high: d.high, medium: d.incidents - d.high } }))}
            series={[
              { key: 'high', label: 'High risk', color: dataScale[0] },
              { key: 'medium', label: 'Medium risk (escalated)', color: dataScale[2] },
            ]}
          />
        </Panel>
        <Panel title="Departments targeted" subtitle="Department of the employee called">
          <BarList items={byDepartment(inRange).map((d) => ({ key: d.key, label: d.key, value: d.count, color: dataScale[1] }))} />
        </Panel>
      </div>

      <div className="grid grid--3">
        <Panel title="Attack types">
          <Donut
            label="Incidents by attack type"
            size={140}
            centre={<><span className="donut-total tabular">{inRange.length}</span><span className="donut-caption">incidents</span></>}
            slices={attack.map((a) => ({ key: a.key, label: attackTypeLabel[a.key], value: a.count, color: attackColor[a.key] }))}
          />
        </Panel>
        <Panel title="Language distribution" subtitle="Language of flagged calls">
          <SegmentBar legend={false} label="Flagged calls by language" slices={languages.map((l, i) => ({ key: l.key, label: l.key, value: l.count, color: dataScale[Math.min(i, dataScale.length - 1)] }))} />
          <BarList items={languages.map((l, i) => ({ key: l.key, label: l.key, value: l.count, color: dataScale[Math.min(i, dataScale.length - 1)] }))} />
        </Panel>
        <Panel title="Geographic distribution" subtitle="Incidents by office">
          <OfficeMap label="Incidents by office on a map of India" counts={byOffice(inRange)} />
        </Panel>
      </div>

      <Panel
        flush
        title="Prevented attempts"
        subtitle="Requests stopped after the claimed person denied them"
        actions={<Link to="/admin/reports" className="text-link">Reports & audit <Icon name="arrowRight" size={14} /></Link>}
      >
        <ul className="prevented-list">
          {prevented.slice(0, 5).map((i) => (
            <li key={i.id} className={i.live ? 'is-live' : ''}>
              <span className="prevented-list__icon"><Icon name="shieldCheck" size={16} /></span>
              <span className="prevented-list__main">
                <Link to={`/security/incidents/${i.id}`} className="prevented-list__title">
                  {i.claimedIdentity.name} ({i.claimedIdentity.roleShort}) impersonated
                </Link>
                <span className="prevented-list__sub">{attackTypeLabel[i.attackType]} · {i.receiver.department}, {i.office} · #{i.id}</span>
              </span>
              <span className="prevented-list__amount tabular">{i.request.amountInr ? formatInr(i.request.amountInr) : 'No amount'}</span>
              <span className="prevented-list__time">{formatRelative(i.createdAt)}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
