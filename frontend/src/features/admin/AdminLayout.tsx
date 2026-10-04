import { ORG_NAME } from '../../app/brand';
import { Workspace } from '../../components/layout/Workspace';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import './admin.css';

export function AdminLayout() {
  const currentUser = useCurrentUser();
  return (
    <Workspace
      area="admin"
      footer={
        <div className="org-card">
          <p className="org-card__name">{ORG_NAME}</p>
          <p className="org-card__meta">7 offices · 3,980 employees</p>
          <p className="org-card__meta">Signed in as {currentUser.name}</p>
        </div>
      }
    />
  );
}
