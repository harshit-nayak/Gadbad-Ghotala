/**
 * The single canonical demo incident used across Employee, Security and Admin.
 * A caller claiming to be Rahul Sharma (CEO) asks Priya Menon (Finance) for a
 * ₹20,00,000 transfer to a new external vendor.
 *
 * All values are illustrative mock data. Scores are per-call signal outputs
 * for the demo, not model accuracy claims.
 */
import { riskLevelFor, weightedRiskScore } from '../domain/risk';
import { formatInr } from '../domain/format';
import type {
  CallOutcome,
  DetectionSignal,
  Incident,
  SignalId,
  TimelineEvent,
  TranscriptLine,
  Verification,
  VerificationMethod,
} from '../domain/types';
import { people } from './people';

export const INCIDENT_ID = '78421';

const DAY = '2026-09-11';
const at = (hms: string) => `${DAY}T${hms}+05:30`;

export const signals: DetectionSignal[] = [
  {
    id: 'audioQuality',
    label: 'Audio quality',
    weight: 0,
    risk: 38,
    reading: 'Fair. Narrowband audio with intermittent packet loss.',
    evidence: ['Narrowband voice channel', 'Short packet-loss gaps'],
    conclusive: true,
  },
  {
    id: 'voiceMatch',
    label: 'Voice match',
    weight: 0.25,
    risk: 82,
    reading: "Similarity 0.18 against Rahul Sharma's trusted voice profile (match threshold 0.72).",
    evidence: ['Profile built only from verified calls', 'Timbre and formant structure diverge'],
    conclusive: true,
  },
  {
    id: 'syntheticSpeech',
    label: 'Synthetic speech',
    weight: 0.25,
    risk: 89,
    reading: 'Strong indicators of generated speech.',
    evidence: ['Unnaturally regular breath and pause spacing', 'Over-smooth spectral detail'],
    conclusive: true,
  },
  {
    id: 'prosody',
    label: 'Prosody',
    weight: 0.1,
    risk: 76,
    reading: "Flat pitch contour and rhythm unlike Rahul's reference calls.",
    evidence: ['Low pitch variation under stress', 'Hindi and English segments share identical cadence'],
    conclusive: true,
  },
  {
    id: 'codecArtifacts',
    label: 'Codec artifacts',
    weight: 0.08,
    risk: 68,
    reading: 'Re-encoding traces inconsistent with a direct mobile call.',
    evidence: ['VoIP audio transcoded to a mobile codec', 'Caller ID presented as mobile'],
    conclusive: true,
  },
  {
    id: 'backgroundNoise',
    label: 'Background noise',
    weight: 0.07,
    risk: 61,
    reading: 'Background segment repeats with no natural variation.',
    evidence: ['Repeating noise loop', 'Noise floor unchanged during speech'],
    conclusive: true,
  },
  {
    id: 'watermark',
    label: 'Watermark detection',
    weight: 0.05,
    risk: 50,
    reading: 'No known watermark found. Absence does not indicate a genuine voice.',
    evidence: ['Checked against known generator watermarks'],
    conclusive: false,
  },
  {
    id: 'contextIntent',
    label: 'Context & intent',
    weight: 0.2,
    risk: 94,
    reading: 'Urgent transfer to a new vendor with approval bypass and secrecy.',
    evidence: ['Financial transfer', 'Deadline pressure', 'Bypass approval', 'Move to WhatsApp'],
    conclusive: true,
  },
];


export const riskScore = weightedRiskScore(signals);

const request = {
  kind: 'funds_transfer',
  amountInr: 2_000_000,
  description: 'Transfer to external vendor',
  counterparty: 'Nexa Trade Solutions Pvt Ltd',
  counterpartyNote: 'Not in approved vendor list',
  deadline: 'within 30 minutes',
  urgency: 'high',
  pressureTactics: ['Skip approval', 'Keep it confidential', 'Move to WhatsApp'],
  requestedAt: at('14:30:29'),
} satisfies Incident['request'];

