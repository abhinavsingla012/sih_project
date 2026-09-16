import {useState} from 'react';
import {UserCheck, CheckCircle2, XCircle, Clock3} from 'lucide-react';
import {Application, Stage} from '../../api/contracts';
import {Button} from '../ui/button';
import {Textarea} from '../ui/textarea';
import {DateText} from '../shared/Common';
import {api, errorMessage} from '../../api/client';
import {toast} from 'sonner';
const waitingFor = (iso:string) => {const m=Math.max(0,Math.round((Date.now()-new Date(iso).getTime())/60000));return m<1?'less than a minute':m<60?`${m} min`:m<1440?`${Math.floor(m/60)} h ${m%60} min`:`${Math.floor(m/1440)} d`;};
export const ReviewPanel = ({app, stage, role, refresh}: {app:Application; stage:Stage; role:string; refresh:()=>void}) => {
  const [remarks,setRemarks]=useState(''),[busy,setBusy]=useState<string|null>(null);
  const review=stage.review; if(!review) return null;
  const decide=async(decision:'SANCTION'|'REJECT')=>{setBusy(decision);try{await api.post(`/reviews/${app.transaction_id}/decision`,{decision,remarks,version:app.version});toast.success(decision==='SANCTION'?'Benefit sanctioned · forwarded to the treasury':'Application rejected · citizen notified');setRemarks('');refresh();}catch(e){toast.error(errorMessage(e));refresh();}finally{setBusy(null);}};
  if(review.decision){
    const ok=review.decision==='SANCTIONED';
    return <div className={`review-outcome ${ok?'sanctioned':'rejected'}`} data-testid="review-outcome">{ok?<CheckCircle2 size={22}/>:<XCircle size={22}/>}<div><strong data-testid="review-outcome-title">{ok?'Sanctioned by the department':'Rejected by the department'}</strong><p data-testid="review-outcome-officer">{review.officer_name}{review.designation?` · ${review.designation}`:''}{review.decided_at&&<> · <DateText value={review.decided_at}/></>}</p>{review.remarks&&<blockquote data-testid="review-outcome-remarks">“{review.remarks}”</blockquote>}</div></div>;
  }
  if(stage.state!=='AWAITING_REVIEW') return null;
  if(role!=='official') return <div className="review-outcome pending" data-testid="review-pending"><Clock3 size={22}/><div><strong>{role==='citizen'?`Your application is with the ${app.department||'department'} department for a decision`:`Awaiting a ${app.department||'department'} officer’s decision`}</strong><p data-testid="review-waiting">Eligibility confirmed · waiting {waitingFor(review.requested_at)}{role==='citizen'?' · you will be notified once an officer decides.':` · it is in the ${app.department||'department'} review inbox; the workflow resumes automatically after sanction.`}</p></div></div>;
  return <section className="review-panel" data-testid="review-panel"><div className="review-panel-heading"><UserCheck size={22}/><div><strong data-testid="review-panel-title">Officer decision required</strong><p>Documents verified against issuer signatures and eligibility confirmed by the department system · waiting {waitingFor(review.requested_at)}. Record your decision; the sanction order is issued in the department system and the treasury is instructed automatically.</p></div></div><label htmlFor="review-remarks" data-testid="review-remarks-label">Officer remarks (recorded in the audit trail)</label><Textarea id="review-remarks" data-testid="review-remarks" placeholder="e.g. Eligibility and course enrolment verified; sanctioned under scheme guidelines." value={remarks} onChange={e=>setRemarks(e.target.value)} minLength={5} maxLength={500}/><div className="review-actions"><Button data-testid="review-sanction" className="primary-button" disabled={!!busy||remarks.trim().length<5} onClick={()=>decide('SANCTION')}><CheckCircle2 size={15}/>{busy==='SANCTION'?'Issuing sanction…':'Sanction benefit'}</Button><Button data-testid="review-reject" variant="outline" className="reject-button" disabled={!!busy||remarks.trim().length<5} onClick={()=>decide('REJECT')}><XCircle size={15}/>{busy==='REJECT'?'Recording…':'Reject application'}</Button><span className="subtle" data-testid="review-hint">Remarks of at least 5 characters are mandatory.</span></div></section>;
};
