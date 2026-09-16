import {CircleCheck, CircleDashed, Clock3, AlertCircle, ShieldX, LoaderCircle, UserCheck, FileWarning} from 'lucide-react';
const LABELS: Record<string,string> = {UNDER_REVIEW:'Under department review', AWAITING_REVIEW:'Awaiting officer decision', HUMAN_INTERVENTION_REQUIRED:'Needs investigation', RETRY_SCHEDULED:'Retry scheduled', RECONCILING:'Reconciling outcome', AWAITING_DOCUMENTS:'Documents required', DOCUMENTS_REQUIRED:'Documents required', DOCUMENTS_SHARED:'Documents shared from DigiLocker', DOCUMENTS_VERIFIED:'Documents verified', DOCUMENT_VERIFICATION:'Document verification', DOCUMENT_GRANT:'DigiLocker consent', DIGILOCKER:'DigiLocker (simulated)'};
export const label = (s:string) => LABELS[s] || (s || '').toLowerCase().replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
export const StatusBadge = ({status, id}:{status:string; id?:string}) => {
  const ok = ['COMPLETED','HEALTHY','ALLOW','ACTIVE','VERIFIED','ELIGIBLE','SANCTIONED'].includes(status);
  const warn = ['RECONCILING','RETRYING','RETRY_SCHEDULED','DEGRADED','HUMAN_INTERVENTION_REQUIRED'].includes(status);
  const bad = ['DENY','BLOCKED','FAILED','REJECTED','REVOKED','UNAVAILABLE'].includes(status);
  const review = ['UNDER_REVIEW','AWAITING_REVIEW'].includes(status);
  const hold = status==='AWAITING_DOCUMENTS';
  const Icon = ok?CircleCheck:warn?AlertCircle:bad?ShieldX:review?UserCheck:hold?FileWarning:status==='PROCESSING'?LoaderCircle:status==='PENDING'?CircleDashed:Clock3;
  return <span data-testid={id || `status-${status.toLowerCase()}`} className={`status-badge ${ok?'success':warn?'warning':bad?'danger':review?'review':hold?'hold':'neutral'}`}><Icon size={12}/>{label(status)}</span>;
};
