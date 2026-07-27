'use client';
import { useRouter, usePathname } from 'next/navigation';
import { useEffect } from 'react';
import { useAuth } from '@/lib/auth';

const ROLE_REDIRECTS: Record<string, string> = {
  admin: '/dashboard',
  supervisor: '/dashboard',
  technician: '/dashboard',
};

const PUBLIC_PATHS = ['/', '/login'];

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (loading) return;
    if (!user && !PUBLIC_PATHS.includes(pathname)) {
      router.push('/login');
    } else if (user && pathname === '/login') {
      router.push(ROLE_REDIRECTS[user.role] || '/dashboard');
    }
  }, [user, loading, pathname, router]);

  if (PUBLIC_PATHS.includes(pathname)) return <>{children}</>;
  if (loading || !user) return <div className="flex items-center justify-center h-screen text-muted">加载中...</div>;
  return <>{children}</>;
}