const transcript: TranscriptLine[] = [
  { at: 4, speaker: 'caller', text: 'Priya, Rahul here. Are you at your desk?' },
  { at: 8, speaker: 'employee', text: 'Yes sir, good afternoon.' },
  {
    at: 12,
    speaker: 'caller',
    text: 'Listen, ek urgent kaam hai. We are closing the vendor deal today.',
    flags: ['urgent kaam'],
  },
  {
    at: 21,
    speaker: 'caller',
    text: 'I need ₹20,00,000 transferred to Nexa Trade Solutions within the next 30 minutes.',
    flags: ['₹20,00,000 transferred', 'within the next 30 minutes'],
  },
  {
    at: 34,
    speaker: 'employee',
    text: "Sir, this vendor isn't in our approved list. Should I take it to Anil for approval?",
  },
  {
    at: 41,
    speaker: 'caller',
    text: "Nahi, don't loop anyone in. Board meeting mein hoon, I will sign the approval later.",
    flags: ["don't loop anyone in", 'sign the approval later'],
  },
  {
    at: 52,
    speaker: 'caller',
    text: 'Keep this confidential for now. Main account details WhatsApp kar raha hoon.',
    flags: ['Keep this confidential', 'WhatsApp kar raha hoon'],
  },
  { at: 61, speaker: 'employee', text: 'Okay sir, one moment.' },
  { at: 68, speaker: 'caller', text: 'Priya? Transfer ho gaya? The vendor is waiting.', flags: ['Transfer ho gaya?'] },
  { at: 75, speaker: 'employee', text: "Sir, I'm confirming it through the verification app first." },
  { at: 82, speaker: 'caller', text: 'There is no time for this. Just do it now, I am authorising it.', flags: ['no time for this', 'Just do it now'] },
];

const baseTimeline: TimelineEvent[] = [
  { at: at('14:30:08'), actor: 'system', label: 'External call reached work device; caller ID matched Rahul Sharma', tone: 'info' },
  { at: at('14:30:10'), actor: 'employee', label: 'Priya Menon accepted the call' },
  { at: at('14:30:19'), actor: 'system', label: "Voice match low against Rahul Sharma's trusted profile", tone: 'medium' },
  { at: at('14:30:24'), actor: 'system', label: 'Synthetic speech indicators detected', tone: 'medium' },
  { at: at('14:30:29'), actor: 'system', label: `Request detected: ${formatInr(request.amountInr)} transfer to new vendor`, tone: 'high' },
  { at: at('14:31:09'), actor: 'system', label: `High-risk alert shown to employee (score ${riskScore})`, tone: 'high' },
];

/** Everything about the call that is known before the employee acts. */
export const liveCall = {
  claimedIdentity: people.rahulSharma,
  receiver: people.priyaMenon,
  callerNumber: people.rahulSharma.mobile ?? '',
  request,
  riskScore,
  riskLevel: riskLevelFor(riskScore),
  signals,
  reasons: [
    'Signs of a computer-generated voice.',
    "The voice doesn't sufficiently match Rahul Sharma's verified voice.",
    'Unusual urgency: payment asked for within 30 minutes.',
    'High-risk financial request to a vendor not on the approved list.',
  ],
  metadata: {
    direction: 'external',
    network: 'VoIP',
    callerIdNote: "Caller ID matches Rahul Sharma's mobile, but audio arrived via a VoIP gateway",
    language: 'Hinglish',
    audioQuality: 'Fair',
    backgroundNoise: 'Low, repeating pattern',
    codec: 'AMR-NB (transcoded)',
    durationSec: 94,
    analysedSec: 88,
    startedAt: at('14:30:08'),
  },
  transcript,
  attackType: 'executive_voice_clone',
  office: 'Mumbai',
  audioRegions: [
    { start: 4, end: 11, signal: 'voiceMatch', label: 'Voice does not match trusted profile', level: 'high' },
    { start: 12, end: 20, signal: 'syntheticSpeech', label: 'Regular breath spacing, over-smooth spectrum', level: 'high' },
    { start: 21, end: 33, signal: 'contextIntent', label: 'Transfer amount and 30-minute deadline', level: 'high' },
    { start: 26, end: 38, signal: 'backgroundNoise', label: 'Background loop repeats', level: 'medium' },
    { start: 41, end: 51, signal: 'prosody', label: 'Flat pitch across Hindi and English', level: 'high' },
    { start: 41, end: 60, signal: 'contextIntent', label: 'Approval bypass, secrecy, move to WhatsApp', level: 'high' },
    { start: 82, end: 90, signal: 'contextIntent', label: 'Pressure to act before verification', level: 'high' },
  ],
} satisfies Partial<Incident>;

/**
 * Timeline script for the live analysis simulation.
 * `start` and `end` are fractions of the simulated analysis window; `from`
 * is the provisional reading before the signal settles on its final risk.
 */
