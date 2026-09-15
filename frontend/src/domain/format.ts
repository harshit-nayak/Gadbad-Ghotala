const inr = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});

/** 2000000 -> "₹20,00,000" (Indian digit grouping) */
export const formatInr = (amount: number) => inr.format(amount);

/** 72 -> "01:12" */
export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const mm = String(Math.floor(s / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

const istTime = new Intl.DateTimeFormat('en-IN', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'Asia/Kolkata',
});

const istTimeSec = new Intl.DateTimeFormat('en-IN', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
  timeZone: 'Asia/Kolkata',
});

/** ISO timestamp -> "14:31:09" in IST */
export const formatTimeSecIst = (iso: string) => istTimeSec.format(new Date(iso));

/** ISO timestamp -> "14:31" in IST */
export const formatTimeIst = (iso: string) => istTime.format(new Date(iso));

/** Current time in the demo world. Fixed so mock data reads consistently. */
export const DEMO_NOW = '2026-09-11T14:36:00+05:30';

const istDate = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', timeZone: 'Asia/Kolkata' });
const istDateYear = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata' });

/** ISO -> "11 Sep" */
export const formatDateIst = (iso: string) => istDate.format(new Date(iso));
/** ISO -> "11 Sep 2026" */
export const formatDateYearIst = (iso: string) => istDateYear.format(new Date(iso));
/** ISO -> "11 Sep, 14:31" */
export const formatDateTimeIst = (iso: string) => `${formatDateIst(iso)}, ${formatTimeIst(iso)}`;

/** Relative to DEMO_NOW: "4 min ago", "3 h ago", "Yesterday", "2 Sep" */
export function formatRelative(iso: string, now = DEMO_NOW): string {
  const diffMin = Math.round((new Date(now).getTime() - new Date(iso).getTime()) / 60000);
  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin} min ago`;
  const hours = Math.floor(diffMin / 60);
  if (hours < 24 && formatDateIst(iso) === formatDateIst(now)) return `${hours} h ago`;
  if (hours < 48) return 'Yesterday';
  return formatDateIst(iso);
}

/** 1284 -> "1,284"; en-IN grouping for large counts */
export const formatCount = (n: number) => new Intl.NumberFormat('en-IN').format(n);

/** 2000000 -> "₹20 L", 25000000 -> "₹2.5 Cr" for compact chart labels */
export function formatInrCompact(amount: number): string {
  if (amount >= 1e7) return `₹${+(amount / 1e7).toFixed(1)} Cr`;
  if (amount >= 1e5) return `₹${+(amount / 1e5).toFixed(1)} L`;
  return formatInr(amount);
}
