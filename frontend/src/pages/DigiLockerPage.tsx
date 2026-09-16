import {useState} from 'react';
import {Navigate, useNavigate, useSearchParams} from 'react-router-dom';
import {useQuery} from '@tanstack/react-query';
import {LockKeyhole, ShieldCheck, CircleCheck, CircleAlert, CloudDownload, Building2} from 'lucide-react';
import {api, get, errorMessage} from '../api/client';
import {useAuth} from '../auth/AuthProvider';
import {Button} from '../components/ui/button';
import {toast} from 'sonner';
// Simulated third-party consent screen. Deliberately not styled like Sampark: this is "another site" the citizen is redirected to.
export default function DigiLockerPage() {
  const [params] = useSearchParams(); const navigate = useNavigate(); const {user} = useAuth();
  const scope = params.get('scope') || '', state = params.get('state') || ''; const redirect = params.get('redirect') || '/citizen';
  const target = redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/citizen';
  const [busy, setBusy] = useState<string | null>(null);
  const q = useQuery({queryKey: ['digilocker-authorize', scope, state], queryFn: () => get(`/mock/digilocker/oauth2/1/authorize?client_id=sampark&scope=${encodeURIComponent(scope)}&state=${encodeURIComponent(state)}`), enabled: !!scope && state.length >= 8, retry: false});
  if (!scope || state.length < 8) return <Navigate to="/citizen" replace/>;
  const back = (qs: string) => navigate(`${target}${target.includes('?') ? '&' : '?'}${qs}`);
  const decide = async (decision: 'allow' | 'deny') => {
    setBusy(decision);
    try {
      const {data} = await api.post('/mock/digilocker/oauth2/1/authorize/decision', {state, scope, decision});
      if (decision === 'deny' || data.error) {back(`error=access_denied&state=${encodeURIComponent(state)}`); return;}
      back(`code=${encodeURIComponent(data.code)}&state=${encodeURIComponent(state)}`);
    } catch (e) {toast.error(errorMessage(e)); setBusy(null);}
  };
  const issue = async (doctype: string, name: string, issuer: string) => {
    setBusy(doctype);
    try {await api.post('/mock/digilocker/issue', {doctype}); toast.success(`${name} issued by ${issuer} · now in your locker`); await q.refetch();}
    catch (e) {toast.error(errorMessage(e));} finally {setBusy(null);}
  };
  const d = q.data; const missing = d ? d.documents.filter((x: any) => !x.available).length : 0;
  return <div className="dl-page" data-testid="digilocker-page">
    <header className="dl-topbar"><span className="dl-logo"><LockKeyhole size={20}/>DigiLocker</span><span className="dl-tag" data-testid="digilocker-simulated-tag">SIMULATED</span><span className="dl-user" data-testid="digilocker-user">{user.name}</span></header>
    <div className="dl-warning" role="note" data-testid="digilocker-simulated-banner"><CircleAlert size={16}/><span>This is a <strong>simulated</strong> DigiLocker built for the Sampark prototype. It is not digilocker.gov.in and holds no real documents.</span></div>
    <main className="dl-main">
      {q.isLoading && <div className="dl-card dl-loading" data-testid="digilocker-loading">Opening your locker…</div>}
      {q.isError && <div className="dl-card" data-testid="digilocker-error"><h1>We could not open this request</h1><p className="dl-note">{errorMessage(q.error)}</p><div className="dl-actions"><Button variant="outline" data-testid="digilocker-return" onClick={() => back(`error=access_denied&state=${encodeURIComponent(state)}`)}>Return to Sampark</Button></div></div>}
      {d && <div className="dl-card" data-testid="digilocker-consent">
        <div className="dl-requester"><span className="dl-requester-mark"><Building2 size={22}/></span><div><span className="dl-eyebrow">ACCESS REQUEST</span><h1 data-testid="digilocker-requester">{d.requester.name}</h1><p data-testid="digilocker-purpose">{d.requester.purpose}</p></div></div>
        <p className="dl-holder" data-testid="digilocker-holder">Signed in as <strong>{d.holder.name}</strong> · mobile {d.holder.mobile}</p>
        <h2>Documents requested</h2>
        <ul className="dl-docs">{d.documents.map((doc: any) => <li key={doc.doctype} className={doc.available ? 'available' : 'missing'} data-testid={`digilocker-doc-${doc.doctype}`}>
          {doc.available ? <CircleCheck size={20}/> : <CircleAlert size={20}/>}
          <div><strong>{doc.name}</strong><span>{doc.issuer_name}</span>{doc.available ? <small data-testid={`digilocker-doc-issued-${doc.doctype}`}>Issued {doc.issued_on} · <code>{doc.uri}</code></small> : <small data-testid={`digilocker-doc-missing-${doc.doctype}`}>Not in your locker</small>}</div>
          {!doc.available && <Button variant="outline" className="dl-issue" data-testid={`digilocker-issue-${doc.doctype}`} disabled={!!busy} onClick={() => issue(doc.doctype, doc.name, doc.issuer_name)}><CloudDownload size={15}/>{busy === doc.doctype ? 'Requesting…' : `Get from ${doc.issuer_name.split(',')[0]} (simulated)`}</Button>}
        </li>)}</ul>
        {missing > 0 && <p className="dl-note warn" data-testid="digilocker-missing-note"><CircleAlert size={15}/><span>{missing} document{missing > 1 ? 's are' : ' is'} not in your locker. Fetch {missing > 1 ? 'them' : 'it'} from the issuing department above, or share only what is available — Sampark will pause your application until the rest arrives.</span></p>}
        <p className="dl-note"><ShieldCheck size={15}/><span>Sampark receives document references and verifies each issuer signature. Your documents stay in your locker, and you can withdraw this consent from Sampark at any time.</span></p>
        <div className="dl-actions"><Button variant="outline" data-testid="digilocker-deny" disabled={!!busy} onClick={() => decide('deny')}>Deny</Button><Button className="dl-allow" data-testid="digilocker-allow" disabled={!!busy} onClick={() => decide('allow')}>{busy === 'allow' ? 'Sharing…' : missing > 0 ? 'Share available documents' : 'Allow'}</Button></div>
      </div>}
      <p className="dl-footer" data-testid="digilocker-footer">Simulated DigiLocker · OAuth 2.0 authorization-code flow · Requester <code>sampark</code> · State <code>{state.slice(0, 8)}…</code></p>
    </main>
  </div>;
}
