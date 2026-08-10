import { expect, test } from '@playwright/test';

test('project lifecycle survives browser close and reload', async ({ browser, page }) => {
  const name = `中文项目-${Date.now()}`;
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '项目中心' })).toBeVisible();

  await page.getByLabel('项目名称').fill(name);
  await page.getByRole('button', { name: '创建项目' }).click();
  await expect(page.getByRole('heading', { name })).toBeVisible();
  await expect(page.getByText(/当前项目目录：中文项目-/)).toBeVisible();

  const projectUrl = page.url();
  await page.close();
  const reopened = await browser.newPage();
  await reopened.goto('/');
  await reopened.getByRole('button', { name: new RegExp(name) }).click();
  await expect(reopened).toHaveURL(projectUrl);

  await reopened.getByRole('button', { name: '第4步 逐页旁白校对' }).click();
  await expect(reopened.getByRole('button', { name: '第4步 逐页旁白校对' })).toHaveAttribute(
    'aria-current',
    'step',
  );
  await reopened.reload();
  await expect(reopened.getByRole('button', { name: '第4步 逐页旁白校对' })).toHaveAttribute(
    'aria-current',
    'step',
  );

  await reopened.getByRole('button', { name: '暂停项目' }).click();
  await expect(reopened.getByRole('button', { name: '继续项目' })).toBeVisible();
  await reopened.getByRole('button', { name: '继续项目' }).click();
  await expect(reopened.getByRole('button', { name: '暂停项目' })).toBeVisible();
});
