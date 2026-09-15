/**
 * Core domain model for Pehchaan AI.
 * These types are the contract between the UI and a future backend.
 * Mock data in src/data conforms to them; real API responses should too.
 */

export type RiskLevel = 'low' | 'medium' | 'high';

export type SignalId =
  | 'audioQuality'
  | 'voiceMatch'
  | 'syntheticSpeech'
  | 'prosody'
  | 'codecArtifacts'
  | 'backgroundNoise'
  | 'watermark'
  | 'contextIntent';

export interface Person {
  id: string;
  name: string;
  initials: string;
  role: string;
  /** Short role for compact places, e.g. "CEO" */
  roleShort: string;
  department: string;
  location: string;
  email?: string;
  mobile?: string;
  /** Number from the company directory, used for call-back verification */
  officialLine?: string;
}

export interface DetectionSignal {
  id: SignalId;
  /** Analyst-facing name */
  label: string;
  /** Contribution to the weighted score. 0 means context only (not scored). */
  weight: number;
  /** 0 to 100, higher is riskier */
  risk: number;
  /** Analyst-facing finding in one sentence */
  reading: string;
  evidence: string[];
  /** False when the signal cannot support a conclusion either way */
  conclusive: boolean;
}

export type CallNetwork = 'Mobile' | 'VoIP' | 'Landline';
export type CallLanguage = 'Hinglish' | 'English' | 'Hindi' | 'Tamil' | 'Marathi';

export interface CallMetadata {
  direction: 'external' | 'internal';
  network: CallNetwork;
  callerIdNote: string;
  language: CallLanguage;
  audioQuality: 'Good' | 'Fair' | 'Poor';
  backgroundNoise: string;
  codec: string;
  durationSec: number;
  analysedSec: number;
  startedAt: string;
}

export type RequestKind =
  | 'funds_transfer'
  | 'payment_detail_change'
  | 'data_sharing'
  | 'credential_request';

export interface RequestedAction {
  kind: RequestKind;
  amountInr?: number;
  /** Plain description, e.g. "Transfer to external vendor" */
  description: string;
  counterparty: string;
  counterpartyNote: string;
  deadline: string;
  urgency: RiskLevel;
  pressureTactics: string[];
  requestedAt: string;
}

export interface TranscriptLine {
  /** Seconds from call start */
  at: number;
  speaker: 'caller' | 'employee';
  text: string;
  /** Exact substrings of `text` to highlight as risky */
  flags?: string[];
}

export type VerificationMethod =
  | 'claimed_person_device'
  | 'official_callback'
  | 'security_team'
  | 'none';

export type VerificationResult = 'denied' | 'confirmed' | 'pending' | 'not_attempted';

export interface Verification {
  method: VerificationMethod;
  result: VerificationResult;
  summary: string;
  at?: string;
}

export type CallOutcome =
  | 'impersonation_confirmed'
  | 'request_confirmed'
  | 'escalated'
  | 'ended_unverified';

export type IncidentStatus = 'new' | 'investigating' | 'contained' | 'closed';

export interface TimelineEvent {
  at: string;
  actor: 'system' | 'employee' | 'claimed_person' | 'security';
  label: string;
  tone?: RiskLevel | 'safe' | 'info';
}

export interface Incident {
  id: string;
  createdAt: string;
  status: IncidentStatus;
  outcome: CallOutcome;
  riskScore: number;
  riskLevel: RiskLevel;
  claimedIdentity: Person;
  receiver: Person;
  callerNumber: string;
  request: RequestedAction;
  metadata: CallMetadata;
  signals: DetectionSignal[];
  /** Plain-language reasons shown to the employee */
  reasons: string[];
  transcript: TranscriptLine[];
  verification: Verification;
  timeline: TimelineEvent[];
  /** Only verified genuine, low-risk calls may update a trusted voice profile */
  voiceProfileUpdate: 'excluded' | 'eligible';
  attackType: AttackType;
  /** Office of the employee who received the call */
  office: Office;
  /** Time ranges in the call audio where signals fired */
  audioRegions: AudioRegion[];
  /** Analyst handling the incident, if assigned */
  assignee?: string;
  /** True for the incident created live in this session */
  live?: boolean;
}

export type AttackType =
  | 'executive_voice_clone'
  | 'vendor_impersonation'
  | 'it_helpdesk_impersonation'
  | 'payroll_change';

export type Office = 'Mumbai' | 'Bengaluru' | 'Delhi NCR' | 'Hyderabad' | 'Chennai' | 'Pune' | 'Kolkata';

export interface AudioRegion {
  start: number;
  end: number;
  signal: SignalId;
  label: string;
  level: RiskLevel;
}

/** One day of organisation-wide call analysis counts. */
export interface DailyCallStats {
  date: string;
  callsAnalysed: number;
  /** Calls that reached medium risk (verification prompted, no incident unless escalated) */
  mediumRisk: number;
}

export type VoiceProfileStatus = 'trusted' | 'enrolling' | 'needs_review';

export interface VerifiedCall {
  at: string;
  counterpart: string;
  durationSec: number;
  channel: CallNetwork;
  verification: string;
  /** Whether this call was used to update the profile, and why not if excluded */
  usedForUpdate: boolean;
  note: string;
}

export interface VoiceProfile {
  person: Person;
  status: VoiceProfileStatus;
  enrolledAt: string;
  lastVerifiedUpdate: string;
  referenceSeconds: number;
  verifiedCalls: VerifiedCall[];
  /** Match threshold used for this profile */
  matchThreshold: number;
}

export type DocumentSource = 'upload' | 'website' | 'extension' | 'api' | 'pasted';

export interface ExtractedEntity {
  kind: 'amount' | 'organisation' | 'person' | 'bank_account' | 'ifsc' | 'email' | 'url' | 'deadline' | 'phone';
  value: string;
  note?: string;
  flagged: boolean;
}

export interface SuspiciousInstruction {
  quote: string;
  reason: string;
  level: RiskLevel;
}

export interface ConsistencyCheck {
  label: string;
  result: 'pass' | 'fail' | 'warn';
  detail: string;
}

export interface DocumentAnalysis {
  id: string;
  name: string;
  source: DocumentSource;
  sourceDetail: string;
  submittedBy: string;
  analysedAt: string;
  /** 'analysing' only for analyses started in this session */
  state: 'analysing' | 'complete';
  meta: string;
  excerpt: string[];
  entities: ExtractedEntity[];
  instructions: SuspiciousInstruction[];
  consistency: ConsistencyCheck[];
  contextSummary: string;
  requestedAction: string;
  reasons: string[];
  recommendation: string;
  riskScore: number;
  riskLevel: RiskLevel;
  /** Counterparty that may link to a call incident */
  counterparty?: string;
  reviewed?: boolean;
  sharedWithSecurity?: boolean;
}

export type AuditCategory = 'verification' | 'employee_action' | 'security_response' | 'profile' | 'report' | 'system';

export interface AuditEvent {
  id: string;
  at: string;
  category: AuditCategory;
  actor: string;
  action: string;
  target: string;
  incidentId?: string;
}
