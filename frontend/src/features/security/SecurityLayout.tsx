import { Workspace } from '../../components/layout/Workspace';
import { Avatar } from '../../components/ui/Avatar';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import './security.css';

export function SecurityLayout() {
  const currentUser = useCurrentUser();

  return (
    <Workspace
      area="security"
      footer={
        <div className="analyst-card">
          {currentUser.avatarUrl ? (
            <img
              src={currentUser.avatarUrl}
              alt=""
              referrerPolicy="no-referrer"
              style={{ width: 28, height: 28, borderRadius: '50%', objectFit: 'cover' }}
            />
          ) : (
            <Avatar initials={currentUser.initials} size="sm" tone="plum" />
          )}
          <div>
            <p className="analyst-card__name">{currentUser.name}</p>
            <p className="analyst-card__role">{currentUser.role}</p>
          </div>
        </div>
      }
    />
  );
}
