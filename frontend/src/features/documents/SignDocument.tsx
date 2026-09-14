import { useState } from 'react';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { docsignApi, DocsignApiError, type SignResult } from '../../services/docsignApi';
import { useDocsignStatus } from './useDocuments';

export function SignDocument() {
  const { status, loading } = useDocsignStatus();
  const enrolled = status?.enrolled ?? [];
  const [employeeId, setEmployeeId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SignResult | null>(null);

  const who = employeeId || enrolled[0]?.id || '';

  const download = () => {
    if (!result) return;
    const blob = new Blob([result.bundle_text], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = result.sig_filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const runSign = async () => {
    if (!who) {
      setError('Pick a signer.');
      return;
    }
    if (!file) {
      setError('Choose a document.');
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await docsignApi.sign(who, file);
      setResult(r);
    } catch (e) {
      setError(e instanceof DocsignApiError ? e.message : 'Signing failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader title="Sign a document" description="Attach a detached, offline-verifiable signature using an enrolled identity's key." />

      <Panel title="Sign">
        {!loading && enrolled.length === 0 ? (
          <p className="subtle">No one is enrolled yet. Use the Admin tab first.</p>
        ) : (
          <div className="doc-form">
            <label className="doc-form__label">Sign as</label>
            <select value={who} onChange={(e) => setEmployeeId(e.target.value)}>
              {enrolled.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name} ({e.id})
                  {e.expired ? ' — expired' : ''}
                </option>
              ))}
            </select>
            <label className="doc-form__label">Document</label>
            <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <Button variant="primary" onClick={runSign} loading={busy}>
              Sign
            </Button>
          </div>
        )}

        {error && <p className="form-error">{error}</p>}

        {result && (
          <div className="verdict verdict--safe">
            <div className="verdict__head">
              <Icon name="check" size={18} />
              <h3>Signed</h3>
            </div>
            <p className="verdict__line">By {result.signer}</p>
            <p className="verdict__hash">
              <code>SHA-256 {result.digest}</code>
            </p>
            {result.registry ? (
              <p className={result.registry.ok ? 'subtle' : 'form-error'}>
                {result.registry.ok
                  ? `Registered in signature registry (record id ${result.registry.signature_id}) — DB-mode verify will find it.`
                  : `Not registered in the signature registry: ${result.registry.error} — the .sig file is unaffected.`}
              </p>
            ) : (
              <p className="subtle">No signature registry configured — .sig file only. DB-mode verify will not find this signature.</p>
            )}
            <Button variant="secondary" onClick={download} icon="download">
              Download {result.sig_filename}
            </Button>
          </div>
        )}
      </Panel>
    </div>
  );
}
