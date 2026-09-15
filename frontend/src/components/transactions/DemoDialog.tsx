import {useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {FlaskConical, ArrowRight, CheckCircle2, Timer, Unplug} from 'lucide-react';
import {Dialog,DialogContent,DialogTitle,DialogDescription} from '../ui/dialog';
import {Button} from '../ui/button';
import {api,errorMessage} from '../../api/client';
import {toast} from 'sonner';
export const DemoDialog=({open,onOpenChange}:any)=>{
 const [scenario,setScenario]=useState('success'),[busy,setBusy]=useState(false);const navigate=useNavigate();
 const start=async()=>{setBusy(true);try{const {data}=await api.post('/demo/journeys',{scenario},{headers:{'Idempotency-Key':crypto.randomUUID()}});onOpenChange(false);navigate(`/operations/transactions/${data.transaction_id}`);toast.success('Demo journey created');}catch(e){toast.error(errorMessage(e));}finally{setBusy(false);}};
 return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent data-testid="demo-journey-dialog" className="product-dialog"><div className="dialog-icon"><FlaskConical size={24}/></div><DialogTitle data-testid="demo-dialog-title">Start a demo journey</DialogTitle><DialogDescription data-testid="demo-dialog-description">Skill development benefit · Aditi Patil · Synthetic data and consent</DialogDescription><div className="scenario-options">{[['success','Successful journey','All three departments complete the service.',CheckCircle2],['timeout_after_commit','Treasury timeout','Payment commits, but the response times out.',Timer],['treasury_unavailable','Treasury unavailable','A recoverable downstream service failure.',Unplug]].map(([id,title,desc,Icon]:any)=><button key={id} data-testid={`scenario-${id}`} className={scenario===id?'selected':''} onClick={()=>setScenario(id)}><Icon size={21}/><span><strong>{title}</strong><small>{desc}</small></span><span className="radio-indicator"/></button>)}</div><Button data-testid="start-demo-journey" disabled={busy} className="primary-button" onClick={start}>{busy?'Creating journey…':'Start journey'}<ArrowRight size={16}/></Button></DialogContent></Dialog>;
};