import React, {createContext, useContext, useState, useEffect} from 'react';
import {api} from '../api/client';
import {User} from '../api/contracts';
import {useQueryClient} from '@tanstack/react-query';
const AuthContext = createContext<any>(null);
export function AuthProvider({children}: {children:React.ReactNode}) {
  const [user, setUser] = useState<User|null>(null), [loading,setLoading] = useState(true);
  const queries = useQueryClient();
  useEffect(() => {api.get('/auth/me').then(r=>setUser(r.data)).catch(()=>setUser(null)).finally(()=>setLoading(false));},[]);
  const login = async (email:string,password:string) => {const {data} = await api.post('/auth/login',{email,password}); queries.clear(); setUser(data); return data;};
  const logout = async () => {await api.post('/auth/logout'); queries.clear(); setUser(null);};
  return <AuthContext.Provider value={{user, loading, login, logout}}>{children}</AuthContext.Provider>;
}
export const useAuth = () => useContext(AuthContext);