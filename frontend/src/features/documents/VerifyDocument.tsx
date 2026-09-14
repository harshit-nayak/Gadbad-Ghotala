import { useState } from 'react';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { Button } from '../../components/ui/Button';
import { docsignApi, DocsignApiError, type VerifyResult } from '../../services/docsignApi';
import { DocumentVerdict } from './DocumentVerdict';

export function VerifyDocument() {
  const [doc, setDoc] = useState<File | null>(null);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [showDegraded, setShowDegraded] = useState(false);
  const [degradedSig, setDegradedSig] = useState<File | null>(null);

  const [showOffline, setShowOffline] = useState(false);
  const [offlineDoc, setOfflineDoc] = useState<File | null>(null);
  const [offlineSig, setOfflineSig] = useState<File | null>(null);
  const [offlineResult, setOfflineResult] = useState<VerifyResult | null>(null);
  const [offlineError, setOfflineError] = useState<string | null>(null);
  const [offlineBusy, setOfflineBusy] = useState(false);

  const runVerify = async () => {
    if (!doc) {
      setError('Choose a document.');
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    setShowDegraded(false);
    try {
      const r = await docsignApi.verify(doc);
      setResult(r);
      if (r.status === 'VERIFICATION_UNAVAILABLE') setShowDegraded(true);
    } catch (e) {
      setError(e instanceof DocsignApiError ? e.message : 'Verification failed.');
    } finally {
      setBusy(false);
    }
  };

  const runDegraded = async () => {
    if (!doc) {
      setError('Choose a document.');
      return;
    }
    if (!degradedSig) {
      setError('Choose the .sig file.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await docsignApi.verifyOffline(doc, degradedSig);
      setResult(r);
    } catch (e) {
      setError(e instanceof DocsignApiError ? e.message : 'Verification failed.');
    } finally {
      setBusy(false);
    }
  };

  const runOffline = async () => {
    if (!offlineDoc) {
      setOfflineError('Choose a document.');
      return;
    }
    if (!offlineSig) {
      setOfflineError('Choose the .sig file.');
      return;
    }
    setOfflineBusy(true);
    setOfflineError(null);
    setOfflineResult(null);
    try {
      const r = await docsignApi.verifyOffline(offlineDoc, offlineSig);
      setOfflineResult(r);
    } catch (e) {
      setOfflineError(e instanceof DocsignApiError ? e.message : 'Verification failed.');
    } finally {
      setOfflineBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        title="Verify a document"
        description="Upload the document — its signature is looked up in the registry. No .sig file needed unless the registry is unavailable."
      />

      <Panel title="Verify">
        <div className="doc-form">
          <label className="doc-form__label">Document</label>
          <input
            type="file"
            onChange={(e) => {
              setDoc(e.target.files?.[0] ?? null);
              setResult(null);
              setError(null);
              setShowDegraded(false);
            }}
          />
          <Button variant="primary" onClick={runVerify} loading={busy}>
            Verify
          </Button>
        </div>

        {error && <p className="form-error">{error}</p>}
        {result && <DocumentVerdict result={result} />}

        {showDegraded && (
          <div className="doc-form doc-form--nested">
            <label className="doc-form__label">Signature file (.sig)</label>
            <input type="file" accept=".sig" onChange={(e) => setDegradedSig(e.target.files?.[0] ?? null)} />
            <Button variant="secondary" onClick={runDegraded} loading={busy}>
              Verify offline
            </Button>
          </div>
        )}

        <p className="subtle doc-form__toggle">
          <button type="button" className="inline-link" onClick={() => setShowOffline((v) => !v)}>
            Verify with a .sig file instead
          </button>
        </p>

        {showOffline && (
          <div className="doc-form doc-form--nested">
            <label className="doc-form__label">Document</label>
            <input type="file" onChange={(e) => setOfflineDoc(e.target.files?.[0] ?? null)} />
            <label className="doc-form__label">Signature file (.sig)</label>
            <input type="file" accept=".sig" onChange={(e) => setOfflineSig(e.target.files?.[0] ?? null)} />
            <Button variant="secondary" onClick={runOffline} loading={offlineBusy}>
              Verify offline
            </Button>
            {offlineError && <p className="form-error">{offlineError}</p>}
            {offlineResult && <DocumentVerdict result={offlineResult} />}
          </div>
        )}
      </Panel>
    </div>
  );
}
