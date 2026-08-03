'use client';
import { ReactNode, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import {
  LayoutDashboard, AlertTriangle, Wrench, Cpu, BookOpen, Bot, Settings, Menu, X, LogOut,
  Activity, BrainCircuit, ShieldCheck
} from 'lucide-react';

interface NavItem {
  label: string;
  href: string;
  icon: ReactNode;
  roles: string[];
}

const ALL_NAV_ITEMS: NavItem[] = [
  { label: '智能运维驾驶舱', href: '/dashboard', icon: <LayoutDashboard size={18} />, roles: ['admin', 'supervisor', 'technician'] },
  { label: '实时状态监测', href: '/monitoring', icon: <Activity size={18} />, roles: ['admin', 'supervisor', 'technician'] },
  { label: '预测性维护', href: '/predictive-maintenance', icon: <BrainCircuit size={18} />, roles: ['admin', 'supervisor', 'technician'] },
  { label: '设备资产中心', href: '/equipment', icon: <Cpu size={18} />, roles: ['admin', 'supervisor', 'technician'] },
  { label: '故障上报', href: '/fault-reports', icon: <AlertTriangle size={18} />, roles: ['admin', 'supervisor', 'technician'] },
  { label: '智能工单中心', href: '/work-orders', icon: <Wrench size={18} />, roles: ['admin', 'supervisor', 'technician'] },
  { label: '操作审批中心', href: '/approvals', icon: <ShieldCheck size={18} />, roles: ['admin', 'supervisor', 'technician'] },
  { label: '运维知识中心', href: '/knowledge', icon: <BookOpen size={18} />, roles: ['admin', 'supervisor', 'technician'] },
  { label: '运维 Agent', href: '/copilot', icon: <Bot size={18} />, roles: ['admin', 'supervisor', 'technician'] },
  { label: '系统管理', href: '/admin', icon: <Settings size={18} />, roles: ['admin'] },
];

const ROLE_LABELS: Record<string, string> = {
  admin: '管理员', supervisor: '主管', technician: '工程师',
};

export default function AppLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  // No sidebar on login page
  if (pathname === '/login') {
    return <>{children}</>;
  }

  const role = user?.role || 'technician';
  const navItems = ALL_NAV_ITEMS.filter(item => item.roles.includes(role));

  const handleLogout = () => {
    logout();
    router.push('/login');
  };

  const sidebar = (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-card-border">
        <div className="flex items-center gap-2 mb-1">
          <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center">
            <Wrench size={16} className="text-primary-400" />
          </div>
          <div className="min-w-0">
            <span className="block font-bold text-sm leading-tight">工业智能运维平台</span>
            <span className="block text-[10px] text-muted mt-0.5">AI Agent · Predictive Maintenance</span>
          </div>
        </div>
        {user && (
          <div className="mt-2 flex items-center justify-between">
            <div className="text-xs text-muted">
              <span>{user.full_name}</span>
              <span className="ml-1 opacity-60">({ROLE_LABELS[role] || role})</span>
            </div>
          </div>
        )}
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {navItems.map(item => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
          return (
            <button
              key={item.href}
              onClick={() => { router.push(item.href); setMobileOpen(false); }}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-primary/15 text-primary-300 font-medium'
                  : 'text-muted hover:bg-white/5 hover:text-white'
              }`}
            >
              {item.icon}
              <span>{item.label}</span>
              {item.href === '/monitoring' && (
                <span className="ml-auto w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" aria-label="在线" />
              )}
            </button>
          );
        })}
      </nav>
      <div className="p-3 border-t border-card-border">
        <button onClick={handleLogout} className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-muted hover:bg-red-500/10 hover:text-red-400 transition-colors">
          <LogOut size={16} /> 退出登录
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex flex-col w-56 shrink-0 border-r border-card-border bg-card">
        {sidebar}
      </aside>

      {/* Mobile Header */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-30 bg-card border-b border-card-border px-4 py-3 flex items-center justify-between">
        <button onClick={() => setMobileOpen(!mobileOpen)} className="btn btn-outline btn-sm p-1.5">
          {mobileOpen ? <X size={18} /> : <Menu size={18} />}
        </button>
        <span className="text-sm font-medium">工业智能运维平台</span>
        <button onClick={handleLogout} className="btn btn-outline btn-sm p-1.5">
          <LogOut size={16} />
        </button>
      </div>

      {/* Mobile Drawer */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-20 flex">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMobileOpen(false)} />
          <div className="relative w-56 bg-card border-r border-card-border z-30 pt-14 animate-slide-in">
            {sidebar}
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto lg:pt-0 pt-14 p-4 lg:p-6">
        {children}
      </main>
    </div>
  );
}
