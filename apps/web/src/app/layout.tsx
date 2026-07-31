import '@/styles/globals.css';
import { Metadata } from 'next';
import { Providers } from './providers';

export const metadata: Metadata = {
  title: '基于 AI Agent 的工业设备智能运维与预测性维护平台',
  description: '从设备遥测、异常诊断、风险预测到智能工单与维修验证的工业运维闭环平台',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
