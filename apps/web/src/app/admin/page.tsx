'use client';
import { Settings, Construction } from 'lucide-react';

export default function AdminPage() {
  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-xl font-bold mb-4">系统管理</h1>
      <div className="card text-center py-16">
        <Construction size={48} className="mx-auto mb-4 text-yellow-400" />
        <h2 className="text-lg font-medium mb-2">功能建设中</h2>
        <p className="text-sm text-muted max-w-md mx-auto">
          系统管理功能正在开发中，将包含用户管理、角色配置和系统设置。
        </p>
      </div>
    </div>
  );
}
