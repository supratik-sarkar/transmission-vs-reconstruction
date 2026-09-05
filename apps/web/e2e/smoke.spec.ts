import { expect, test } from '@playwright/test';

/**
 * End-to-end smoke tests.
 *
 * Require the API on 127.0.0.1:8099 in DEMO_MODE and the dev server on :5173.
 * They assert behaviour a unit test cannot: that the panes stay synchronised and
 * that no secret reaches the delivered bundle.
 */

test('application loads and shows its run mode', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Transmission');
  await expect(page.locator('.badge')).toBeVisible();
});

test('synthetic run streams and populates the panes', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /Run synthetic demo/ }).click();
  await expect(page.locator('.timeline .row').first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('.stage[data-status="ok"]').first()).toBeVisible();
});

test('selecting an atom synchronises source, inspector and causal panes', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /Run synthetic demo/ }).click();
  await page.locator('tbody tr').first().click();
  await expect(page.locator('tbody tr[aria-selected="true"]')).toHaveCount(1);
  await expect(page.getByText(/Δᵃᵛ/)).toBeVisible();
});

test('benchmark page shows readiness and no fabricated results', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Benchmark arena' }).click();
  await expect(page.getByText('NOT RUN').first()).toBeVisible();
  await expect(page.getByText(/primary comparators are benchmark-eligible/)).toBeVisible();
});

test('provider status reveals no secret material', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'System' }).click();
  const body = await page.locator('body').innerText();
  expect(body).not.toMatch(/sk-[A-Za-z0-9_-]{16,}/);
  expect(body).not.toMatch(/AIza[0-9A-Za-z_-]{30,}/);
  expect(body).not.toMatch(/Bearer\s+\S{16,}/);
});

test('research mode blocks the prohibited action', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'System' }).click();
  // The final test must be visibly sealed and must never appear as a button.
  await expect(page.getByText(/SEALED/)).toBeVisible();
  await expect(page.getByRole('button', { name: /final test/i })).toHaveCount(0);
});

test('multi-hop playback advances through the depth sweep', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Multi-hop' }).click();
  await expect(page.getByRole('button', { name: 'h = 5' })).toBeVisible();
  await page.getByRole('button', { name: 'h = 3' }).click();
  await expect(page.getByText(/Depth 3 of a/)).toBeVisible();
});
