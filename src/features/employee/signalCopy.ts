/**
 * Plain-language wording for the employee. Technical names stay in the
 * Security view; the employee only needs "what, why, what to do".
 * Codec, background noise and watermark checks still run, but only
 * Security sees them; the employee gets the five checks that explain the risk.
 */
import type { Tone } from '../../components/ui/Pill';
import type { SignalId } from '../../domain/types';

export interface EmployeeStatus {
  text: string;
  tone: Tone;
}

interface EmployeeSignalCopy {
  label: string;
  hint: (claimedFirstName: string) => string;
  status: (risk: number) => EmployeeStatus;
}

const band = (risk: number, low: EmployeeStatus, medium: EmployeeStatus, high: EmployeeStatus) =>
  risk < 40 ? low : risk < 70 ? medium : high;

export const employeeSignalCopy: Partial<Record<SignalId, EmployeeSignalCopy>> = {
  audioQuality: {
    label: 'Call audio',
    hint: () => 'Line quality, so checks can be trusted',
    status: (r) => (r < 30 ? { text: 'Clear', tone: 'safe' } : r < 60 ? { text: 'Fair', tone: 'neutral' } : { text: 'Poor', tone: 'warn' }),
  },
  voiceMatch: {
    label: 'Voice match',
    hint: (name) => `Compared with ${name}'s verified voice`,
    status: (r) => band(r, { text: 'Matches', tone: 'safe' }, { text: 'Partial', tone: 'warn' }, { text: "Doesn't match", tone: 'risk' }),
  },
  syntheticSpeech: {
    label: 'AI-generated voice',
    hint: () => 'Signs the voice was produced by software',
    status: (r) => band(r, { text: 'Not detected', tone: 'safe' }, { text: 'Possible', tone: 'warn' }, { text: 'Likely', tone: 'risk' }),
  },
  prosody: {
    label: 'Speaking style',
    hint: () => 'Rhythm, pitch and pauses',
    status: (r) => band(r, { text: 'Natural', tone: 'safe' }, { text: 'Slightly off', tone: 'warn' }, { text: 'Unusual', tone: 'risk' }),
  },
  contextIntent: {
    label: 'Context of the request',
    hint: () => 'Money, secrecy and time pressure',
    status: (r) => band(r, { text: 'Routine', tone: 'safe' }, { text: 'Sensitive', tone: 'warn' }, { text: 'High pressure', tone: 'risk' }),
  },
};

export const firstName = (fullName: string) => fullName.split(' ')[0];
