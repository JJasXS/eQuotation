// Frontend behavior tests for purchase request create form (Playwright style scaffold).
// Requires Playwright test runner if you want to execute this file.

import { test, expect } from '@playwright/test';

test('purchase request form validates required fields', async ({ page }) => {
  await page.goto('http://localhost:5000/admin/procurement');
  await page.getByRole('button', { name: 'Create eProcurement' }).click();
  await page.getByRole('button', { name: 'Submit Purchase Request' }).click();
  await expect(page.locator('#pr-form-message')).toContainText('requesterId is required');
});

test('purchase request form calculates totals', async ({ page }) => {
  await page.goto('http://localhost:5000/admin/procurement');
  await page.getByRole('button', { name: 'Create eProcurement' }).click();

  await page.locator('#pr-requester-id').fill('U001');
  await page.locator('#pr-department-id').fill('IT');
  await page.locator('#pr-line-items-body tr:first-child td:nth-child(1) input').fill('ITM-001');
  await page.locator('#pr-line-items-body tr:first-child td:nth-child(2) input').fill('Mouse');
  await page.locator('#pr-line-items-body tr:first-child td:nth-child(4) input').fill('2');
  await page.locator('#pr-line-items-body tr:first-child td:nth-child(5) input').fill('50');
  await page.locator('#pr-line-items-body tr:first-child td:nth-child(6) input').fill('6');

  await expect(page.locator('#pr-grand-total')).toHaveText('106.00');
});
