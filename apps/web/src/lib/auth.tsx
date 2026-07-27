'use client';
import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { AuthState, User, Role } from './types';
import { login as apiLogin, getMe } from './api';

const AuthCtx = createContext<AuthState>({ token: null, user: null, role: null, login: async () => {}, logout: () => {}, loading: true });

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = localStorage.getItem('token');
    if (t) {
      setToken(t);
      getMe().then(u => { setUser(u); setLoading(false); }).catch(() => { localStorage.removeItem('token'); setLoading(false); });
    } else { setLoading(false); }
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await apiLogin(email, password);
    localStorage.setItem('token', res.access_token);
    setToken(res.access_token);
    setUser({ id: res.user_id, email, full_name: res.full_name, role: res.role as Role, is_active: true });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthCtx.Provider value={{ token, user, role: user?.role || null, login, logout, loading }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() { return useContext(AuthCtx); }
