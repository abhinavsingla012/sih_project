import {useState} from 'react';
import {Link} from 'react-router-dom';
import {useQuery} from '@tanstack/react-query';
import {Inbox, ArrowUpRight, Clock3, CheckCircle2, XCircle} from 'lucide-react';
import {get} from '../api/client';
import {useAuth} from '../auth/AuthProvider';
import {PageHeader, Loading, ErrorState, Empty, DateText} from '../components/shared/Common';
import {StatusBadge} from '../components/shared/StatusBadge';
import {Application} from '../api/contracts';
const waiting = (iso:string) => {const m=Math.max(0,Math.round((Date.now()-new Date(iso).getTime())/60000));return m<1?'just now':m<60?`${m} min`:m<1440?`${Math.floor(m/60)} h`:`${Math.floor(m/1440)} d`;};
export default function ReviewsPage(){
  const {user}=useAuth(); const official=user.role==='official'; const [state,setState]=useState<'pending'|'decided'>('pending');
  const q=useQuery({queryKey:['reviews',state],queryFn:()=>get(`/reviews?state=${state}`),refetchInterval:4000});
  const items:Application[]=q.data?.items||[];
  return <><PageHeader eyebrow={official?`${(user.unit_name||'DEPARTMENT').toUpperCase()} · MAHARASHTRA`:'DEPARTMENT REVIEW'} title="Review inbox" description={official?`Cases awaiting your sanction, ${user.name.split(' ')[0]}. Eligibility has already been verified by the department system.`:'Applications waiting for a department officer’s sanction. Read-only view for operations and audit.'}/>
    <div className="review-tabs" role="tablist" data-testid="review-tabs">{(['pending','decided'] as const).map(s=><button key={s} role="tab" aria-selected={state===s} data-testid={`review-tab-${s}`} className={state===s?'active':''} onClick={()=>setState(s)}>{s==='pending'?<Clock3 size={14}/>:<CheckCircle2 size={14}/>}{s==='pending'?'Awaiting decision':'Decided'}{q.data&&state===s&&<span data-testid={`review-count-${s}`}>{q.data.total}</span>}</button>)}</div>
    {q.isLoading?<Loading/>:q.isError?<ErrorState retry={q.refetch} error={q.error}/>:!items.length?<Empty title={state==='pending'?'No cases waiting':'No decisions recorded yet'} description={state==='pending'?'New eligible applications appear here as soon as the eligibility check completes.':'Sanctioned and rejected cases will be listed here with the officer of record.'}/>:
    <div className="application-table review-table" data-testid="review-table"><div className="table-heading"><span>APPLICATION / TRANSACTION</span><span>APPLICANT</span><span>{state==='pending'?'WAITING':'DECISION'}</span><span>STATUS</span><span>{state==='pending'?'ELIGIBLE SINCE':'DECIDED'}</span><span/></div>
      {items.map(app=>{const stage=app.stages.find(s=>s.id==='approval'); const r=stage?.review; return <Link key={app.id} data-testid={`review-row-${app.id}`} to={`/operations/transactions/${app.transaction_id}`} className="application-row"><div className="id-cell"><strong>{app.id}</strong><span className="mono">{app.transaction_id}</span></div><div className="name-cell"><span>{app.owner_name}</span><small data-testid={`review-scheme-${app.id}`}>{app.service_name} · {app.option_label} · {app.district}</small></div>
        {state==='pending'?<span className="review-waiting" data-testid={`review-waiting-${app.id}`}><Clock3 size={13}/>{r?waiting(r.requested_at):'—'}</span>:<span className={`review-decision ${r?.decision==='SANCTIONED'?'ok':'bad'}`} data-testid={`review-decision-${app.id}`}>{r?.decision==='SANCTIONED'?<CheckCircle2 size={13}/>:<XCircle size={13}/>}{r?.decision==='SANCTIONED'?'Sanctioned':'Rejected'}<small>{r?.officer_name}</small></span>}
        <StatusBadge id={`review-status-${app.id}`} status={app.status}/><span className="date-cell">{r?.decided_at?<DateText value={r.decided_at}/>:r?<DateText value={r.requested_at}/>:'—'}</span><ArrowUpRight className="row-arrow" size={17}/></Link>;})}
    </div>}
    <div className="review-footnote" data-testid="review-footnote"><Inbox size={14}/>{official?'Opening a case shows the department’s own evidence only. Sanction issues the order in your department system; the treasury is instructed by the fabric.':'Officers of the approving department decide cases from their own workspace; operators cannot sanction on their behalf.'}</div></>;
}
