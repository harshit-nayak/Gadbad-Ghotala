import { Workspace } from '../../components/layout/Workspace';
import { Avatar } from '../../components/ui/Avatar';
import { currentAnalyst } from '../../data/people';
import './security.css';

export function SecurityLayout() {
  const [name, role] = currentAnalyst.split(', ');
  return (
    <Workspace
      area="security"
      footer={
        <div className="analyst-card">
          <Avatar initials={name.split(' ').map((p) => p[0]).join('')} size="sm" tone="charcoal" />
          <div>
            <p className="analyst-card__name">{name}</p>
            <p className="analyst-card__role">{role}</p>
          </div>
        </div>
      }
    />
  );
}
