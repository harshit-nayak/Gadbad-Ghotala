/**
 * Organisation metrics derived from incidents and daily call counts.
 * Security and Administrator dashboards both read from these functions,
 * so the same event always produces the same numbers everywhere.
 */
import type { AttackType, CallLanguage, DailyCallStats, Incident, Office, RequestKind } from './types';
import { DEMO_NOW } from './format';

const istDayKey = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' });
export const dayKey = (iso: string) => istDayKey.format(new Date(iso));

export type RangeDays = 7 | 30;

export const statsInRange = (stats: DailyCallStats[], days: RangeDays) => stats.slice(-days);

export function incidentsInRange(incidents: Incident[], days: RangeDays, now = DEMO_NOW) {
  const startKey = dayKey(new Date(new Date(now).getTime() - (days - 1) * 86_400_000).toISOString());
  return incidents.filter((i) => dayKey(i.createdAt) >= startKey);
}

export const isPrevented = (i: Incident) => i.outcome === 'impersonation_confirmed';
export const isActive = (i: Incident) => i.status === 'new' || i.status === 'investigating';

export interface Kpis {
  callsAnalysed: number;
  highRisk: number;
  mediumRisk: number;
  genuine: number;
  activeInvestigations: number;
  prevented: number;
  incidents: number;
}

/** Seeded daily counts exclude the call made live in the demo session; add it back. */
const liveCallsOn = (incidents: Incident[], date: string) => incidents.filter((i) => i.live && dayKey(i.createdAt) === date).length;

export function computeKpis(stats: DailyCallStats[], incidents: Incident[], days: RangeDays): Kpis {
  const range = statsInRange(stats, days);
  const inRange = incidentsInRange(incidents, days);
  const callsAnalysed = range.reduce((sum, d) => sum + d.callsAnalysed + liveCallsOn(incidents, d.date), 0);
  const mediumRisk = range.reduce((sum, d) => sum + d.mediumRisk, 0);
  const highRisk = inRange.filter((i) => i.riskLevel === 'high').length;
  return {
    callsAnalysed,
    highRisk,
    mediumRisk,
    genuine: callsAnalysed - mediumRisk - highRisk,
    activeInvestigations: incidents.filter(isActive).length,
    prevented: inRange.filter(isPrevented).length,
    incidents: inRange.length,
  };
}

export interface DayPoint {
  date: string;
  calls: number;
  medium: number;
  high: number;
  prevented: number;
  incidents: number;
}

export function dailySeries(stats: DailyCallStats[], incidents: Incident[], days: RangeDays): DayPoint[] {
  return statsInRange(stats, days).map((d) => {
    const sameDay = incidents.filter((i) => dayKey(i.createdAt) === d.date);
    return {
      date: d.date,
      calls: d.callsAnalysed + liveCallsOn(incidents, d.date),
      medium: d.mediumRisk,
      high: sameDay.filter((i) => i.riskLevel === 'high').length,
      prevented: sameDay.filter(isPrevented).length,
      incidents: sameDay.length,
    };
  });
}

export interface Share<K extends string = string> {
  key: K;
  count: number;
}

export function countBy<K extends string>(incidents: Incident[], pick: (i: Incident) => K): Share<K>[] {
  const counts = new Map<K, number>();
  incidents.forEach((i) => counts.set(pick(i), (counts.get(pick(i)) ?? 0) + 1));
  return [...counts.entries()].map(([key, count]) => ({ key, count })).sort((a, b) => b.count - a.count);
}

export const byAttackType = (list: Incident[]) => countBy<AttackType>(list, (i) => i.attackType);
export const byDepartment = (list: Incident[]) => countBy<string>(list, (i) => i.receiver.department);
export const byLanguage = (list: Incident[]) => countBy<CallLanguage>(list, (i) => i.metadata.language);
export const byOffice = (list: Incident[]) => countBy<Office>(list, (i) => i.office);
export const byRequestKind = (list: Incident[]) => countBy<RequestKind>(list, (i) => i.request.kind);

export function outcomeBreakdown(list: Incident[]) {
  return {
    prevented: list.filter(isPrevented).length,
    genuine: list.filter((i) => i.outcome === 'request_confirmed').length,
    escalated: list.filter((i) => i.outcome === 'escalated').length,
    unverified: list.filter((i) => i.outcome === 'ended_unverified').length,
  };
}

export const blockedValue = (list: Incident[]) =>
  list.filter(isPrevented).reduce((sum, i) => sum + (i.request.amountInr ?? 0), 0);

/** Incidents linked by claimed identity, counterparty, or caller number. */
export function relatedIncidents(target: Incident, all: Incident[]) {
  return all
    .filter((i) => i.id !== target.id)
    .map((i) => {
      const reasons: string[] = [];
      if (i.claimedIdentity.id === target.claimedIdentity.id) reasons.push('claimed identity');
      if (i.request.counterparty === target.request.counterparty) reasons.push('counterparty');
      if (i.callerNumber === target.callerNumber) reasons.push('caller number');
      return { incident: i, reasons };
    })
    .filter((r) => r.reasons.length > 0)
    .slice(0, 5);
}
