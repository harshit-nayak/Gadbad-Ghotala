import { Link, useParams } from 'react-router-dom';
import { EmbeddingGrid } from '../../components/incident/EmbeddingGrid';
import { IncidentTable } from '../../components/incident/IncidentTable';
import { profileStatusLabel } from '../../components/incident/labels';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { Avatar } from '../../components/ui/Avatar';
import { EmptyState } from '../../components/ui/Controls';
import { Icon } from '../../components/ui/Icon';
import { Pill } from '../../components/ui/Pill';
import { embeddingCells, profileFor } from '../../data/voiceProfiles';
import { formatClock, formatDateTimeIst, formatDateYearIst } from '../../domain/format';
import { useDemo } from '../../state/DemoProvider';

function ReferenceWave({ seed }: { seed: string }) {
  const values = embeddingCells(`${seed}-wave`, 120);
  return (
    <svg className="reference-wave" viewBox="0 0 480 64" preserveAspectRatio="none" role="img" aria-label="Reference voice waveform">
      {values.map((v, i) => {
        const envelope = Math.sin((Math.PI * i) / values.length) ** 0.6 * (0.55 + 0.45 * Math.abs(Math.sin(i * 0.21)));
        const h = Math.max(2, v * envelope * 58);
        return <rect key={i} x={i * 4} y={32 - h / 2} width={2.6} height={h} rx={1.2} />;
      })}
    </svg>
  );
}

export function VoiceProfileDetail() {
  const { personId } = useParams();
  const { state } = useDemo();
  const profile = personId ? profileFor(personId) : undefined;

  if (!profile) {
    return (
      <div className="page">
        <Panel>
          <EmptyState icon="shield" title="Voice profile not found">
            <Link to="/security/profiles" className="text-link">Back to voice profiles</Link>
          </EmptyState>
        </Panel>
      </div>
    );
  }

  const { person } = profile;
  const status = profileStatusLabel[profile.status];
  const related = state.incidents.filter((i) => i.claimedIdentity.id === person.id);
  const latest = related[0];
  const latestVoice = latest?.signals.find((s) => s.id === 'voiceMatch');
  const similarity = latestVoice ? 1 - latestVoice.risk / 100 : null;
  const used = profile.verifiedCalls.filter((c) => c.usedForUpdate).length;

  return (
    <div className="page">
      <PageHeader
        eyebrow={
          <>
            <Link to="/security/profiles">Voice profiles</Link>
            <Icon name="chevronRight" size={14} />
            <span>{person.name}</span>
          </>
        }
        title={
          <span className="profile-title">
            <Avatar initials={person.initials} size="md" tone="lilac" />
            <span>
              {person.name}
              <span className="profile-title__sub">{person.role} · {person.department} · {person.location}</span>
            </span>
            <Pill tone={status.tone} dot>{status.text}</Pill>
          </span>
        }
      />

      <div className="grid grid--3">
        <Panel title="Reference voice" className="span-2">
          <ReferenceWave seed={person.id} />
          <dl className="profile-stats">
            <div><dt>Reference audio</dt><dd className="tabular">{formatClock(profile.referenceSeconds)}</dd></div>
            <div><dt>Enrolled</dt><dd className="tabular">{formatDateYearIst(profile.enrolledAt)}</dd></div>
            <div><dt>Last verified update</dt><dd className="tabular">{formatDateYearIst(profile.lastVerifiedUpdate)}</dd></div>
            <div><dt>Match threshold</dt><dd className="tabular">{profile.matchThreshold.toFixed(2)}</dd></div>
          </dl>
        </Panel>
        <Panel title="Update policy">
          <p className="policy-note">
            <Icon name="lock" size={16} />
            <span>Only verified genuine calls update this profile. Calls with risk signals, failed verification or poor audio are excluded.</span>
          </p>
          <dl className="policy-counts">
            <div><dt>Verified calls used</dt><dd className="tabular">{used}</dd></div>
            <div><dt>Verified calls excluded</dt><dd className="tabular">{profile.verifiedCalls.length - used}</dd></div>
            <div><dt>Flagged calls blocked</dt><dd className="tabular">{related.length}</dd></div>
          </dl>
        </Panel>
      </div>

      <Panel title="Voice embedding" subtitle="Visual projection of the stored embedding, compared with the latest call that claimed this identity">
        <div className="embedding-compare">
          <figure>
            <EmbeddingGrid values={embeddingCells(person.id)} label={`${person.name} trusted profile embedding`} />
            <figcaption>Trusted profile</figcaption>
          </figure>
          {latest && similarity !== null ? (
            <>
              <div className="embedding-compare__score">
                <p className="embedding-compare__value tabular">{similarity.toFixed(2)}</p>
                <p className="subtle">similarity</p>
                <p className={`embedding-compare__verdict ${similarity < profile.matchThreshold ? 'is-risk' : 'is-safe'}`}>
                  {similarity < profile.matchThreshold ? `Below ${profile.matchThreshold.toFixed(2)} threshold` : 'Above threshold'}
                </p>
              </div>
              <figure>
                <EmbeddingGrid values={embeddingCells(`call-${latest.id}`)} label={`Embedding from call in incident ${latest.id}`} tone="risk" />
                <figcaption>
                  Call in <Link to={`/security/incidents/${latest.id}`} className="fact-link tabular">#{latest.id}</Link>, {formatDateTimeIst(latest.createdAt)}
                </figcaption>
              </figure>
            </>
          ) : (
            <p className="subtle">No flagged calls have claimed this identity.</p>
          )}
        </div>
      </Panel>

      <Panel flush title="Verified call history" subtitle="Genuine calls checked against this profile">
        <div className="table-wrap">
          <table className="table">
            <caption className="visually-hidden">Verified call history</caption>
            <thead>
              <tr>
                <th scope="col">Date (IST)</th>
                <th scope="col">With</th>
                <th scope="col">Channel</th>
                <th scope="col" className="num">Duration</th>
                <th scope="col">Verification</th>
                <th scope="col">Profile update</th>
              </tr>
            </thead>
            <tbody>
              {profile.verifiedCalls.map((c) => (
                <tr key={c.at}>
                  <td className="tabular muted nowrap">{formatDateTimeIst(c.at)}</td>
                  <td>{c.counterpart}</td>
                  <td className="muted">{c.channel}</td>
                  <td className="num tabular">{formatClock(c.durationSec)}</td>
                  <td className="muted">{c.verification}</td>
                  <td>
                    <Pill tone={c.usedForUpdate ? 'safe' : 'neutral'}>{c.usedForUpdate ? 'Used' : 'Excluded'}</Pill>
                    <span className="cell-sub">{c.note.replace(/^(Used|Not used): /, '')}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel flush title="Related incidents" subtitle="Calls that claimed this identity. None of these can update the profile.">
        {related.length ? (
          <IncidentTable caption="Incidents claiming this identity" incidents={related} columns={['id', 'time', 'employee', 'request', 'risk', 'status']} />
        ) : (
          <EmptyState title="No incidents" />
        )}
      </Panel>
    </div>
  );
}
