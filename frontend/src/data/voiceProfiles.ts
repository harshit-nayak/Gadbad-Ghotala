/** Trusted voice profiles. Profiles only learn from verified genuine calls. */
import type { Person, VerifiedCall, VoiceProfile, VoiceProfileStatus } from '../domain/types';
import { people } from './people';
import { seeded } from './seed';

const rng = seeded(4040);
const ist = (date: string, time: string) => `${date}T${time}+05:30`;

const counterparts = [people.priyaMenon, people.anilKapoor, people.arjunMehta, people.meeraJoshi, people.nehaIyer, people.vikramRao];

function history(owner: Person, dates: string[]): VerifiedCall[] {
  return dates.map((date, i) => {
    const counterpart = rng.pick(counterparts.filter((p) => p.id !== owner.id)).name;
    const noisy = i === 2;
    return {
      at: ist(date, `${rng.int(10, 18)}:${String(rng.int(0, 59)).padStart(2, '0')}:00`),
      counterpart,
      durationSec: rng.int(90, 900),
      channel: rng.weighted([['Mobile', 3], ['VoIP', 2]] as const),
      verification: 'Verified on registered device',
      usedForUpdate: !noisy,
      note: noisy ? 'Not used: audio quality below enrolment standard' : 'Used: verified genuine, low risk',
    };
  });
}

const profile = (
  person: Person,
  status: VoiceProfileStatus,
  enrolledAt: string,
  dates: string[],
  referenceSeconds: number,
): VoiceProfile => {
  const verifiedCalls = history(person, dates);
  const used = verifiedCalls.filter((c) => c.usedForUpdate).map((c) => c.at).sort();
  return {
    person,
    status,
    enrolledAt,
    lastVerifiedUpdate: used[used.length - 1] ?? enrolledAt,
    referenceSeconds,
    verifiedCalls,
    matchThreshold: 0.72,
  };
};

export const voiceProfiles: VoiceProfile[] = [
  profile(people.rahulSharma, 'trusted', '2025-11-04T11:00:00+05:30', ['2026-09-08', '2026-09-03', '2026-08-29', '2026-08-21', '2026-08-12', '2026-07-30'], 412),
  profile(people.anilKapoor, 'trusted', '2025-11-06T12:00:00+05:30', ['2026-09-09', '2026-08-31', '2026-08-18', '2026-08-02'], 356),
  profile(people.deepakVerma, 'trusted', '2025-12-01T10:30:00+05:30', ['2026-09-02', '2026-08-20', '2026-07-28'], 298),
  profile(people.vikramRao, 'needs_review', '2026-01-15T15:00:00+05:30', ['2026-08-11', '2026-06-19'], 184),
  profile(people.nehaIyer, 'trusted', '2026-02-10T09:45:00+05:30', ['2026-09-05', '2026-08-26', '2026-08-07'], 240),
  profile(people.sanaQureshi, 'enrolling', '2026-08-28T16:10:00+05:30', ['2026-09-04'], 96),
];

export const profileFor = (personId: string) => voiceProfiles.find((p) => p.person.id === personId);

/**
 * Display-only projection of a profile's voice embedding into a small grid.
 * Real embeddings are high-dimensional; this just gives analysts a stable
 * visual fingerprint to compare.
 */
export function embeddingCells(seed: string, count = 48): number[] {
  let h = 0;
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const r = seeded(h);
  return Array.from({ length: count }, () => Math.round(r.next() * 100) / 100);
}
