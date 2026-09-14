/**
 * Seeded history of call incidents for the 30 days before the demo.
 * Every Security and Administrator number is computed from this list plus
 * the incident created live in the session, so the views always agree.
 */
import { riskLevelFor, weightedRiskScore } from '../domain/risk';
import { formatInr } from '../domain/format';
import type {
  AttackType,
  AudioRegion,
  CallLanguage,
  CallOutcome,
  DetectionSignal,
  Incident,
  IncidentStatus,
  Person,
  RequestKind,
  SignalId,
  TimelineEvent,
  TranscriptLine,
} from '../domain/types';
import { analysts, people } from './people';
import { signals as referenceSignals } from './incident78421';
import { seeded } from './seed';

const rng = seeded(20260911);

const FIRST_DAY = Date.UTC(2026, 7, 13); // 13 Aug 2026
const DAYS = 29; // through 10 Sep; the demo incident is the first of 11 Sep
const DAY_MS = 86_400_000;

interface Scenario {
  attackType: AttackType;
  weight: number;
  claimed: Person[];
  receivers: Person[];
  kind: RequestKind;
}

const scenarios: Scenario[] = [
  {
    attackType: 'executive_voice_clone',
    weight: 6,
    claimed: [people.rahulSharma, people.rahulSharma, people.anilKapoor, people.anilKapoor, people.deepakVerma],
    receivers: [people.priyaMenon, people.arjunMehta, people.rohanDas, people.lakshmiReddy, people.meeraJoshi],
    kind: 'funds_transfer',
  },
  {
    attackType: 'vendor_impersonation',
    weight: 3,
    claimed: [people.nehaIyer, people.anilKapoor],
    receivers: [people.rohanDas, people.lakshmiReddy, people.priyaMenon],
    kind: 'payment_detail_change',
  },
  {
    attackType: 'it_helpdesk_impersonation',
    weight: 2,
    claimed: [people.sanaQureshi, people.deepakVerma],
    receivers: [people.farhanSheikh, people.meeraJoshi, people.kavyaNair, people.nehaIyer],
    kind: 'credential_request',
  },
  {
    attackType: 'payroll_change',
    weight: 2,
    claimed: [people.vikramRao],
    receivers: [people.kavyaNair, people.arjunMehta],
    kind: 'payment_detail_change',
  },
];

const counterparties = [
  'Orbit Logistics LLP',
  'Sahyadri Infra Projects',
  'Bluepeak Consulting Pvt Ltd',
  'Veda Exports',
  'Tristar Industrial Supplies',
  'Coastal Freight Services',
];
const amounts = [350_000, 480_000, 750_000, 990_000, 1_200_000, 1_500_000, 1_850_000, 2_500_000, 3_200_000, 4_800_000];
const languages: [CallLanguage, number][] = [
  ['Hinglish', 40],
  ['English', 28],
  ['Hindi', 16],
  ['Tamil', 8],
  ['Marathi', 8],
];

const iso = (ms: number) => new Date(ms).toISOString().replace('.000Z', 'Z');
const clamp = (n: number) => Math.max(4, Math.min(98, Math.round(n)));
const first = (p: Person) => p.name.split(' ')[0];

function requestFor(s: Scenario, requestedAt: string) {
  switch (s.attackType) {
    case 'executive_voice_clone': {
      const amountInr = rng.pick(amounts);
      const counterparty = rng.pick(counterparties);
      return {
        kind: s.kind,
        amountInr,
        description: 'Transfer to external vendor',
        counterparty,
        counterpartyNote: 'Not in approved vendor list',
        deadline: rng.pick(['within 30 minutes', 'before 4 pm', 'within the hour']),
        urgency: 'high' as const,
        pressureTactics: ['Skip approval', 'Keep it confidential'],
        requestedAt,
      };
    }
    case 'vendor_impersonation':
      return {
        kind: s.kind,
        amountInr: rng.pick(amounts),
        description: 'Change vendor bank account before payment run',
        counterparty: rng.pick(counterparties),
        counterpartyNote: 'New account differs from vendor master',
        deadline: 'before today’s payment run',
        urgency: 'high' as const,
        pressureTactics: ['Payment run deadline', 'Skip call-back check'],
        requestedAt,
      };
    case 'it_helpdesk_impersonation':
      return {
        kind: s.kind,
        description: 'Share VPN code and email password',
        counterparty: 'IT helpdesk (claimed)',
        counterpartyNote: 'IT never asks for passwords by phone',
        deadline: 'immediately',
        urgency: 'medium' as const,
        pressureTactics: ['Account lock threat'],
        requestedAt,
      };
    case 'payroll_change':
      return {
        kind: s.kind,
        description: 'Change salary account for senior staff',
        counterparty: 'New salary account',
        counterpartyNote: 'Change requested outside HR system',
        deadline: 'before payroll cut-off',
        urgency: 'medium' as const,
        pressureTactics: ['Payroll cut-off', 'Keep it confidential'],
        requestedAt,
      };
  }
}

