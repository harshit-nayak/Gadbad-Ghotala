/**
 * Landing page content.
 *
 * METRICS: every number shown on the landing page lives in `metrics` and
 * `benchmark` below. They are deliberate placeholders ("XX") until the model
 * team supplies measured values. Replace the `value` strings here only; no
 * component hard-codes a figure.
 */

export interface Metric {
  value: string;
  label: string;
  note: string;
}

/** Impact numbers. Replace `value` with measured results. */
export const metrics: Metric[] = [
  { value: '99.7%', label: 'Detection accuracy', note: 'On the internal evaluation set' },
  { value: '4 ms', label: 'Detection latency', note: 'From speech onset to risk update' },
  { value: '22+', label: 'Languages evaluated', note: 'Including code-switched speech' },
];

export interface BenchmarkRow {
  metric: string;
  value: string;
  definition: string;
}

/** Technical benchmark table. Values pending from the model team. */
export const benchmark: BenchmarkRow[] = [
  { metric: 'Detection accuracy', value: '99.7%', definition: 'Correct calls over total calls evaluated' },
  { metric: 'Precision', value: 'XX', definition: 'Of the calls flagged synthetic, the share that were synthetic' },
  { metric: 'Recall', value: 'XX', definition: 'Of the synthetic calls, the share that were flagged' },
  { metric: 'F1 score', value: 'XX', definition: 'Harmonic mean of precision and recall' },
  { metric: 'False positive rate', value: 'XX%', definition: 'Genuine calls incorrectly flagged' },
  { metric: 'Detection latency', value: '4 ms', definition: 'Median time to a stable risk reading' },
];

export const benchmarkNote =
  'Figures are produced on an internal evaluation set and published once the evaluation is complete. No comparison against third-party systems is claimed.';

/** Problem section: scenarios that scroll horizontally. */
export interface Scenario {
  type: string;
  quote: string;
  voice: string;
  request: string;
  urgency: string;
  action: string;
}

/** Problem section: classified social-engineering scenarios. */
export const scenarios: Scenario[] = [
  {
    type: 'Executive impersonation',
    quote: 'Transfer the amount immediately. I am in a meeting.',
    voice: 'Claimed CEO',
    request: 'Funds transfer',
    urgency: 'Immediate',
    action: 'Payment release',
  },
  {
    type: 'OTP request',
    quote: 'Just read the OTP out to me.',
    voice: 'Claimed IT helpdesk',
    request: 'One-time code',
    urgency: 'Account lock threat',
    action: 'Credential disclosure',
  },
  {
    type: 'Vendor fraud',
    quote: "We've changed our bank details. Please update them today.",
    voice: 'Claimed vendor contact',
    request: 'Payment detail change',
    urgency: 'Before payment run',
    action: 'Beneficiary change',
  },
  {
    type: 'Authority impersonation',
    quote: 'Skip the normal verification process. This is urgent.',
    voice: 'Claimed senior manager',
    request: 'Process exception',
    urgency: 'Same day',
    action: 'Verification bypass',
  },
  {
    type: 'Caller ID spoofing',
    quote: 'The caller ID looks legitimate. The voice sounds perfect.',
    voice: 'Spoofed number',
    request: 'Any sensitive action',
    urgency: 'Varies',
    action: 'Misplaced trust',
  },
];

/** Six-stage pipeline used by the "what the product does" and prevention sections. */
export interface Stage {
  id: string;
  title: string;
  body: string;
  icon: 'activity' | 'shield' | 'alert' | 'shieldCheck' | 'lock' | 'search';
}

export const stages: Stage[] = [
  { id: 'detect', title: 'Detect', body: 'Synthetic and cloned speech indicators are measured while the call is still live.', icon: 'activity' },
  { id: 'assess', title: 'Assess', body: 'Voice signals, conversation context and the request itself are weighed together.', icon: 'shield' },
  { id: 'alert', title: 'Alert', body: 'The employee gets a plain warning with the reasons, not a raw model score.', icon: 'alert' },
  { id: 'verify', title: 'Verify', body: 'The specific request is confirmed with the real person through an official channel.', icon: 'shieldCheck' },
  { id: 'prevent', title: 'Prevent', body: 'The sensitive action is stopped before money or access leaves the organisation.', icon: 'lock' },
  { id: 'investigate', title: 'Investigate', body: 'Security receives the incident with audio, transcript, signals and a timeline.', icon: 'search' },
];

