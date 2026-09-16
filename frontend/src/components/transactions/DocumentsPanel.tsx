import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {FolderLock, Eye, ShieldCheck, ShieldX, CircleAlert, BadgeCheck} from 'lucide-react';
import {Application, SharedDocument} from '../../api/contracts';
import {Button} from '../ui/button';
import {Dialog, DialogContent, DialogTitle, DialogDescription} from '../ui/dialog';
import {DateText} from '../shared/Common';
import {StatusBadge} from '../shared/StatusBadge';
import {useSchemes} from '../shared/Scheme';
import {get, errorMessage} from '../../api/client';
export const DocumentsPanel = ({app, role}: {app: Application; role: string}) => {
  const [preview, setPreview] = useState<SharedDocument | null>(null);
  const scheme = useSchemes().data?.find(s => s.code === app.service_code);
  const docs = app.documents; const stage = app.stages.find(s => s.id === 'documents');
  if (!docs && !stage?.hold) return null;
  const results: any[] = stage?.evidence?.source_summary?.documents || [];
  const missing: string[] = stage?.hold?.missing || [];
  const typeOf = (code: string) => scheme?.documents.find(d => d.code === code);
  const canPreview = ['official', 'operator', 'auditor'].includes(role);
  return <section className="documents-panel" data-testid="documents-panel">
    <div className="documents-panel-heading"><FolderLock size={22}/><div><strong data-testid="documents-panel-title">Documents shared from DigiLocker</strong><p data-testid="documents-panel-summary">{docs ? <>Consent given <DateText value={docs.connected_at}/> · {docs.shared.length} of {scheme?.documents.length || docs.shared.length} required documents shared · Sampark keeps references only, never the content.</> : 'No documents have been shared yet.'}</p></div>{stage && <StatusBadge status={stage.state} id="documents-stage-status"/>}</div>
    <div className="documents-list">
      {(docs?.shared || []).map(d => {const r = results.find(x => x.uri === d.uri); return <div key={d.uri} className="document-row" data-testid={`document-row-${d.doctype}`}>
        <div className="document-main"><strong>{d.name}</strong><span>{d.issuer_name} · issued {d.issued_on}</span><code>{d.uri}</code></div>
        <div className="document-checks">{r ? <><span className={`check ${r.signature === 'VALID' ? 'ok' : 'bad'}`} data-testid={`document-signature-${d.doctype}`}>{r.signature === 'VALID' ? <ShieldCheck size={14}/> : <ShieldX size={14}/>}Issuer signature {r.signature.toLowerCase()}</span><span className={`check ${r.holder_match === 'MATCH' ? 'ok' : 'bad'}`} data-testid={`document-holder-${d.doctype}`}>{r.holder_match === 'MATCH' ? <BadgeCheck size={14}/> : <CircleAlert size={14}/>}Holder {r.holder_match === 'MATCH' ? 'matches registry' : 'does not match'}</span></> : stage?.state === 'COMPLETED' ? <span className="check ok" data-testid={`document-verified-${d.doctype}`}><ShieldCheck size={14}/>Verified · issuer signature and holder checked</span> : <span className="check pending" data-testid={`document-pending-${d.doctype}`}>Awaiting verification</span>}</div>
        {canPreview && <Button variant="outline" data-testid={`document-preview-${d.doctype}`} onClick={() => setPreview(d)}><Eye size={15}/>Preview</Button>}
      </div>;})}
      {missing.map(code => <div key={code} className="document-row missing" data-testid={`document-missing-${code}`}><CircleAlert size={18}/><div className="document-main"><strong>{typeOf(code)?.name || code}</strong><span>Not shared yet · {typeOf(code)?.issuer_name || 'issuing department'}</span></div></div>)}
    </div>
    <Dialog open={!!preview} onOpenChange={v => !v && setPreview(null)}><DialogContent className="product-dialog document-dialog" data-testid="document-preview-dialog">{preview && <DocumentPreview doc={preview} applicationId={app.id}/>}</DialogContent></Dialog>
  </section>;
};
const DocumentPreview = ({doc, applicationId}: {doc: SharedDocument; applicationId: string}) => {
  const q = useQuery({queryKey: ["document", applicationId, doc.uri], queryFn: () => get(`/applications/${applicationId}/documents/${encodeURIComponent(doc.uri)}`), retry: false});
  if (q.isLoading) return <><DialogTitle>Opening document…</DialogTitle><DialogDescription>Fetching from the simulated DigiLocker with the citizen’s consent.</DialogDescription></>;
  if (q.isError) return <><DialogTitle data-testid="document-preview-error-title">Document unavailable</DialogTitle><DialogDescription data-testid="document-preview-error">{errorMessage(q.error)}</DialogDescription></>;
  const d = q.data.document; const ok = q.data.signature === 'VALID';
  return <><DialogTitle data-testid="document-preview-title">{d.name}</DialogTitle><DialogDescription data-testid="document-preview-note">{q.data.note}</DialogDescription>
    <article className={`doc-preview ${ok ? '' : 'invalid'}`} data-testid="document-preview">
      <header><span>{d.issuer_name}</span><span>{d.doctype}</span></header>
      <h3>{d.name}</h3>
      <dl>
        <div><dt>Holder</dt><dd data-testid="document-holder-name">{d.holder.name}</dd></div>
        <div><dt>Identifier</dt><dd className="mono" data-testid="document-holder-id">{d.holder.masked_id}</dd></div>
        <div><dt>Date of birth</dt><dd className="mono" data-testid="document-holder-dob">{d.holder.dob}</dd></div>
        <div><dt>Issued on</dt><dd>{d.issued_on}</dd></div>
        {Object.entries(d.fields).map(([k, v]: any) => <div key={k}><dt>{k.replaceAll('_', ' ')}</dt><dd data-testid={`document-field-${k}`}>{String(v)}</dd></div>)}
      </dl>
      <footer>
        <div className={`doc-seal ${ok ? '' : 'bad'}`} data-testid="document-seal">{ok ? <ShieldCheck size={22}/> : <ShieldX size={22}/>}<span>{ok ? 'DIGITALLY SIGNED' : 'SIGNATURE INVALID'}<small>{d.issuer_name.split(',')[0]}</small></span></div>
        <div className="doc-hash"><span>SHA-256 <code>{d.hash.slice(0, 20)}…</code></span><span>Signed {d.signed_at}</span></div>
      </footer>
    </article></>;
};
