import { Workspace } from '../../components/layout/Workspace';
import { useDocsignStatus } from './useDocuments';
import './documents.css';

export function DocumentsLayout() {
  const { status, error, loading } = useDocsignStatus();
  const reachable = !loading && !error;

  return (
    <Workspace
      area="documents"
      footer={
        <ul className="channel-health">
          <li>
            <span className={`health-dot ${reachable ? 'health-dot--ok' : 'health-dot--bad'}`} />
            docsign API {loading ? 'checking…' : reachable ? 'reachable' : 'unreachable'}
          </li>
          <li>
            <span className={`health-dot ${status?.ca ? 'health-dot--ok' : 'health-dot--bad'}`} />
            Root CA {status?.ca ? 'initialised' : 'not initialised'}
          </li>
        </ul>
      }
    />
  );
}
