import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import KnowledgePage from '@/app/knowledge/page';

describe('KnowledgePage', () => {
  it('渲染页面标题', () => {
    render(<KnowledgePage />);
    expect(screen.getByText('知识库')).toBeInTheDocument();
  });

  it('展示功能建设中提示', () => {
    render(<KnowledgePage />);
    expect(screen.getByText('功能建设中')).toBeInTheDocument();
  });

  it('展示功能规划说明', () => {
    render(<KnowledgePage />);
    expect(screen.getByText(/知识库管理功能正在开发中/)).toBeInTheDocument();
  });

  it('展示三个功能模块入口', () => {
    render(<KnowledgePage />);
    expect(screen.getByText('维修手册')).toBeInTheDocument();
    expect(screen.getByText('操作规程')).toBeInTheDocument();
    expect(screen.getByText('故障案例')).toBeInTheDocument();
  });
});
