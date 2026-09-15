/**
 * Incident reports for calls the detector scored at or above REPORT_THRESHOLD.
 *
 * Evidence (what the model found) is staged by whichever screen saw the high
 * score -- the live call alert, Audio check, or the Capture client tab -- and
 * the report page adds the caller-side details the model can't know. Kept in
 * sessionStorage so a refresh doesn't lose a half-written report; nothing
 * leaves the browser.
 */
import type { AudioCheckSummary, AudioWindowResult } from './audioCheckService';
import { readSession, type DetectionSession } from './detectionFeed';

/** Session risk (percent) at which a report is offered. Matches the backend's high band cut (1 - THRESHOLD_SYNTHETIC). */
export const REPORT_THRESHOLD = 70;

export interface EvidenceWindow {
  startMs: number | null;
  endMs: number | null;
  label: string;
  pReal: number | null;
}

export interface ReportEvidence {
  source: 'live_call' | 'audio_file';
  /** Backend session id, or the uploaded file's name */
  reference: string;
  detector: string;
  /** ISO: when the call started, or when the file was analysed */
  analysedAt: string;
  riskPercent: number;
  band: string;
  recommendation: string | null;
  speechSeconds: number;
  durationSeconds: number | null;
  counts: { real: number; uncertain: number; synthetic: number };
  windows: EvidenceWindow[];
}

export type Platform = 'whatsapp_voice' | 'whatsapp_video' | 'phone' | 'other';
export type Relationship = 'family' | 'friend' | 'boss_colleague' | 'bank' | 'government' | 'company_support' | 'unknown' | 'other';
export type RequestKind = 'money' | 'otp' | 'bank_details' | 'personal_info' | 'remote_app' | 'secrecy' | 'urgency';
export type Outcome = 'nothing' | 'shared_info' | 'sent_money';
export type PaymentMethod = 'upi' | 'bank_transfer' | 'card' | 'wallet' | 'other';

export interface CallDetails {
  reporterName: string;
  reporterContact: string;
  organisation: string;
  /** datetime-local value */
  callTime: string;
  platform: Platform;
  callerNumber: string;
  claimedName: string;
  relationship: Relationship;
  requests: RequestKind[];
  outcome: Outcome;
  amountInr: string;
  paymentMethod: PaymentMethod;
  transactionRef: string;
  notes: string;
}

export interface ReportRecord {
  id: string;
  generatedAt: string;
  details: CallDetails;
  evidence: ReportEvidence;
}

export const platformLabel: Record<Platform, string> = {
  whatsapp_voice: 'WhatsApp voice call',
  whatsapp_video: 'WhatsApp video call',
  phone: 'Mobile or landline call',
  other: 'Another app',
};

export const relationshipLabel: Record<Relationship, string> = {
  family: 'Family member',
  friend: 'Friend',
  boss_colleague: 'Boss or colleague',
  bank: 'Bank',
  government: 'Police or government official',
  company_support: 'Company customer support',
  unknown: "Didn't say",
  other: 'Someone else',
};

export const requestLabel: Record<RequestKind, string> = {
  money: 'Send money',
  otp: 'Share an OTP, PIN or password',
  bank_details: 'Share bank or card details',
  personal_info: 'Share personal details (Aadhaar, PAN, address)',
  remote_app: 'Install an app or share the screen',
  secrecy: 'Keep the call secret',
  urgency: 'Act immediately',
};

export const outcomeLabel: Record<Outcome, string> = {
  nothing: "I didn't do anything they asked",
  shared_info: 'I shared some information',
  sent_money: 'I sent money',
};

export const paymentLabel: Record<PaymentMethod, string> = {
  upi: 'UPI',
  bank_transfer: 'Bank transfer (NEFT / IMPS / RTGS)',
  card: 'Debit or credit card',
  wallet: 'Wallet',
  other: 'Other',
};

export const verdictLabel: Record<string, string> = {
  likely_real: 'Sounds real',
  uncertain: 'Unclear',
  likely_synthetic: 'Sounds AI-generated',
};

// ---------------------------------------------------------------- evidence

export function evidenceFromLiveSession(session: DetectionSession): ReportEvidence | null {
  const readout = readSession(session);
  if (readout.windows === 0) return null;
  const windows = session.verdicts.map((v) => ({
    startMs: v.window_start_ms ?? null,
    endMs: v.window_end_ms ?? null,
    label: v.label,
    pReal: v.p_bonafide ?? null,
  }));
  const lastEnd = Math.max(0, ...windows.map((w) => w.endMs ?? 0));
  return {
    source: 'live_call',
    reference: session.id,
    detector: session.detector,
    analysedAt: new Date(session.startedAt).toISOString(),
    riskPercent: readout.score,
    band: readout.last?.risk_band ?? 'low',
    recommendation: readout.recommendation,
    speechSeconds: readout.speechSeconds,
    durationSeconds: lastEnd ? lastEnd / 1000 : null,
    counts: {
      real: windows.filter((w) => w.label === 'likely_real').length,
      uncertain: readout.uncertain,
      synthetic: readout.synthetic,
    },
    windows,
  };
}

export function evidenceFromAudioCheck(
  fileName: string,
  detector: string,
  durationMs: number,
  windows: AudioWindowResult[],
  summary: AudioCheckSummary,
): ReportEvidence {
  const count = (label: string) => windows.filter((w) => w.label === label).length;
  return {
    source: 'audio_file',
    reference: fileName,
    detector,
    analysedAt: new Date().toISOString(),
    riskPercent: Math.round(summary.risk.session_risk * 100),
    band: summary.risk.risk_band,
    recommendation: summary.risk.recommendation,
    speechSeconds: summary.analysis.speech_seconds,
    durationSeconds: durationMs / 1000,
    counts: { real: count('likely_real'), uncertain: count('uncertain'), synthetic: count('likely_synthetic') },
    windows: windows.map((w) => ({ startMs: w.start_ms, endMs: w.end_ms, label: w.label, pReal: w.p_bonafide })),
  };
}

