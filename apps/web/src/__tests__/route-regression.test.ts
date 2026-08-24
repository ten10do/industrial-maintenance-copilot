import fs from 'node:fs';
import path from 'node:path';

const EXPECTED_ROUTES = [
  '/',
  '/admin',
  '/alarms',
  '/approvals',
  '/copilot',
  '/dashboard',
  '/equipment',
  '/equipment/[id]',
  '/fault-reports',
  '/fault-reports/[id]',
  '/fault-reports/new',
  '/gateway',
  '/knowledge',
  '/knowledge/[id]',
  '/knowledge/[id]/edit',
  '/knowledge/new',
  '/login',
  '/monitoring',
  '/predictive-maintenance',
  '/work-orders',
  '/work-orders/[id]',
];

function collectPages(directory: string): string[] {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return collectPages(target);
    return entry.name === 'page.tsx' ? [target] : [];
  });
}

describe('application route regression', () => {
  it('preserves the complete master route inventory', () => {
    const appDirectory = path.join(process.cwd(), 'src', 'app');
    const routes = collectPages(appDirectory)
      .map((filename) => {
        const relative = path.relative(appDirectory, path.dirname(filename));
        return relative ? `/${relative.replaceAll(path.sep, '/')}` : '/';
      })
      .sort();

    expect(routes).toEqual([...EXPECTED_ROUTES].sort());
    expect(routes).toHaveLength(21);
  });
});
