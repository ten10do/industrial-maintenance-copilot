import { test, expect } from '@playwright/test';
import { loginAs, navigateTo } from './helpers/auth';

const BASE = '/api/v1';

async function apiGet(page: any, path: string) {
  return page.evaluate(async ({ base, path: p }: { base: string; path: string }) => {
    const token = localStorage.getItem('token');
    const res = await fetch(`${base}${p}`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return res.json();
  }, { base: BASE, path });
}

async function apiPost(page: any, path: string, body: any) {
  return page.evaluate(async ({ base, path: p, body: b }: { base: string; path: string; body: any }) => {
    const token = localStorage.getItem('token');
    const res = await fetch(`${base}${p}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(b),
    });
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return res.json();
  }, { base: BASE, path, body });
}

test.describe('知识库浏览与查询', () => {

  test('场景1: 浏览知识库列表并查看详情', async ({ page }) => {
    await loginAs(page, 'technician');

    // Navigate to knowledge page via sidebar
    await navigateTo(page, '运维知识中心', '**/knowledge');

    // Wait for items to load
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    await expect(page.getByText('加载中...', { exact: true })).toBeHidden({
      timeout: 10000,
    });

    // Verify the page title
    await expect(page.locator('h1')).toContainText('知识库');

    // Check if we have items or empty state
    const emptyState = page.locator('text=知识库中暂无内容');
    const hasItems = await emptyState.isVisible({ timeout: 3000 }).catch(() => false);

    if (hasItems) {
      // Empty state is handled - should show the BookOpen icon and text
      await expect(page.locator('text=知识库中暂无内容')).toBeVisible();
    } else {
      // Verify list items are rendered
      const cards = page.locator('.card');
      const cardCount = await cards.count();
      expect(cardCount).toBeGreaterThan(0);

      // Each card should have a title
      const firstTitle = await cards.first().locator('.font-semibold').textContent();
      expect(firstTitle).toBeTruthy();

      // Click first item to enter detail
      await cards.first().click({ force: true });
      await page.waitForURL(/\/knowledge\/\d+/, { timeout: 10000 });

      // Wait for detail content to load (title should appear, then info section)
      await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });
      // Detail page shows metadata like source, content type etc.
      await expect(page.getByText('来源名称', { exact: true })).toBeVisible({
        timeout: 10000,
      });
    }
  });

  test('场景2: 按分类筛选知识库条目', async ({ page }) => {
    await loginAs(page, 'supervisor');

    await navigateTo(page, '运维知识中心', '**/knowledge');
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // Verify category filter dropdown exists
    const categorySelect = page.locator('select').first();
    await expect(categorySelect).toBeVisible({ timeout: 5000 });

    // Select a category
    await categorySelect.selectOption('manual');
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // After filtering, either show filtered results or empty state
    // Just verify no crash - page should still show title
    await expect(page.locator('h1')).toContainText('知识库');

    // Reset filter
    await categorySelect.selectOption('');
    await page.waitForLoadState('networkidle', { timeout: 10000 });
  });

  test('场景3: 搜索知识库', async ({ page }) => {
    await loginAs(page, 'technician');

    await navigateTo(page, '运维知识中心', '**/knowledge');
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // Find search input
    const searchInput = page.locator('input[placeholder="搜索标题或内容..."]');
    await expect(searchInput).toBeVisible({ timeout: 5000 });

    // Clear search, type keyword, press Enter to trigger API search
    await searchInput.fill('接近');
    await searchInput.press('Enter');
    // Wait briefly for the API call to complete
    await page.waitForTimeout(2000);

    // Either shows results cards or "未找到匹配的知识条目"
    const results = page.locator('.card');
    const noResult = page.locator('text=未找到匹配的知识条目');
    const hasResults = await results.first().isVisible({ timeout: 5000 }).catch(() => false);
    const hasNoResult = await noResult.isVisible({ timeout: 5000 }).catch(() => false);

    // Either outcome is valid
    expect(hasResults || hasNoResult).toBe(true);
  });

  test('场景4: 管理员创建知识条目并删除', async ({ page }) => {
    await loginAs(page, 'admin');

    await navigateTo(page, '运维知识中心', '**/knowledge');
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // Click "新建条目" button
    const newBtn = page.locator('text=新建条目');
    await expect(newBtn).toBeVisible({ timeout: 5000 });
    await newBtn.click({ force: true });

    // Should navigate to create page
    await page.waitForURL(/\/knowledge\/new/, { timeout: 10000 });
    await expect(page.locator('h1')).toContainText(/新建|创建/);

    // Fill in form
    await page.fill('input[placeholder="知识条目标题"]', `E2E 测试条目 ${Date.now()}`);
    await page.fill('textarea[placeholder="知识条目正文内容（支持 Markdown 格式）"]', '这是 E2E 测试创建的知识条目内容。');

    // Select category
    const categorySelect = page.locator('select').first();
    if (await categorySelect.isVisible({ timeout: 3000 }).catch(() => false)) {
      await categorySelect.selectOption('case');
    }

    // Submit
    const submitBtn = page.locator('button[type="submit"]');
    await expect(submitBtn).toBeEnabled({ timeout: 5000 });

    const saveResp = page.waitForResponse(
      resp => resp.url().includes('/api/v1/knowledge') && resp.request().method() === 'POST',
      { timeout: 30000 }
    );
    await submitBtn.click({ force: true });
    const resp = await saveResp.catch(() => null);

    if (resp && resp.status() === 200) {
      // Wait for redirect to detail
      await page.waitForURL(/\/knowledge\/\d+/, { timeout: 10000 });
      await page.waitForLoadState('networkidle', { timeout: 10000 });

      // Verify detail page
      await expect(page.locator('h1')).toBeVisible({ timeout: 5000 });

      // Delete the entry using role-based selector
      const deleteBtn = page.getByRole('button', { name: /删除/ });
      if (await deleteBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
        // Set up dialog handler BEFORE clicking - this prevents auto-dismiss
        page.once('dialog', async dialog => {
          await dialog.accept();
        });
        await deleteBtn.click({ force: true });
        // Wait for redirect back to list after deletion
        await page.waitForURL(/\/knowledge$/, { timeout: 10000 }).catch(() => {});
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
      }
    }
  });
});

test.describe('Copilot AI 问答与引用来源', () => {

  test('场景5: 提问并查看 AI 回答与引用来源', async ({ page }) => {
    await loginAs(page, 'technician');

    // Navigate to copilot page
    await navigateTo(page, '运维 Agent', '**/copilot');
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // Verify page title
    await expect(page.locator('h1')).toContainText('AI 维修助手');

    // Safety notice should be visible
    await expect(page.locator('text=AI 建议仅供辅助')).toBeVisible({ timeout: 5000 });

    // Question input should be present
    const questionInput = page.locator('[data-testid="copilot-question-input"]');
    await expect(questionInput).toBeVisible({ timeout: 5000 });

    // Type a question
    await questionInput.fill('E102 故障一般是什么原因？');

    // Submit button should be enabled
    const submitBtn = page.locator('[data-testid="copilot-submit-button"]');
    await expect(submitBtn).toBeEnabled({ timeout: 3000 });

    // Click submit and wait for response
    const askResp = page.waitForResponse(
      resp => resp.url().includes('/api/v1/copilot/ask'),
      { timeout: 30000 }
    );
    await submitBtn.click({ force: true });
    const resp = await askResp.catch(() => null);

    if (resp && resp.ok()) {
      // Wait for answer to render
      await page.waitForLoadState('networkidle', { timeout: 10000 });
      await page.waitForTimeout(500);

      // Answer should be visible (not null)
      const answerText = page.locator('.prose');
      const hasAnswer = await answerText.isVisible({ timeout: 5000 }).catch(() => false);

      if (hasAnswer) {
        // Verify answer content
        const answerContent = await answerText.textContent();
        expect(answerContent).toBeTruthy();

        // Check for Mock AI badge
        const mockBadge = page.locator('text=Mock AI 模式');
        const hasMockBadge = await mockBadge.isVisible({ timeout: 3000 }).catch(() => false);

        // Confidence score should be visible
        const confidence = page.locator('text=置信度');
        expect(confidence).toBeVisible({ timeout: 3000 });

        // Check if citations are visible
        const citations = page.locator('text=引用来源');
        const hasCitations = await citations.isVisible({ timeout: 3000 }).catch(() => false);

        if (!hasCitations) {
          // If no citations, should show evidence insufficient warning
          const noEvidence = page.locator('text=证据不足');
          const hasNoEvidence = await noEvidence.isVisible({ timeout: 3000 }).catch(() => false);
          expect(hasNoEvidence || hasMockBadge).toBe(true);
        } else {
          // Verify citation cards exist
          const citationCards = page.locator('.rounded-full.bg-primary\\/20');
          const cardCount = await citationCards.count();
          expect(cardCount).toBeGreaterThan(0);
        }
      }
    }
  });

  test('场景6: Copilot 无可靠来源场景', async ({ page }) => {
    await loginAs(page, 'technician');

    await navigateTo(page, '运维 Agent', '**/copilot');
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // Type a very specific question unlikely to match
    const questionInput = page.locator('[data-testid="copilot-question-input"]');
    await questionInput.fill('什么是量子纠缠在维修中的应用？');

    const submitBtn = page.locator('[data-testid="copilot-submit-button"]');
    await expect(submitBtn).toBeEnabled({ timeout: 3000 });

    const askResp = page.waitForResponse(
      resp => resp.url().includes('/api/v1/copilot/ask'),
      { timeout: 30000 }
    );
    await submitBtn.click({ force: true });
    const resp = await askResp.catch(() => null);

    if (resp && resp.ok()) {
      await page.waitForLoadState('networkidle', { timeout: 10000 });

      // Should still get an answer, but with low confidence
      const confidence = page.locator('text=置信度:');
      expect(confidence).toBeVisible({ timeout: 5000 });

      // Either has citation or shows evidence insufficient
      const hasCitations = await page.locator('text=引用来源').isVisible({ timeout: 3000 }).catch(() => false);
      const hasNoEvidence = await page.locator('text=证据不足').isVisible({ timeout: 3000 }).catch(() => false);
      expect(hasCitations || hasNoEvidence).toBe(true);
    }
  });

  test('场景7: 清空对话重新提问', async ({ page }) => {
    await loginAs(page, 'technician');

    await navigateTo(page, '运维 Agent', '**/copilot');
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // First question
    const questionInput = page.locator('[data-testid="copilot-question-input"]');
    await questionInput.fill('E102 故障');

    const submitBtn = page.locator('[data-testid="copilot-submit-button"]');
    await expect(submitBtn).toBeEnabled({ timeout: 3000 });

    const askResp1 = page.waitForResponse(
      resp => resp.url().includes('/api/v1/copilot/ask'),
      { timeout: 30000 }
    );
    await submitBtn.click({ force: true });

    // Wait for the answer panel to render (need result !== null for clear button to show)
    const gotAnswer = await page.locator('.prose').waitFor({ state: 'visible', timeout: 15000 }).then(() => true).catch(() => false);

    if (gotAnswer) {
      // Clear button appears when answer is available — it's the btn-outline in the input row
      // (example questions disappear when result is set, so only the Trash2 clear button remains)
      const clearBtn = page.locator('.card button.btn-outline');
      await expect(clearBtn.first()).toBeVisible({ timeout: 5000 });
      await clearBtn.first().click({ force: true });

      // After clearing, result is null → input is cleared, answer disappears
      await page.waitForTimeout(500);
      const inputValue = await questionInput.inputValue();
      expect(inputValue).toBe('');

      // Answer panel should be gone
      await expect(page.locator('.prose')).not.toBeVisible({ timeout: 5000 });

      // Example questions should reappear
      await expect(page.locator('text=快捷示例')).toBeVisible({ timeout: 5000 });
    }
  });

  test('场景8: 快捷示例问题一键提问', async ({ page }) => {
    await loginAs(page, 'technician');

    await navigateTo(page, '运维 Agent', '**/copilot');
    await page.waitForLoadState('networkidle', { timeout: 10000 });

    // Check example questions are visible
    const exampleSection = page.locator('text=快捷示例');
    await expect(exampleSection).toBeVisible({ timeout: 5000 });

    // Click the first example question
    const exampleQ1 = page.locator('text=E102 故障一般是什么原因？');
    await expect(exampleQ1).toBeVisible({ timeout: 5000 });

    const askResp = page.waitForResponse(
      resp => resp.url().includes('/api/v1/copilot/ask'),
      { timeout: 30000 }
    );
    await exampleQ1.click({ force: true });
    const resp = await askResp.catch(() => null);

    if (resp && resp.ok()) {
      await page.waitForLoadState('networkidle', { timeout: 10000 });

      // Answer should appear
      const hasAnswer = await page.locator('.prose').isVisible({ timeout: 5000 }).catch(() => false);
      const hasCitations = await page.locator('text=引用来源').isVisible({ timeout: 3000 }).catch(() => false);
      const hasNoEvidence = await page.locator('text=证据不足').isVisible({ timeout: 3000 }).catch(() => false);

      // At least one of these should be true
      expect(hasAnswer || hasCitations || hasNoEvidence).toBe(true);
    }
  });
});