function transcriptFor(s: Scenario, claimed: Person, receiver: Person, request: Incident['request']): TranscriptLine[] {
  const amount = request.amountInr ? formatInr(request.amountInr) : '';
  switch (s.attackType) {
    case 'executive_voice_clone':
      return [
        { at: 3, speaker: 'caller', text: `${first(receiver)}, ${first(claimed)} here. Quick one, it's urgent.`, flags: ["it's urgent"] },
        { at: 14, speaker: 'caller', text: `Please release ${amount} to ${request.counterparty} ${request.deadline}.`, flags: [`${request.deadline}`] },
        { at: 27, speaker: 'employee', text: 'Sir, I will need the approval on the payment request.' },
        { at: 33, speaker: 'caller', text: 'Approval baad mein ho jayega. Keep this between us for now.', flags: ['Approval baad mein', 'Keep this between us'] },
      ];
    case 'vendor_impersonation':
      return [
        { at: 4, speaker: 'caller', text: `Hi ${first(receiver)}, ${request.counterparty} has changed banks.` },
        { at: 15, speaker: 'caller', text: 'Update the account before the payment run, I will send the new details.', flags: ['Update the account before the payment run'] },
        { at: 29, speaker: 'employee', text: 'We normally call the vendor back to confirm.' },
        { at: 36, speaker: 'caller', text: 'No time for that today, just process it.', flags: ['No time for that today'] },
      ];
    case 'it_helpdesk_impersonation':
      return [
        { at: 3, speaker: 'caller', text: `${first(receiver)}, this is ${first(claimed)} from IT. Your account is flagged.` },
        { at: 12, speaker: 'caller', text: 'Read me the code on your phone or it will be locked in five minutes.', flags: ['Read me the code', 'locked in five minutes'] },
        { at: 25, speaker: 'employee', text: 'Can I raise a ticket instead?' },
      ];
    case 'payroll_change':
      return [
        { at: 5, speaker: 'caller', text: `${first(receiver)}, ${first(claimed)} here. Two salary accounts need changing today.` },
        { at: 17, speaker: 'caller', text: 'Do it directly, not through the HR system. Keep it confidential.', flags: ['not through the HR system', 'Keep it confidential'] },
      ];
  }
}

const readingFor = (id: SignalId, risk: number, claimed: Person): string => {
  const high = risk >= 70;
  switch (id) {
    case 'audioQuality':
      return risk > 50 ? 'Poor. Heavy compression limits some checks.' : 'Fair. Usable for all checks.';
    case 'voiceMatch':
      return high
        ? `Similarity ${(1 - risk / 100).toFixed(2)} against ${claimed.name}'s trusted voice profile.`
        : `Partial match with ${claimed.name}'s trusted voice profile.`;
    case 'syntheticSpeech':
      return high ? 'Strong indicators of generated speech.' : 'Some indicators of generated speech.';
    case 'prosody':
      return high ? 'Pitch and rhythm differ from reference calls.' : 'Minor rhythm differences from reference calls.';
    case 'codecArtifacts':
      return high ? 'Re-encoding traces inconsistent with caller ID.' : 'Audio routed through a VoIP gateway.';
    case 'backgroundNoise':
      return high ? 'Background audio loops with no variation.' : 'Background noise mostly consistent.';
    case 'watermark':
      return 'No known watermark found. Absence does not indicate a genuine voice.';
    case 'contextIntent':
      return high ? 'Sensitive request with urgency and a process bypass.' : 'Sensitive request with mild pressure.';
  }
};

