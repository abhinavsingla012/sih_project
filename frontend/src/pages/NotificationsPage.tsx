import {Link} from 'react-router-dom';
import {useQuery} from '@tanstack/react-query';
import {Bell,Check,ArrowUpRight} from 'lucide-react';
import {get,api,errorMessage} from '../api/client';
import {Button} from '../components/ui/button';
import {PageHeader,Loading,ErrorState,Empty,DateText} from '../components/shared/Common';
import {label} from '../components/shared/StatusBadge';
import {toast} from 'sonner';
export default function NotificationsPage(){
 const q=useQuery({queryKey:['notifications'],queryFn:()=>get('/notifications'),refetchInterval:5000});
 const mark=async(id:string)=>{try{await api.patch(`/notifications/${id}`);q.refetch()}catch(e){toast.error(errorMessage(e))}};
 return <><PageHeader eyebrow="CITIZEN PORTAL" title="Notifications" description="Updates from your service journeys."/>{q.isLoading?<Loading/>:q.isError?<ErrorState retry={q.refetch}/>:!q.data.items.length?<Empty title="You’re all caught up" description="New service updates will appear here."/>:<div className="notification-list">{q.data.items.map((n:any)=><div key={n.id} data-testid={`notification-${n.id}`} className={`notification-row ${n.read?'read':''}`}><Bell size={20}/><div><strong>{label(n.type)}</strong><span><DateText value={n.timestamp}/></span><Link className="text-link" data-testid={`notification-link-${n.id}`} to={`/citizen/applications/${n.application_id}`}>{n.application_id}<ArrowUpRight size={13}/></Link></div>{!n.read?<Button data-testid={`notification-read-${n.id}`} variant="ghost" title="Mark read" aria-label="Mark read" onClick={()=>mark(n.id)}><Check size={17}/></Button>:<span className="subtle" data-testid={`notification-read-state-${n.id}`}>Read</span>}</div>)}</div>}</>;
}