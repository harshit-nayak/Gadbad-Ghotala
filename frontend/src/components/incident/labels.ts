import type {
  AttackType,
  AuditCategory,
  CallOutcome,
  DocumentSource,
  IncidentStatus,
  RequestKind,
  RiskLevel,
  SignalId,
  VoiceProfileStatus,
} from '../../domain/types';
import type { IconName } from '../ui/Icon';
import type { Tone } from '../ui/Pill';

export const riskLevelLabel: Record<RiskLevel, string> = { low: 'Low', medium: 'Medium', high: 'High' };
export const riskLevelTone: Record<RiskLevel, Tone> = { low: 'safe', medium: 'warn', high: 'risk' };
export const riskColor: Record<RiskLevel, string> = { low: 'var(--safe)', medium: 'var(--warn)', high: 'var(--risk)' };

export const incidentStatusLabel: Record<IncidentStatus, string> = {
  new: 'New',
  investigating: 'Investigating',
  contained: 'Contained',
  closed: 'Closed',
};
export const incidentStatusTone: Record<IncidentStatus, Tone> = {
  new: 'risk',
  investigating: 'warn',
  contained: 'analysis',
  closed: 'neutral',
};

export const outcomeLabel: Record<CallOutcome, string> = {
  impersonation_confirmed: 'Impersonation confirmed, request blocked',
  request_confirmed: 'Request confirmed by claimed caller',
  escalated: 'Escalated to Security before verification',
  ended_unverified: 'Call ended without verification',
};
export const outcomeShort: Record<CallOutcome, string> = {
  impersonation_confirmed: 'Confirmed fraud',
  request_confirmed: 'Genuine',
  escalated: 'Escalated',
  ended_unverified: 'Unverified',
};

export const attackTypeLabel: Record<AttackType, string> = {
  executive_voice_clone: 'Executive voice clone',
  vendor_impersonation: 'Vendor payment redirection',
  it_helpdesk_impersonation: 'IT helpdesk impersonation',
  payroll_change: 'Payroll account change',
};

export const requestKindLabel: Record<RequestKind, string> = {
  funds_transfer: 'Funds transfer',
  payment_detail_change: 'Payment detail change',
  data_sharing: 'Data sharing',
  credential_request: 'Credential request',
};

export const signalShortLabel: Record<SignalId, string> = {
  audioQuality: 'Audio quality',
  voiceMatch: 'Voice match',
  syntheticSpeech: 'Synthetic speech',
  prosody: 'Prosody',
  codecArtifacts: 'Codec artifacts',
  backgroundNoise: 'Background noise',
  watermark: 'Watermark',
  contextIntent: 'Context & intent',
};

/** Fixed signal colours so the same signal reads the same in every chart. */
export const signalColor: Record<SignalId, string> = {
  voiceMatch: 'var(--sig-voice)',
  syntheticSpeech: 'var(--sig-synthetic)',
  contextIntent: 'var(--sig-context)',
  prosody: 'var(--sig-prosody)',
  codecArtifacts: 'var(--sig-codec)',
  backgroundNoise: 'var(--sig-noise)',
  watermark: 'var(--sig-watermark)',
  audioQuality: 'var(--ink-subtle)',
};

export const profileStatusLabel: Record<VoiceProfileStatus, { text: string; tone: Tone }> = {
  trusted: { text: 'Trusted', tone: 'safe' },
  enrolling: { text: 'Enrolling', tone: 'analysis' },
  needs_review: { text: 'Needs review', tone: 'warn' },
};

export const documentSourceLabel: Record<DocumentSource, { text: string; icon: IconName }> = {
  upload: { text: 'Upload', icon: 'upload' },
  website: { text: 'Website', icon: 'globe' },
  extension: { text: 'Browser extension', icon: 'puzzle' },
  api: { text: 'API', icon: 'code' },
  pasted: { text: 'Pasted content', icon: 'fileText' },
};

export const auditCategoryLabel: Record<AuditCategory, string> = {
  verification: 'Verification',
  employee_action: 'Employee action',
  security_response: 'Security response',
  profile: 'Voice profile',
  report: 'Report',
  system: 'System',
};
