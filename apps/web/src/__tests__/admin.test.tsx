import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import AdminPage from '@/app/admin/page';

describe('AdminPage', () => {
  it('渲染页面标题', () => {
    render(<AdminPage />);
    expect(screen.getByText('系统管理')).toBeInTheDocument();
  });

  it('展示功能建设中提示', () => {
    render(<AdminPage />);
    expect(screen.getByText('功能建设中')).toBeInTheDocument();
  });

  it('展示功能规划说明', () => {
    render(<AdminPage />);
    expect(screen.getByText(/系统管理功能正在开发中/)).toBeInTheDocument();
    expect(screen.getByText(/用户管理/)).toBeInTheDocument();
  });
});
