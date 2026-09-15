import React, {createContext, useContext, useState, useEffect, useRef} from 'react';
import {toast} from 'sonner';
import {api} from '../api/client';
import {User} from '../api/contracts';
import {useQueryClient} from '@tanstack/react-query';
const AuthContext = createContext<any>(null);
export function AuthProvider({children}: {children:React.ReactNode}) {
  const [user, setUser] = useState<User|null>(null), [loading,setLoading] = useState(true);
  const queries = useQueryClient();
  const userRef = useRef<User|null>(null); userRef.current = user;
  useEffect(() => {api.get('/auth/me').then(r=>setUser(r.data)).catch(()=>setUser(null)).finally(()=>setLoading(false));},[]);
  useEffect(() => {
    // A 401 on any authenticated call means the session expired or was revoked: return to sign-in instead of showing a stale workspace.
    const id = api.interceptors.response.use(r => r, error => {
      const url: string = error?.config?.url || '';
      if (error?.response?.status === 401 && !url.includes('/auth/login')) {
        if (userRef.current) toast.error('Your session has expired. Please sign in again.', {id: 'session-expired'});
        queries.clear(); setUser(null);
      }
      return Promise.reject(error);
    });
    return () => api.interceptors.response.eject(id);
  }, [queries]);
  const login = async (email:string,password:string) => {
    const {data} = await api.post('/auth/login',{email,password});
    // Confirm the browser actually kept the session cookie (embedded frames with third-party cookies blocked silently drop it).
    try { await api.get('/auth/me'); }
    catch (e:any) { if (e?.response?.status === 401) throw Object.assign(new Error('COOKIE_BLOCKED'), {code:'COOKIE_BLOCKED', userMessage:'Your browser did not keep the sign-in cookie in this embedded view. Open the app in a new tab and sign in there.'}); }
    queries.clear(); setUser(data); return data;
  };
  const logout = async () => {try {await api.post('/auth/logout');} finally {queries.clear(); setUser(null);}};
  return <AuthContext.Provider value={{user, loading, login, logout}}>{children}</AuthContext.Provider>;
}
export const useAuth = () => useContext(AuthContext);