function signalsFor(target: number, genuine: boolean, claimed: Person): DetectionSignal[] {
  const offsets: Record<SignalId, number> = {
    audioQuality: -30,
    voiceMatch: genuine ? -30 : 2,
    syntheticSpeech: genuine ? -35 : 6,
    prosody: -6,
    codecArtifacts: -10,
    backgroundNoise: -14,
    watermark: 0,
    contextIntent: 12,
  };
  let list = referenceSignals.map((ref) => {
    const risk = ref.id === 'watermark' ? 50 : clamp(target + offsets[ref.id] + (rng.next() - 0.5) * 12);
    return { ...ref, risk };
  });
  // Nudge scored signals so the weighted score lands near the target band.
  const delta = target - weightedRiskScore(list);
  list = list.map((s) => (s.weight > 0 && s.id !== 'watermark' ? { ...s, risk: clamp(s.risk + delta) } : s));
  return list.map((s) => ({ ...s, reading: readingFor(s.id, s.risk, claimed) }));
}

function regionsFor(transcript: TranscriptLine[], signals: DetectionSignal[]): AudioRegion[] {
  const bySignal = Object.fromEntries(signals.map((s) => [s.id, s]));
  const callerLines = transcript.filter((l) => l.speaker === 'caller');
  const regions: AudioRegion[] = [];
  callerLines.forEach((line, index) => {
    const end = line.at + 9;
    if (index === 0) {
      regions.push({ start: line.at, end, signal: 'voiceMatch', label: 'Voice compared with trusted profile', level: riskLevelFor(bySignal.voiceMatch.risk) });
    }
    if (index === 1) {
      regions.push({ start: line.at, end, signal: 'syntheticSpeech', label: 'Generated speech indicators', level: riskLevelFor(bySignal.syntheticSpeech.risk) });
    }
    if (line.flags?.length) {
      regions.push({ start: line.at, end: end + 2, signal: 'contextIntent', label: 'Risky request language', level: riskLevelFor(bySignal.contextIntent.risk) });
    }
  });
  return regions;
}

function timelineFor(startMs: number, outcome: CallOutcome, receiver: Person, claimed: Person, id: string, score: number, assignee?: string, status?: IncidentStatus): TimelineEvent[] {
  const t = (sec: number) => iso(startMs + sec * 1000);
  const events: TimelineEvent[] = [
    { at: t(0), actor: 'system', label: `Call reached ${receiver.name}; caller ID showed ${claimed.name}`, tone: 'info' },
    { at: t(22), actor: 'system', label: `Risk alert shown to employee (score ${score})`, tone: riskLevelFor(score) },
  ];
  if (outcome === 'impersonation_confirmed') {
    events.push({ at: t(60), actor: 'claimed_person', label: `${claimed.name} denied the request on registered device`, tone: 'high' });
    events.push({ at: t(62), actor: 'system', label: 'Request blocked and call ended', tone: 'safe' });
  } else if (outcome === 'request_confirmed') {
    events.push({ at: t(60), actor: 'claimed_person', label: `${claimed.name} confirmed the request`, tone: 'safe' });
  } else if (outcome === 'escalated') {
    events.push({ at: t(48), actor: 'employee', label: `${receiver.name} notified the Security team`, tone: 'medium' });
  } else {
    events.push({ at: t(40), actor: 'employee', label: `${receiver.name} ended the call without verifying`, tone: 'medium' });
  }
  events.push({ at: t(64), actor: 'system', label: `Incident #${id} created`, tone: 'info' });
  if (assignee) events.push({ at: t(900), actor: 'security', label: `Assigned to ${assignee}` });
  if (status === 'closed') events.push({ at: t(6 * 3600), actor: 'security', label: 'Incident closed after review', tone: 'safe' });
  return events;
}

function reasonsFor(s: Scenario, claimed: Person, genuine: boolean): string[] {
  const voice = genuine
    ? 'Audio quality made the voice harder to match.'
    : `The voice doesn't closely match ${claimed.name}'s verified voice.`;
  const request: Record<AttackType, string> = {
    executive_voice_clone: 'Urgent payment to a vendor that is not on the approved list.',
    vendor_impersonation: 'Bank details change requested just before a payment run.',
    it_helpdesk_impersonation: 'You were asked to share a login code.',
    payroll_change: 'Salary account change requested outside the HR system.',
  };
  return [voice, request[s.attackType]];
}

