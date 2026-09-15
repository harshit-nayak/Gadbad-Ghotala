import { ORG_NAME } from '../../app/brand';
import { Workspace } from '../../components/layout/Workspace';
import { currentAdmin } from '../../data/people';
import './admin.css';

export function AdminLayout() {
  const [name] = currentAdmin.split(', ');
  return (
    <Workspace
      area="admin"
      footer={
        <div className="org-card">
          <p className="org-card__name">{ORG_NAME}</p>
          <p className="org-card__meta">7 offices · 3,980 employees</p>
          <p className="org-card__meta">Signed in as {name}</p>
        </div>
      }
    />
  );
}
