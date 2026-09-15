import '@/App.css';
import '@/government-theme.css';
import {BrowserRouter,Routes,Route,Navigate,Outlet} from 'react-router-dom';
import {AuthProvider,useAuth} from './auth/AuthProvider';
import {AppShell} from './components/layout/AppShell';
import {Loading} from './components/shared/Common';
import {Toaster} from './components/ui/sonner';
import LoginPage from './pages/LoginPage';
import OverviewPage from './pages/OverviewPage';
import ApplicationsPage from './pages/ApplicationsPage';
import NewApplicationPage from './pages/NewApplicationPage';
import TransactionPage from './pages/TransactionPage';
import ResourcesPage from './pages/ResourcesPage';
import AuditPage from './pages/AuditPage';
import NotificationsPage from './pages/NotificationsPage';
import ReviewsPage from './pages/ReviewsPage';
import {homePath} from './api/contracts';
function Guard({citizen}){const {user,loading}=useAuth();if(loading)return <Loading/>;if(!user)return <Navigate to="/login" replace/>;if(citizen!==undefined&&(user.role==='citizen')!==citizen)return <Navigate to={homePath(user)} replace/>;return <Outlet/>;}
function Home(){const {user,loading}=useAuth();return loading?<Loading/>:<Navigate to={homePath(user)} replace/>;}
export default function App(){return <BrowserRouter><AuthProvider><Routes><Route path="/login" element={<LoginPage/>}/><Route element={<Guard/>}><Route element={<AppShell/>}><Route element={<Guard citizen={false}/>}><Route path="/operations" element={<OverviewPage/>}/><Route path="/operations/transactions" element={<ApplicationsPage/>}/><Route path="/operations/transactions/:key" element={<TransactionPage/>}/><Route path="/operations/exceptions" element={<ApplicationsPage exceptions/>}/><Route path="/operations/reviews" element={<ReviewsPage/>}/>{['connectors','mappings','policy','health'].map(view=><Route key={view} path={`/operations/${view}`} element={<ResourcesPage view={view}/>}/>)}<Route path="/operations/audit" element={<AuditPage/>}/></Route><Route element={<Guard citizen/>}><Route path="/citizen" element={<ApplicationsPage/>}/><Route path="/citizen/new" element={<NewApplicationPage/>}/><Route path="/citizen/applications/:key" element={<TransactionPage/>}/><Route path="/citizen/notifications" element={<NotificationsPage/>}/></Route></Route></Route><Route path="*" element={<Home/>}/></Routes><Toaster position="bottom-right" richColors/></AuthProvider></BrowserRouter>}