'use client';
import { ReactNode } from 'react';
import { AuthProvider } from '@/lib/auth';
import AuthGuard from '@/lib/guards';
import { Toaster } from 'react-hot-toast';
import AppLayout from './app-layout';

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <AuthGuard>
        <AppLayout>{children}</AppLayout>
      </AuthGuard>
      <Toaster position="top-right" toastOptions={{
        style: { background: '#1e293b', color: '#f8fafc', border: '1px solid #334155' }
      }} />
    </AuthProvider>
  );
}
