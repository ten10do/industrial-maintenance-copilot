'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { Wrench } from 'lucide-react';

export default function LoginPage() {
  const [email, setEmail] = useState('admin@example.com');
  const [password, setPassword] = useState('Demo123456');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
      router.push('/dashboard');
    } catch (err: any) {
      setError(err.message || '登录失败');
    } finally {
      setLoading(false);
    }
  };

  const quickLogin = async (e: string) => {
    setEmail(e);
    setPassword('Demo123456');
    setError('');
    setLoading(true);
    try {
      await login(e, 'Demo123456');
      router.push('/dashboard');
    } catch (err: any) {
      setError(err.message || '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary/20 mb-4">
            <Wrench size={32} className="text-primary-400" />
          </div>
          <h1 className="text-2xl font-bold">设备运维工单 Copilot</h1>
          <p className="text-sm text-muted mt-2">工业设备智能维修管理系统</p>
        </div>
        <form onSubmit={handleSubmit} className="card space-y-4">
          <div>
            <label className="block text-sm mb-1">邮箱</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} required className="w-full" placeholder="请输入邮箱" />
          </div>
          <div>
            <label className="block text-sm mb-1">密码</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} required className="w-full" placeholder="请输入密码" />
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button type="submit" disabled={loading} className="btn btn-primary btn-block btn-lg">
            {loading ? '登录中...' : '登录'}
          </button>
        </form>
        <div className="mt-6 space-y-2">
          <p className="text-xs text-muted text-center mb-2">演示账号快捷登录</p>
          {[
            { email: 'admin@example.com', label: '管理员', color: 'bg-primary/10 text-primary-300 border-primary/30' },
            { email: 'supervisor@example.com', label: '主管', color: 'bg-warning/10 text-warning border-warning/30' },
            { email: 'tech1@example.com', label: '工程师', color: 'bg-success/10 text-green-400 border-green-400/30' },
          ].map(({ email: e, label, color }) => (
            <button
              key={e}
              onClick={() => quickLogin(e)}
              disabled={loading}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm border ${color}`}
            >
              {label}: {e}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
