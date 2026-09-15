import {RefreshCw, ArrowUpRight, Inbox, Network} from 'lucide-react';
import {Button} from '../ui/button';
export const Brand = () => <div className="brand" data-testid="brand"><span className="brand-mark"><Network size={24}/></span><span>Samanvay<span className="brand-caption" lang="mr">समन्वय · महाराष्ट्र</span></span></div>;
export const PageHeader = ({eyebrow,title,description,action}:any) => <div className="page-heading"><div><div className="eyebrow" data-testid="page-eyebrow">{eyebrow}</div><h1 data-testid="page-title">{title}</h1>{description&&<p data-testid="page-description">{description}</p>}</div>{action}</div>;
export const Loading = () => <div className="loading-state" data-testid="loading-state"><RefreshCw className="spin" size={20}/> Loading workspace…</div>;
export const ErrorState = ({retry}:any) => <div className="empty-state" data-testid="error-state"><Inbox size={28}/><h2>We couldn’t load this view</h2><p>The service may be temporarily unavailable.</p><Button data-testid="retry-loading" variant="outline" onClick={retry}><RefreshCw size={15}/>Try again</Button></div>;
export const Empty = ({title,description,action}:any) => <div className="empty-state" data-testid="empty-state"><Inbox size={30}/><h2>{title}</h2><p>{description}</p>{action}</div>;
export const DateText = ({value}:any) => <>{new Date(value).toLocaleString('en-IN',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}</>;
export const Arrow = () => <ArrowUpRight size={16}/>;