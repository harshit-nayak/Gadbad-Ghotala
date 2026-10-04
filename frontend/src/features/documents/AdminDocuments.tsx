import { useState } from 'react';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { Button } from '../../components/ui/Button';
import { Pill } from '../../components/ui/Pill';
import { docsignApi, DocsignApiError } from '../../services/docsignApi';
import { useDocsignStatus } from './useDocuments';

import { useCurrentUser } from '../../hooks/useCurrentUser';

export function AdminDocuments() {
  const { status, loading, error: statusError, refresh } = useDocsignStatus();
  const currentUser = useCurrentUser();

  const [initBusy, setInitBusy] = useState(false);
  const [initError, setInitError] = useState<string | null>(null);

  const [name, setName] = useState(currentUser.name || '');
  const [email, setEmail] = useState(currentUser.email || '');
  const [empId, setEmpId] = useState(currentUser.id || '');
  const [enrolBusy, setEnrolBusy] = useState(false);
  const [enrolError, setEnrolError] = useState<string | null>(null);
  const [enrolMsg, setEnrolMsg] = useState<string | null>(null);

  const initCa = async () => {
    setInitBusy(true);
    setInitError(null);
    try {
      await docsignApi.initCa();
      await refresh();
    } catch (e) {
      setInitError(e instanceof DocsignApiError ? e.message : 'Could not initialise the root CA.');
    } finally {
      setInitBusy(false);
    }
  };

  const enrol = async () => {
    if (!name.trim() || !email.trim() || !empId.trim()) {
      setEnrolError('All three fields are required.');
      return;
    }
    setEnrolBusy(true);
    setEnrolError(null);
    setEnrolMsg(null);
    try {
      const r = await docsignApi.enrol({ name: name.trim(), email: email.trim(), id: empId.trim() });
      setEnrolMsg(`Enrolled ${r.name} (${r.id}) — certificate valid until ${r.not_after}`);
      setName('');
      setEmail('');
      setEmpId('');
      await refresh();
    } catch (e) {
      setEnrolError(e instanceof DocsignApiError ? e.message : 'Enrolment failed.');
    } finally {
      setEnrolBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        title="Document signing administration"
        description="Manage the internal root of trust and enrol employees for document signing."
      />

      <Panel title="Root certificate authority">
        {loading ? (
          <p className="subtle">Loading…</p>
        ) : status?.ca ? (
          <>
            <dl className="meta-list">
              <div>
                <dt>Subject</dt>
                <dd>
                  <code className="code">{status.ca.subject}</code>
                </dd>
              </div>
              <div>
                <dt>Valid</dt>
                <dd>
                  {status.ca.not_before} → {status.ca.not_after}
                </dd>
              </div>
            </dl>
            <p className="subtle">Distribute root_ca.pem to every verifier through a trusted channel.</p>
            <a className="btn btn--secondary btn--md" href={docsignApi.rootCaUrl} download>
              Download root_ca.pem
            </a>
          </>
        ) : (
          <>
            <p className="subtle">No root CA on this machine yet.</p>
            <Button variant="primary" onClick={initCa} loading={initBusy}>
              Initialise Root CA
            </Button>
          </>
        )}
        {initError && <p className="form-error">{initError}</p>}
        {statusError && <p className="form-error">{statusError}</p>}
      </Panel>

      <Panel title="Enrol an employee">
        <p className="subtle">
          In a real deployment this must be gated behind verified identity — a certificate issued to the wrong person verifies perfectly.
        </p>
        <div className="doc-form">
          <label className="doc-form__label">Full name</label>
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Priya Sharma" />
          <label className="doc-form__label">Email</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="priya.sharma@company.internal" />
          <label className="doc-form__label">Employee ID</label>
          <input type="text" value={empId} onChange={(e) => setEmpId(e.target.value)} placeholder="EMP10452" />
          <Button variant="primary" onClick={enrol} loading={enrolBusy}>
            Enrol
          </Button>
        </div>
        {enrolError && <p className="form-error">{enrolError}</p>}
        {enrolMsg && <p className="verdict verdict--safe verdict--inline">{enrolMsg}</p>}
      </Panel>

      <Panel flush title="Enrolled on this machine">
        {!status?.enrolled?.length ? (
          <p className="subtle" style={{ padding: 'var(--space-5)' }}>
            Nobody enrolled yet.
          </p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Expires</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {status.enrolled.map((e) => (
                  <tr key={e.id}>
                    <td>
                      <code className="code">{e.id}</code>
                    </td>
                    <td>{e.name}</td>
                    <td>{e.email}</td>
                    <td>{(e.not_after || '').slice(0, 10)}</td>
                    <td>
                      <Pill tone={e.expired ? 'risk' : 'safe'} dot>
                        {e.expired ? 'expired' : 'valid'}
                      </Pill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
