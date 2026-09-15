import {CircleCheck, CircleDashed, Clock3, AlertCircle, ShieldX, LoaderCircle} from 'lucide-react';
export const label = (s:string) => (s || '').toLowerCase().replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
export const StatusBadge = ({status, id}:{status:string; id?:string}) => {
  const ok = ['COMPLETED','HEALTHY','ALLOW','ACTIVE','VERIFIED','ELIGIBLE'].includes(status);
  const warn = ['RECONCILING','RETRYING','RETRY_SCHEDULED','DEGRADED','HUMAN_INTERVENTION_REQUIRED'].includes(status);
  const bad = ['DENY','BLOCKED','FAILED','REJECTED','REVOKED','UNAVAILABLE'].includes(status);
  const Icon = ok?CircleCheck:warn?AlertCircle:bad?ShieldX:status==='PROCESSING'?LoaderCircle:status==='PENDING'?CircleDashed:Clock3;
  return <span data-testid={id || `status-${status.toLowerCase()}`} className={`status-badge ${ok?'success':warn?'warning':bad?'danger':'neutral'}`}><Icon size={12}/>{label(status)}</span>;
};