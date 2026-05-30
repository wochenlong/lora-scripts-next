import { expect, test } from "@playwright/test";

test("production dist renders source-owned classic tag editor launcher", async ({ page }) => {
  await page.goto("/tageditor.html");
  await expect(page.locator(".classic-tag-editor-page")).toBeVisible();
  await expect(page.locator('iframe[src="/proxy/tageditor/"]')).toBeVisible();
  await expect(page.locator("#sd-native-editor-entry")).toHaveCount(0);
});

test("production dist renders native tag editor entries", async ({ page }) => {
  await page.goto("/native-tageditor.html");
  await expect(page.locator(".sidebar")).toBeVisible();
  await expect(page.locator("#sd-native-editor-entry")).toBeVisible();
  await expect(page.locator("#dataset-path")).toBeVisible();

  await page.goto("/native-tageditor-standalone.html");
  await expect(page.locator(".sidebar")).toHaveCount(0);
  await expect(page.locator("#sd-native-editor-entry")).toBeVisible();
  await expect(page.locator("#dataset-path")).toBeVisible();
});

test("production dist renders migrated source pages", async ({ page }) => {
  await page.goto("/lora/anima-finetune.html");
  await expect(page.locator("#anima-train-form")).toBeVisible();
  await expect(page.locator(".anima-contract-card")).toContainText("Source Contract");

  await page.goto("/lora/params.html");
  await expect(page.locator(".params-page")).toBeVisible();
  await expect(page.locator(".params-section-card")).toHaveCount(12);

  await page.goto("/tensorboard.html");
  await expect(page.locator(".tensorboard-page")).toBeVisible();
  await expect(page.locator('iframe[src="/proxy/tensorboard/"]')).toBeVisible();
});
