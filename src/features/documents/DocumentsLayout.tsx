import { Workspace } from '../../components/layout/Workspace';
import './documents.css';

export function DocumentsLayout() {
  return (
    <Workspace
      area="documents"
      footer={
        <ul className="channel-health">
          <li><span className="health-dot health-dot--ok" />Browser extension active</li>
          <li><span className="health-dot health-dot--ok" />API operational</li>
        </ul>
      }
    />
  );
}
