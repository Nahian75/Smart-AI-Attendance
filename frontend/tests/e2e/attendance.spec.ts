import { test, expect } from '@playwright/test';

test.describe('Smart Attendance System E2E Tests', () => {
  const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';

  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
  });

  test('Login with valid credentials', async ({ page }) => {
    await page.fill('input[type="email"]', 'admin@demo.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL(/dashboard/);
    await expect(page.locator('h1')).toContainText('Overview');
  });

  test('Login with invalid credentials', async ({ page }) => {
    await page.fill('input[type="email"]', 'admin@demo.com');
    await page.fill('input[type="password"]', 'wrongpassword');
    await page.click('button[type="submit"]');

    await expect(page.locator('text=Invalid credentials')).toBeVisible();
  });

  test('Navigate to all dashboard pages', async ({ page }) => {
    // Login first
    await page.fill('input[type="email"]', 'admin@demo.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');

    // Overview
    await page.click('text=Overview');
    await expect(page).toHaveURL(/dashboard/);
    await expect(page.locator('h1')).toContainText('Overview');

    // Employees
    await page.click('text=Employees');
    await expect(page).toHaveURL(/dashboard\/employees/);

    // Cameras
    await page.click('text=Cameras');
    await expect(page).toHaveURL(/dashboard\/cameras/);

    // Alerts
    await page.click('text=Alerts');
    await expect(page).toHaveURL(/dashboard\/alerts/);

    // Security Alerts
    await page.click('text=Security');
    await expect(page).toHaveURL(/dashboard\/security-alerts/);

    // Analytics
    await page.click('text=Analytics');
    await expect(page).toHaveURL(/dashboard\/analytics/);

    // Reports
    await page.click('text=Reports');
    await expect(page).toHaveURL(/dashboard\/reports/);
  });

  test('View occupancy cards', async ({ page }) => {
    await page.fill('input[type="email"]', 'admin@demo.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');

    await page.click('text=Overview');

    // Check building occupancy
    await expect(page.locator('text=Building occupancy')).toBeVisible();
    await expect(page.locator('text=Building occupancy').locator('..')).toContainText(/\d+/);

    // Check zone cards
    await expect(page.locator('text=floor_1')).toBeVisible();
    await expect(page.locator('text=floor_2')).toBeVisible();
  });

  test('View shift compliance table', async ({ page }) => {
    await page.fill('input[type="email"]', 'admin@demo.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');

    await page.click('text=Reports');

    // Check shift compliance table
    await expect(page.locator('text=Shift compliance')).toBeVisible();
    await expect(page.locator('th').filter({ hasText: 'Employee' })).toBeVisible();
    await expect(page.locator('th').filter({ hasText: 'Dept' })).toBeVisible();
    await expect(page.locator('th').filter({ hasText: 'On-time' })).toBeVisible();
    await expect(page.locator('th').filter({ hasText: 'Late' })).toBeVisible();
  });

  test('Download monthly CSV report', async ({ page }) => {
    await page.fill('input[type="email"]', 'admin@demo.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');

    await page.click('text=Reports');

    // Select year and month
    const yearSelect = page.locator('select');
    await yearSelect.selectOption('2025');

    const monthSelect = page.locator('select:nth-child(2)');
    await monthSelect.selectOption('1');

    // Click download button
    await page.click('text=Download CSV');

    // Wait for download
    const download = await page.waitForEvent('download');
    expect(download.suggestedFilename()).toContain('attendance_2025_01');
  });

  test('Toggle dark mode', async ({ page }) => {
    await page.fill('input[type="email"]', 'admin@demo.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');

    // Click theme toggle
    await page.click('button[aria-label="Toggle theme"]');

    // Check if dark mode is applied (html element should have dark class)
    const html = page.locator('html');
    await expect(html).toHaveClass(/dark/);

    // Toggle back to light mode
    await page.click('button[aria-label="Toggle theme"]');
    await expect(html).not.toHaveClass(/dark/);
  });

  test('Responsive layout - mobile view', async ({ page }) => {
    // Set viewport to mobile size
    await page.setViewportSize({ width: 375, height: 667 });

    await page.fill('input[type="email"]', 'admin@demo.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');

    // Check sidebar is collapsible or hidden on mobile
    const sidebar = page.locator('aside');
    await expect(sidebar).toBeVisible();

    // Check dashboard content is responsive
    const dashboard = page.locator('main');
    await expect(dashboard).toBeVisible();
  });

  test('Responsive layout - tablet view', async ({ page }) => {
    // Set viewport to tablet size
    await page.setViewportSize({ width: 768, height: 1024 });

    await page.fill('input[type="email"]', 'admin@demo.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');

    // Check dashboard layout adapts
    const dashboard = page.locator('main');
    await expect(dashboard).toBeVisible();

    // Check sidebar is visible
    const sidebar = page.locator('aside');
    await expect(sidebar).toBeVisible();
  });

  test('WebSocket connection for live events', async ({ page }) => {
    await page.fill('input[type="email"]', 'admin@demo.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');

    // Wait for WebSocket connection
    await page.waitForTimeout(2000);

    // Check if live event feed is visible
    await expect(page.locator('text=Recent check-ins')).toBeVisible();

    // Check if alerts feed is visible
    await expect(page.locator('text=Security alerts')).toBeVisible();
  });

  test('View security alerts', async ({ page }) => {
    await page.fill('input[type="email"]', 'admin@demo.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');

    await page.click('text=Security');

    // Check security alerts section
    await expect(page.locator('text=Security Incidents')).toBeVisible();
    await expect(page.locator('text=Loitering Monitoring')).toBeVisible();

    // Check alert types
    await expect(page.locator('text=🚨 Intruder')).toBeVisible();
    await expect(page.locator('text=🚫 Blacklist')).toBeVisible();
    await expect(page.locator('text=🔒 Restricted area')).toBeVisible();
  });

  test('View analytics dashboard', async ({ page }) => {
    await page.fill('input[type="email"]', 'admin@demo.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');

    await page.click('text=Analytics');

    // Check building occupancy
    await expect(page.locator('text=Building occupancy')).toBeVisible();

    // Check department breakdown
    await expect(page.locator('text=floor_1')).toBeVisible();
    await expect(page.locator('text=floor_2')).toBeVisible();

    // Check shift compliance table
    await expect(page.locator('text=Shift compliance')).toBeVisible();
  });

  test('Employee management - view employees list', async ({ page }) => {
    await page.fill('input[type="email"]', 'admin@demo.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');

    await page.click('text=Employees');

    // Check employees list is visible
    await expect(page.locator('text=Employees')).toBeVisible();

    // Check table headers
    await expect(page.locator('th').filter({ hasText: 'Name' })).toBeVisible();
    await expect(page.locator('th').filter({ hasText: 'Email' })).toBeVisible();
    await expect(page.locator('th').filter({ hasText: 'Department' })).toBeVisible();
  });

  test('Camera management - view cameras list', async ({ page }) => {
    await page.fill('input[type="email"]', 'admin@demo.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');

    await page.click('text=Cameras');

    // Check cameras list is visible
    await expect(page.locator('text=Cameras')).toBeVisible();

    // Check table headers
    await expect(page.locator('th').filter({ hasText: 'Name' })).toBeVisible();
    await expect(page.locator('th').filter({ hasText: 'Location' })).toBeVisible();
    await expect(page.locator('th').filter({ hasText: 'Status' })).toBeVisible();
  });
});