export const liveAnalysisScript = {
  durationMs: 14_000,
  baselineRisk: 12,
  requestDetectedAt: 0.56,
  signals: {
    audioQuality: { from: 30, start: 0, end: 0.12 },
    voiceMatch: { from: 30, start: 0.06, end: 0.45 },
    syntheticSpeech: { from: 18, start: 0.14, end: 0.62 },
    codecArtifacts: { from: 20, start: 0.18, end: 0.52 },
    prosody: { from: 25, start: 0.22, end: 0.66 },
    backgroundNoise: { from: 20, start: 0.3, end: 0.7 },
    watermark: { from: 50, start: 0.34, end: 0.74 },
    contextIntent: { from: 10, start: 0.52, end: 0.94 },
  } satisfies Record<SignalId, { from: number; start: number; end: number }>,
};

const verificationFor = (outcome: CallOutcome, method: VerificationMethod): Verification => {
  const via =
    method === 'official_callback' ? 'on call-back to official line' : 'on registered device';
  switch (outcome) {
    case 'impersonation_confirmed':
      return { method, result: 'denied', summary: `Denied by Rahul Sharma ${via}`, at: at('14:31:40') };
    case 'request_confirmed':
      return { method, result: 'confirmed', summary: `Confirmed by Rahul Sharma ${via}`, at: at('14:31:40') };
    case 'escalated':
      return { method: 'security_team', result: 'pending', summary: 'Escalated to Security before verification', at: at('14:31:20') };
    case 'ended_unverified':
      return { method: 'none', result: 'not_attempted', summary: 'Call ended before verification' };
  }
};

const outcomeEvents = (outcome: CallOutcome, method: VerificationMethod): TimelineEvent[] => {
  const channel =
    method === 'official_callback' ? 'Priya called back the official line' : 'Verification sent to Rahul Sharma\'s registered device';
  const created: TimelineEvent = {
    at: at('14:31:42'),
    actor: 'system',
    label: `Incident #${INCIDENT_ID} created and Security notified`,
    tone: 'info',
  };
  switch (outcome) {
    case 'impersonation_confirmed':
      return [
        { at: at('14:31:15'), actor: 'employee', label: channel },
        { at: at('14:31:40'), actor: 'claimed_person', label: 'Rahul Sharma denied making the request', tone: 'high' },
        { at: at('14:31:41'), actor: 'system', label: 'Transfer blocked and call ended', tone: 'safe' },
        created,
      ];
    case 'request_confirmed':
      return [
        { at: at('14:31:15'), actor: 'employee', label: channel },
        { at: at('14:31:40'), actor: 'claimed_person', label: 'Rahul Sharma confirmed the request', tone: 'safe' },
        { ...created, label: `Incident #${INCIDENT_ID} logged for review (high-risk signals present)` },
      ];
    case 'escalated':
      return [
        { at: at('14:31:20'), actor: 'employee', label: 'Priya notified the Security team; request on hold', tone: 'medium' },
        created,
      ];
    case 'ended_unverified':
      return [
        { at: at('14:31:12'), actor: 'employee', label: 'Priya ended the call without verifying', tone: 'medium' },
        created,
      ];
  }
};

/** Seconds into the call when it ended, per outcome (call started 14:30:08). */
const callEndSec: Record<CallOutcome, number> = {
  impersonation_confirmed: 94,
  request_confirmed: 94,
  escalated: 74,
  ended_unverified: 64,
};

/** Build incident #78421 for whichever path the employee took in the demo. */
export function createIncident78421(outcome: CallOutcome, method: VerificationMethod): Incident {
  const end = callEndSec[outcome];
  return {
    id: INCIDENT_ID,
    createdAt: at('14:31:42'),
    status: outcome === 'impersonation_confirmed' ? 'contained' : 'new',
    outcome,
    ...liveCall,
    // Shorter calls only contain the audio, transcript and findings up to the hang-up.
    metadata: { ...liveCall.metadata, durationSec: end, analysedSec: end - 6 },
    transcript: liveCall.transcript.filter((line) => line.at < end - 2),
    audioRegions: liveCall.audioRegions
      .filter((r) => r.start < end - 2)
      .map((r) => ({ ...r, end: Math.min(r.end, end - 1) })),
    verification: verificationFor(outcome, method),
    timeline: [...baseTimeline, ...outcomeEvents(outcome, method)],
    voiceProfileUpdate: 'excluded',
    live: true,
  };
}
