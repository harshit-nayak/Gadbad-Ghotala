import { useNavigate } from 'react-router-dom';
import { profileStatusLabel } from '../../components/incident/labels';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { Avatar } from '../../components/ui/Avatar';
import { Pill } from '../../components/ui/Pill';
import { voiceProfiles } from '../../data/voiceProfiles';
import { formatClock, formatDateYearIst } from '../../domain/format';
import { useDemo } from '../../state/DemoProvider';

export function VoiceProfiles() {
  const { state } = useDemo();
  const navigate = useNavigate();

  return (
    <div className="page">
      <PageHeader
        title="Voice profiles"
        description="Trusted voice profiles for people most often impersonated. Profiles are built at enrolment and only updated from verified genuine calls."
      />
      <Panel flush>
        <div className="table-wrap">
          <table className="table">
            <caption className="visually-hidden">Voice profiles</caption>
            <thead>
              <tr>
                <th scope="col">Person</th>
                <th scope="col">Department</th>
                <th scope="col">Status</th>
                <th scope="col" className="num">Reference audio</th>
                <th scope="col">Last verified update</th>
                <th scope="col" className="num">Impersonation incidents</th>
              </tr>
            </thead>
            <tbody>
              {voiceProfiles.map((p) => {
                const incidents = state.incidents.filter((i) => i.claimedIdentity.id === p.person.id).length;
                const status = profileStatusLabel[p.status];
                return (
                  <tr key={p.person.id} className="table__row--link" onClick={() => navigate(`/security/profiles/${p.person.id}`)}>
                    <td>
                      <span className="person-cell">
                        <Avatar initials={p.person.initials} size="sm" tone="lilac" />
                        <span>
                          <span className="cell-strong">{p.person.name}</span>
                          <span className="cell-sub">{p.person.role}</span>
                        </span>
                      </span>
                    </td>
                    <td className="muted">{p.person.department}, {p.person.location}</td>
                    <td><Pill tone={status.tone}>{status.text}</Pill></td>
                    <td className="num tabular">{formatClock(p.referenceSeconds)}</td>
                    <td className="tabular muted">{formatDateYearIst(p.lastVerifiedUpdate)}</td>
                    <td className="num tabular td-strong">{incidents}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