function buildHistory(): Incident[] {
  const drafts: { startMs: number; scenario: Scenario }[] = [];
  for (let d = 0; d < DAYS; d++) {
    const dayMs = FIRST_DAY + d * DAY_MS;
    const weekday = new Date(dayMs).getUTCDay();
    const weekend = weekday === 0 || weekday === 6;
    const count = weekend ? rng.weighted([[0, 8], [1, 1]] as const) : rng.weighted([[0, 3], [1, 4], [2, 2]] as const);
    for (let c = 0; c < count; c++) {
      // 09:30 to 18:30 IST, stored as UTC
      const minuteOfDay = rng.int(9 * 60 + 30, 18 * 60 + 30) - 330;
      drafts.push({ startMs: dayMs + minuteOfDay * 60_000, scenario: rng.weighted(scenarios.map((s) => [s, s.weight] as const)) });
    }
  }
  drafts.sort((a, b) => a.startMs - b.startMs);

  const lastId = 78420;
  const demoMs = new Date('2026-09-11T14:30:00+05:30').getTime();

  return drafts.map(({ startMs, scenario }, index) => {
    const id = String(lastId - (drafts.length - 1 - index));
    const ageDays = (demoMs - startMs) / DAY_MS;
    const isHigh = rng.next() < 0.68;
    const outcome: CallOutcome = isHigh
      ? rng.weighted([['impersonation_confirmed', 70], ['ended_unverified', 18], ['request_confirmed', 12]] as const)
      : rng.weighted([['escalated', 55], ['request_confirmed', 45]] as const);
    const genuine = outcome === 'request_confirmed';
    const claimed = rng.pick(scenario.claimed);
    const receiver = rng.pick(scenario.receivers.filter((p) => p.id !== claimed.id));
    const target = isHigh ? rng.int(71, 92) : rng.int(46, 67);
    const signals = signalsFor(target, genuine, claimed);
    const riskScore = weightedRiskScore(signals);
    const createdAt = iso(startMs + 64_000);
    const request = requestFor(scenario, iso(startMs + 14_000));
    const transcript = transcriptFor(scenario, claimed, receiver, request);

    let status: IncidentStatus;
    if (genuine || ageDays > 6) status = 'closed';
    else if (outcome === 'impersonation_confirmed') status = ageDays > 2 ? 'closed' : 'contained';
    else status = ageDays < 1.2 ? 'new' : 'investigating';
    const assignee = status === 'new' ? undefined : rng.pick(Object.values(analysts));
    const durationSec = rng.int(48, 170);
    const network = rng.weighted([['VoIP', 62], ['Mobile', 38]] as const);

    return {
      id,
      createdAt,
      status,
      outcome,
      riskScore,
      riskLevel: riskLevelFor(riskScore),
      claimedIdentity: claimed,
      receiver,
      callerNumber: rng.next() < 0.6 && claimed.mobile ? claimed.mobile : `+91 ${rng.int(70000, 99999)} ${rng.int(10000, 99999)}`,
      request,
      metadata: {
        direction: 'external',
        network,
        callerIdNote: network === 'VoIP' ? 'Audio arrived via a VoIP gateway' : 'Carrier mobile call',
        language: rng.weighted(languages),
        audioQuality: rng.weighted([['Good', 30], ['Fair', 55], ['Poor', 15]] as const),
        backgroundNoise: rng.pick(['Low', 'Moderate, office', 'Low, repeating pattern', 'Street traffic']),
        codec: network === 'VoIP' ? rng.pick(['AMR-NB (transcoded)', 'G.711 (transcoded)']) : rng.pick(['AMR-WB', 'AMR-NB']),
        durationSec,
        analysedSec: durationSec - rng.int(2, 8),
        startedAt: iso(startMs),
      },
      signals,
      reasons: reasonsFor(scenario, claimed, genuine),
      transcript,
      verification:
        outcome === 'impersonation_confirmed'
          ? { method: 'claimed_person_device', result: 'denied', summary: `Denied by ${claimed.name} on registered device`, at: iso(startMs + 60_000) }
          : outcome === 'request_confirmed'
            ? { method: 'claimed_person_device', result: 'confirmed', summary: `Confirmed by ${claimed.name} on registered device`, at: iso(startMs + 60_000) }
            : outcome === 'escalated'
              ? { method: 'security_team', result: 'pending', summary: 'Escalated to Security before verification', at: iso(startMs + 48_000) }
              : { method: 'none', result: 'not_attempted', summary: 'Call ended before verification' },
      timeline: timelineFor(startMs, outcome, receiver, claimed, id, riskScore, assignee, status),
      voiceProfileUpdate: genuine && riskScore < 40 ? 'eligible' : 'excluded',
      attackType: scenario.attackType,
      office: receiver.location as Incident['office'],
      audioRegions: regionsFor(transcript, signals),
      assignee,
    } satisfies Incident;
  });
}

/** Oldest first; the live incident #78421 follows the last one. */
export const incidentHistory: Incident[] = buildHistory();
