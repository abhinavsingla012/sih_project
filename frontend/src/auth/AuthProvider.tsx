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
  const login = async (email:string,password:string) => {const {data} = await api.post('/auth/login',{email,password}); queries.clear(); setUser(data); return data;};
  const logout = async () => {try {await api.post('/auth/logout');} finally {queries.clear(); setUser(null);}};
  return <AuthContext.Provider value={{user, loading, login, logout}}>{children}</AuthContext.Provider>;
}
export const useAuth = () => useContext(AuthContext);
