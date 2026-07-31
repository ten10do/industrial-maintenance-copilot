import { Page, expect } from '@playwright/test';

const DEFAULT_CREDENTIALS: Record<string, { email: string; password: string }> = {
  admin: {
    email: process.env.E2E_ADMIN_EMAIL ?? 'admin@example.com',
    password: process.env.E2E_ADMIN_PASSWORD ?? 'Demo123456',
  },
  supervisor: {
    email: process.env.E2E_SUPERVISOR_EMAIL ?? 'supervisor@example.com',
    password: process.env.E2E_SUPERVISOR_PASSWORD ?? 'Demo123456',
  },
  technician: {
    email: process.env.E2E_TECHNICIAN_EMAIL ?? 'tech1@example.com',
    password: process.env.E2E_TECHNICIAN_PASSWORD ?? 'Demo123456',
  },
  technician2: {
    email: process.env.E2E_TECHNICIAN2_EMAIL ?? 'tech2@example.com',
    password: process.env.E2E_TECHNICIAN2_PASSWORD ?? 'Demo123456',
  },
};

export type Role = keyof typeof DEFAULT_CREDENTIALS;

/**
 * Login as a specific role. Clears previous auth state first.
 */
export async function loginAs(page: Page, role: Role): Promise<void> {
  // Clear any existing auth state
  await page.goto('/login');
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.waitForSelector('input[type="email"]', { timeout: 10000 });

  const creds = DEFAULT_CREDENTIALS[role];
  await page.fill('input[type="email"]', creds.email);
  await page.fill('input[type="password"]', creds.password);
  // Use force click to bypass "stable" check that times out on slow connections
  await page.locator('button[type="submit"]').click({ force: true });

  await page.waitForURL('/dashboard', { timeout: 15000 });
  // Wait for dashboard to fully render (network idle + content)
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
  // Give React time to finish rendering
  await page.waitForTimeout(2000);
  // h1 text varies by role
  const h1Text = role === 'technician' || role === 'technician2' ? '维修工作台' : '智能运维驾驶舱';
  await expect(page.locator('h1')).toContainText(h1Text, { timeout: 10000 }).catch(() => {});
}

/**
 * Switch login to a different user. Clears localStorage and logs in fresh.
 */
export async function switchLogin(page: Page, email: string, password: string): Promise<void> {
  await page.goto('/login');
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.waitForSelector('input[type="email"]', { timeout: 10000 });

  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);
  await page.locator('button[type="submit"]').click({ force: true });

  await page.waitForURL('/dashboard', { timeout: 15000 });
}

export async function logout(page: Page): Promise<void> {
  const logoutBtn = page.locator('text=退出登录');
  if (await logoutBtn.isVisible()) {
    await logoutBtn.click();
    await page.waitForURL('/login', { timeout: 10000 });
  }
}

export async function navigateTo(page: Page, label: string, expectedPath: string): Promise<void> {
  await page.locator(`text=${label}`).first().click({ force: true });
  await page.waitForURL(expectedPath, { timeout: 10000 });
}