export const isReportable = (evidence: ReportEvidence | null) => !!evidence && evidence.riskPercent >= REPORT_THRESHOLD;

// ---------------------------------------------------------------- storage

const EVIDENCE_KEY = 'gg.report.evidence';
const RECORD_KEY = 'gg.report.record';
const PROGRESS_KEY = 'gg.report.progress';

function read<T>(key: string): T | null {
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: unknown) {
  try {
    if (value === null) window.sessionStorage.removeItem(key);
    else window.sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage blocked (private mode): the report still works for this page view.
  }
}

/** Hand new evidence to the report page; any report in progress is for a different call, so it's discarded. */
export function stageReportEvidence(evidence: ReportEvidence) {
  write(EVIDENCE_KEY, evidence);
  write(RECORD_KEY, null);
  write(PROGRESS_KEY, null);
}

export const loadStagedEvidence = () => read<ReportEvidence>(EVIDENCE_KEY);
export const loadReport = () => read<ReportRecord>(RECORD_KEY);
export const saveReport = (record: ReportRecord) => write(RECORD_KEY, record);
export const loadProgress = () => read<Record<string, boolean>>(PROGRESS_KEY) ?? {};
export const saveProgress = (progress: Record<string, boolean>) => write(PROGRESS_KEY, progress);

export function clearReport() {
  write(EVIDENCE_KEY, null);
  write(RECORD_KEY, null);
  write(PROGRESS_KEY, null);
}

// ---------------------------------------------------------------- details

function toLocalInput(iso: string): string {
  const date = new Date(iso);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

/** Organisation filled in on new reports until organisations come from the account. */
export const DEFAULT_ORGANISATION = 'GG';

export interface ReporterPrefill {
  name?: string | null;
  email?: string | null;
}

export const emptyDetails = (evidence: ReportEvidence, reporter: ReporterPrefill = {}): CallDetails => ({
  reporterName: reporter.name?.trim() ?? '',
  reporterContact: reporter.email?.trim() ?? '',
  organisation: DEFAULT_ORGANISATION,
  callTime: evidence.source === 'live_call' ? toLocalInput(evidence.analysedAt) : '',
  platform: evidence.source === 'live_call' ? 'whatsapp_voice' : 'phone',
  callerNumber: '',
  claimedName: '',
  relationship: 'unknown',
  requests: [],
  outcome: 'nothing',
  amountInr: '',
  paymentMethod: 'upi',
  transactionRef: '',
  notes: '',
});

export function validateDetails(details: CallDetails): Partial<Record<keyof CallDetails, string>> {
  const errors: Partial<Record<keyof CallDetails, string>> = {};
  if (!details.reporterName.trim()) errors.reporterName = 'Enter your name.';
  if (!details.callTime) errors.callTime = 'Enter when the call happened.';
  if (details.outcome === 'sent_money' && !(Number(details.amountInr) > 0)) errors.amountInr = 'Enter the amount you sent.';
  return errors;
}

export function newReportId(now = new Date()): string {
  const day = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
  const suffix = Math.random().toString(36).slice(2, 6).toUpperCase();
  return `GG-${day}-${suffix}`;
}

export const formatLocalDateTime = (value: string) =>
  value ? new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : 'Not recorded';

const listJoin = (items: string[]) =>
  items.length <= 1 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items.at(-1)}`;

/** One paragraph a police officer or bank can read first. */
export function summarise({ details, evidence }: Pick<ReportRecord, 'details' | 'evidence'>): string {
  const claimed = details.claimedName.trim()
    ? `${details.claimedName.trim()} (${relationshipLabel[details.relationship].toLowerCase()})`
    : details.relationship === 'unknown'
      ? 'someone who did not say who they were'
      : `a ${relationshipLabel[details.relationship].toLowerCase()}`;
  const asked = details.requests.length ? ` The caller asked them to ${listJoin(details.requests.map((r) => requestLabel[r].toLowerCase()))}.` : '';
  const outcome =
    details.outcome === 'sent_money'
      ? ` ${details.reporterName.trim()} sent ₹${Number(details.amountInr).toLocaleString('en-IN')} by ${paymentLabel[details.paymentMethod]}.`
      : details.outcome === 'shared_info'
        ? ` ${details.reporterName.trim()} shared some information with the caller.`
        : ` ${details.reporterName.trim()} did not act on the request.`;
  const analysed = evidence.source === 'live_call' ? 'during the call' : `from the recording "${evidence.reference}"`;

  return (
    `On ${formatLocalDateTime(details.callTime)}, ${details.reporterName.trim()} received a ${platformLabel[details.platform].toLowerCase()} ` +
    `from ${details.callerNumber.trim() || 'an unknown number'} claiming to be ${claimed}.${asked}${outcome} ` +
    `The voice detector (${evidence.detector}) analysed ${evidence.speechSeconds.toFixed(1)} seconds of the caller's speech ${analysed}: ` +
    `${evidence.counts.synthetic} of ${evidence.windows.length} stretches sounded AI-generated, giving a synthetic-voice risk of ` +
    `${evidence.riskPercent}%, at or above the ${REPORT_THRESHOLD}% reporting threshold.`
  );
}