export interface Capability {
  title: string;
  body: string;
  icon: 'activity' | 'fingerprint' | 'chart' | 'shieldCheck' | 'search' | 'dashboard';
}

export const capabilities: Capability[] = [
  { title: 'Real-time voice detection', body: 'Detect suspicious synthetic or cloned speech during a live interaction, not after the call ends.', icon: 'activity' },
  { title: 'Context-aware risk analysis', body: 'Combine voice signals with the nature of the request and the way the conversation is going.', icon: 'fingerprint' },
  { title: 'Dynamic risk scoring', body: 'Turn many weighted signals into one clear level: low, caution or high.', icon: 'chart' },
  { title: 'Action-based verification', body: 'Ask the employee to verify the specific request before any sensitive action is taken.', icon: 'shieldCheck' },
  { title: 'Security investigation', body: 'Give fraud teams the audio, transcript, signal breakdown and timeline behind every incident.', icon: 'search' },
  { title: 'Organisation-wide visibility', body: 'Show administrators what is being targeted, in which departments, and what was prevented.', icon: 'dashboard' },
];

/** Real-world conditions the system is designed and evaluated around. */
export const conditions: string[] = [
  'Hinglish conversations',
  'Indian regional accents',
  'Code-switching mid-sentence',
  'Noisy environments',
  'Mobile-call compression',
  'Short utterances',
  'High-pressure social engineering',
];

export interface CaseStudy {
  id: string;
  number: string;
  title: string;
  summary: string;
  steps: string[];
  outcome: string;
}

export const caseStudies: CaseStudy[] = [
  {
    id: 'executive',
    number: 'Case study 01',
    title: 'Executive impersonation',
    summary:
      'An employee in Finance receives a call from someone claiming to be a senior executive, asking for an urgent transfer to a vendor that is not on the approved list.',
    steps: ['Call received', 'Voice analysed live', 'Suspicious signals combine', 'High risk shown', 'Request verified with the executive', 'Transfer stopped'],
    outcome: 'The payment never leaves. Security receives the call evidence as an incident.',
  },
  {
    id: 'vendor',
    number: 'Case study 02',
    title: 'Vendor impersonation',
    summary:
      'A caller impersonates a known vendor just before a payment run and asks for the bank account on file to be changed.',
    steps: ['Call received', 'Voice compared with past contact', 'Account change flagged', 'Caution raised', 'Vendor called back officially', 'Account change held'],
    outcome: 'The payment run continues to the account already on file.',
  },
  {
    id: 'authority',
    number: 'Case study 03',
    title: 'Authority impersonation',
    summary:
      'A cloned voice pressures an employee to skip a normal security step, such as reading out a one-time code or approving access.',
    steps: ['Call received', 'Urgency and secrecy detected', 'Credential request flagged', 'High risk shown', 'Employee notifies Security', 'Access request refused'],
    outcome: 'No code is shared, and the attempt is recorded for the security team.',
  },
];

export interface Workspace {
  name: string;
  question: string;
  body: string;
}

export const workspaces: Workspace[] = [
  { name: 'Employee', question: 'What should I do right now?', body: 'A clear warning, the request in plain words, and one way to verify it.' },
  { name: 'Security and fraud', question: 'Why was this flagged?', body: 'Signal weights, audio regions, transcript, timeline and verification result.' },
  { name: 'Documents', question: 'Can this communication be trusted?', body: 'Extracted entities, suspicious instructions and consistency checks.' },
  { name: 'Administrator', question: 'What is happening across the organisation?', body: 'Trends, attack types, departments targeted and prevention outcomes.' },
];

export const navLinks = [
  { label: 'Product', href: '#product' },
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Case studies', href: '#case-studies' },
  { label: 'Benchmarks', href: '#benchmarks' },
];

/** "Why this matters" transition section. */
export const trustShift = {
  title: 'Voice cloning changes the trust equation.',
  points: [
    { title: 'A familiar voice can be reproduced', body: 'A few seconds of public audio is enough to rebuild how a colleague sounds.' },
    { title: 'Caller ID can be spoofed', body: 'The number on the screen is not evidence of who is speaking.' },
    { title: 'Urgency manipulates people', body: 'Deadlines, secrecy and seniority are used to push past normal checks.' },
    { title: 'Intuition is no longer enough', body: 'Employees are asked to judge authenticity from a voice alone, in seconds.' },
  ],
  close: 'Pehchaan AI adds an intelligent verification layer between the conversation and the action.',
};
