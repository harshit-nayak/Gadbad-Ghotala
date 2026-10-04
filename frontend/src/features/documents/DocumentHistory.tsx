import { useEffect, useMemo, useState } from 'react';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { EmptyState, SearchField } from '../../components/ui/Controls';
import { Icon } from '../../components/ui/Icon';
import { Pill } from '../../components/ui/Pill';
import { formatDateTimeIst } from '../../domain/format';
import { docsignApi, DocsignApiError, type SignatureHistoryEntry } from '../../services/docsignApi';

/** Real signing history from the docsign registry (docPipeline) — GET /api/history. */
export function DocumentHistory() {
  const [records, setRecords] = useState<SignatureHistoryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    docsignApi
      .history()
      .then((res) => setRecords(res.records))
      .catch((e) => setError(e instanceof DocsignApiError ? e.message : 'Could not reach the docsign service.'));
  }, []);

  const list = useMemo(() => {
    if (!records) return [];
    const q = query.trim().toLowerCase();
    if (!q) return records;
    return records.filter((r) => `${r.filename ?? ''} ${r.employee_name}`.toLowerCase().includes(q));
  }, [records, query]);

  return (
    <div className="page">
      <PageHeader title="Signing history" description="Every document signed through the docsign pipeline, newest first." />
      <div className="toolbar">
        <SearchField label="Search history" value={query} onChange={setQuery} placeholder="Search filename or signer" />
      </div>
      <Panel flush>
        {error ? (
          <EmptyState icon="shield" title="Could not load history">
            <p>{error}</p>
          </EmptyState>
        ) : !records ? (
          <p className="subtle" style={{ padding: 'var(--space-5)' }}>Loading…</p>
        ) : list.length ? (
          <ul className="doc-list">
            {list.map((r) => (
              <li key={r.id}>
                <span className="doc-row">
                  <span className="doc-row__icon doc-row__icon--low">
                    <Icon name="fileText" size={18} />
                  </span>
                  <span className="doc-row__main">
                    <span className="doc-row__name">{r.filename ?? 'Untitled document'}</span>
                    <span className="doc-row__meta">
                      <Icon name="userCheck" size={12} />
                      {r.employee_name} ({r.employee_id})
                    </span>
                  </span>
                  <Pill tone="safe" dot>Signed</Pill>
                  <span className="doc-row__time">{formatDateTimeIst(r.signed_at)}</span>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState icon="fileText" title="No signatures yet">
            <p>Sign a document to see it appear here.</p>
          </EmptyState>
        )}
      </Panel>
    </div>
  );
}
