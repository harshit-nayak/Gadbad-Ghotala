import { useMemo, useState } from 'react';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { EmptyState, SearchField, Segmented } from '../../components/ui/Controls';
import type { RiskLevel } from '../../domain/types';
import { useDemo } from '../../state/DemoProvider';
import { DocumentRow } from './DocumentRow';

export function DocumentHistory() {
  const { state } = useDemo();
  const [query, setQuery] = useState('');
  const [risk, setRisk] = useState<'all' | RiskLevel>('all');
  const list = useMemo(
    () =>
      state.documents.filter(
        (d) => (risk === 'all' || d.riskLevel === risk) && `${d.name} ${d.submittedBy}`.toLowerCase().includes(query.trim().toLowerCase()),
      ),
    [state.documents, query, risk],
  );

  return (
    <div className="page">
      <PageHeader title="All analyses" description="Documents, web pages and messages checked across the organisation." />
      <div className="toolbar">
        <SearchField label="Search analyses" value={query} onChange={setQuery} placeholder="Search name or person" />
        <Segmented<'all' | RiskLevel>
          label="Risk level"
          value={risk}
          onChange={setRisk}
          options={[
            { value: 'all', label: 'All' },
            { value: 'high', label: 'High' },
            { value: 'medium', label: 'Medium' },
            { value: 'low', label: 'Low' },
          ]}
        />
      </div>
      <Panel flush>
        {list.length ? (
          <ul className="doc-list">{list.map((d) => <DocumentRow key={d.id} doc={d} />)}</ul>
        ) : (
          <EmptyState icon="fileText" title="No analyses match" />
        )}
      </Panel>
    </div>
  );
}
