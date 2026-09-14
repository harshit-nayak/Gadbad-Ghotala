/** Daily organisation-wide call analysis counts for the 30-day window. */
import type { DailyCallStats } from '../domain/types';
import { seeded } from './seed';

const rng = seeded(911);

function build(): DailyCallStats[] {
  const days: DailyCallStats[] = [];
  const start = Date.UTC(2026, 7, 13);
  for (let d = 0; d < 30; d++) {
    const date = new Date(start + d * 86_400_000);
    const weekday = date.getUTCDay();
    const weekend = weekday === 0 || weekday === 6;
    const isToday = d === 29;
    // Mild growth as the browser/phone rollout reached more teams.
    const growth = 1 + d * 0.006;
    let calls = weekend ? rng.int(160, 260) : Math.round(rng.int(840, 1060) * growth);
    let medium = weekend ? rng.int(1, 4) : rng.int(6, 15);
    if (isToday) {
      calls = 532; // up to 14:36 IST
      medium = 5;
    }
    days.push({ date: date.toISOString().slice(0, 10), callsAnalysed: calls, mediumRisk: medium });
  }
  return days;
}

export const dailyCallStats: DailyCallStats[] = build();
