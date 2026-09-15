import { useRef, useState, type DragEvent } from 'react';
import { Link } from 'react-router-dom';
import { PageHeader, Panel } from '../../components/layout/Workspace';
import { Button } from '../../components/ui/Button';
import { Tabs } from '../../components/ui/Controls';
import { Icon } from '../../components/ui/Icon';
import { Pill } from '../../components/ui/Pill';
import { formatCount } from '../../domain/format';
import { readableAsText, sampleTextForFile, sampleTextForUrl } from '../../services/documentService';
import { useDemo } from '../../state/DemoProvider';
import { DocumentRow } from './DocumentRow';
import { useStartAnalysis } from './useDocuments';

type Mode = 'upload' | 'website' | 'paste';

const EXAMPLE = `From: Rahul Sharma <rahul.sharma@kaveri-holdings.co>
Priya, following our call please transfer ₹20,00,000 to Nexa Trade Solutions Pvt Ltd today.
Their bank details have changed, use account 50200081734409 (IFSC HDFC0004521).
This is confidential. Do not inform the finance committee until the deal is announced.`;

export function DocumentSecurity() {
  const { state } = useDemo();
  const start = useStartAnalysis();
  const [mode, setMode] = useState<Mode>('upload');
  const [dragging, setDragging] = useState(false);
  const [url, setUrl] = useState('');
  const [text, setText] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);

  const handleFile = (file: File) => {
    const meta = `${file.name.split('.').pop()?.toUpperCase() ?? 'File'}, ${Math.max(1, Math.round(file.size / 1024))} KB`;
    const submit = (content: string) => start({ name: file.name, source: 'upload', sourceDetail: 'Uploaded in GG', meta, text: content });
    if (readableAsText(file)) {
      const reader = new FileReader();
      reader.onload = () => submit(String(reader.result ?? ''));
      reader.onerror = () => submit(sampleTextForFile(file.name));
      reader.readAsText(file);
    } else {
      submit(sampleTextForFile(file.name));
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const cleanUrl = url.trim();
  const validUrl = /^(https?:\/\/)?([\w-]+\.)+[a-z]{2,}(\/\S*)?$/i.test(cleanUrl);

  return (
    <div className="page">
      <PageHeader
        title="Document security"
        description="Check documents, web pages and messages for impersonation, payment redirection and credential requests before anyone acts on them."
      />

      <div className="grid grid--main-side">
        <Panel title="Analyse content">
          <Tabs<Mode>
            label="Content source"
            active={mode}
            onChange={setMode}
            tabs={[
              { id: 'upload', label: 'Upload document' },
              { id: 'website', label: 'Website' },
              { id: 'paste', label: 'Paste content' },
            ]}
          />
          <div className="analyse-body" role="tabpanel" id={`panel-${mode}`} aria-labelledby={`tab-${mode}`}>
            {mode === 'upload' && (
              <div
                className={`dropzone ${dragging ? 'is-dragging' : ''}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
              >
                <span className="dropzone__icon"><Icon name="upload" size={22} /></span>
                <p className="dropzone__title">Drop a document here</p>
                <p className="dropzone__sub">PDF, Word, email (.eml) or text, up to 25 MB</p>
                <Button variant="primary" onClick={() => fileInput.current?.click()}>Choose file</Button>
                <p className="dropzone__sample">
                  No document to hand?{' '}
                  <button
                    type="button"
                    className="inline-link"
                    onClick={() => start({ name: 'Vendor_Bank_Change_Notice.pdf', source: 'upload', sourceDetail: 'Uploaded in GG', meta: 'PDF, 1 page, 92 KB', text: sampleTextForFile('Vendor_Bank_Change_Notice.pdf') })}
                  >
                    Analyse a sample vendor notice
                  </button>
                </p>
                <input
                  ref={fileInput}
                  type="file"
                  className="visually-hidden"
                  accept=".pdf,.doc,.docx,.txt,.eml,.md,.csv,.html"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFile(file);
                    e.target.value = '';
                  }}
                />
              </div>
            )}

            {mode === 'website' && (
              <form
                className="url-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (validUrl) start({ name: cleanUrl.replace(/^https?:\/\//, ''), source: 'website', sourceDetail: 'Website check', meta: 'Web page', text: sampleTextForUrl(cleanUrl) });
                }}
              >
                <label className="field field--url">
                  <Icon name="globe" size={16} />
                  <span className="visually-hidden">Website address</span>
                  <input type="text" inputMode="url" placeholder="https://vendor-portal.example/invoice" value={url} onChange={(e) => setUrl(e.target.value)} />
                </label>
                <Button variant="primary" type="submit" disabled={!validUrl}>Analyse page</Button>
                <p className="subtle url-form__hint">
                  Checks the page for payment instructions, look-alike domains and requests to act outside approved channels.{' '}
                  <button type="button" className="inline-link" onClick={() => setUrl('https://nexatrade-solutions.co/invoice/INV-2304')}>Try an example</button>
                </p>
              </form>
            )}

            {mode === 'paste' && (
              <div className="paste-form">
                <label className="visually-hidden" htmlFor="paste-content">Content to analyse</label>
                <textarea id="paste-content" className="textarea" rows={7} placeholder="Paste an email, chat message or document text" value={text} onChange={(e) => setText(e.target.value)} />
                <div className="paste-form__actions">
                  <button type="button" className="inline-link" onClick={() => setText(EXAMPLE)}>Use an example</button>
                  <Button variant="primary" disabled={text.trim().length < 20} onClick={() => start({ name: 'Pasted content', source: 'pasted', sourceDetail: 'Pasted in GG', meta: `${text.trim().split(/\s+/).length} words`, text })}>
                    Analyse content
                  </Button>
                </div>
              </div>
            )}
          </div>
        </Panel>

        <div className="stack">
          <Panel title="Browser extension" actions={<Pill tone="safe" dot="live">Active</Pill>}>
            <dl className="meta-list">
              <div><dt>Coverage</dt><dd><span className="tabular">{formatCount(3412)}</span> of <span className="tabular">{formatCount(3980)}</span> managed browsers</dd></div>
              <div><dt>Version</dt><dd>1.4.2, policy synced 14:20 IST</dd></div>
              <div><dt>Checks</dt><dd>Webmail attachments, invoice portals, payment pages</dd></div>
            </dl>
            <div className="coverage"><span style={{ width: `${(3412 / 3980) * 100}%` }} /></div>
          </Panel>
          <Panel title="API" actions={<Pill tone="safe" dot>Operational</Pill>}>
            <dl className="meta-list">
              <div><dt>Endpoint</dt><dd><code className="code">POST /v1/documents/analyse</code></dd></div>
              <div><dt>Key</dt><dd><code className="code">gg_live_••••7c2e</code></dd></div>
              <div><dt>Requests today</dt><dd className="tabular">{formatCount(1284)}</dd></div>
              <div><dt>Connected systems</dt><dd>Document management, accounts payable</dd></div>
            </dl>
          </Panel>
        </div>
      </div>

      <Panel
        flush
        title="Recent analyses"
        actions={<Link to="/documents/history" className="text-link">View all <Icon name="arrowRight" size={14} /></Link>}
      >
        <ul className="doc-list">
          {state.documents.slice(0, 5).map((doc) => (
            <DocumentRow key={doc.id} doc={doc} />
          ))}
        </ul>
      </Panel>
    </div>
  );
}
