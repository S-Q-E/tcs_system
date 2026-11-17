import { expect, test, type Page } from "@playwright/test";

// Mobile adaptation: checks in a phone viewport.
// Desktop specs are separate; this file runs with the same `npm run e2e` command.
test.use({
  viewport: { width: 375, height: 667 },
  hasTouch: true,
  isMobile: true,
});

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "mobile-test@example.com";
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "mobile-test-password-1";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/deals");
}

async function expectNoPageOverflow(page: Page, where: string) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, `horizontal overflow on ${where}`).toBeLessThanOrEqual(1);
}

test("mobile: login has no horizontal overflow", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await expectNoPageOverflow(page, "/login");
});

test("mobile: main screens have no horizontal overflow", async ({ page }) => {
  await login(page);
  for (const path of ["/deals", "/tasks", "/contacts", "/dialogs", "/analytics"]) {
    await page.goto(path);
    await expect(page.locator("main")).toBeVisible();
    await expectNoPageOverflow(page, path);
  }
  // The bottom tab bar is visible, the sidebar is not.
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
});

test("mobile: dialogs list -> chat -> back", async ({ page }) => {
  await login(page);
  await page.goto("/dialogs");

  const rows = page.locator("aside button", { hasText: /(Bot paused|Bot replying)/ });
  await expect(rows.first()).toBeVisible({ timeout: 15_000 });

  // In the list view the chat is hidden; only the list is visible.
  await expect(page.getByLabel("Message to prospect")).toBeHidden();

  await rows.first().click();
  await expect(page).toHaveURL(/wa=/);

  // In the chat the list is hidden; Back, the composer and Send are visible.
  const back = page.getByRole("button", { name: "Back to list" });
  await expect(back).toBeVisible();
  const composer = page.getByLabel("Message to prospect");
  await expect(composer).toBeVisible();
  const send = page.getByRole("button", { name: "Send" });
  await expect(send).toBeVisible();
  const box = await send.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.y + box!.height).toBeLessThanOrEqual(667);
  await expectNoPageOverflow(page, "/dialogs?wa=");

  await back.click();
  await expect(page).toHaveURL(/\/dialogs$/);
  await expect(rows.first()).toBeVisible();
  await expect(composer).toBeHidden();
});
