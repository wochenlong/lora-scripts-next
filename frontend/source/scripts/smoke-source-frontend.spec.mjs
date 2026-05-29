import { expect, test } from "@playwright/test";

const shellRoutes = [
  "/",
  "/other/settings.html",
  "/lora/anima-finetune.html",
  "/missing-route",
];

for (const route of shellRoutes) {
  test(`source shell loads ${route}`, async ({ page }) => {
    await page.goto(route);
    await expect(page.locator("#app")).toBeVisible();
    await expect(page.locator(".sidebar")).toBeVisible();
  });
}

test("native tag editor source route loads embedded editor", async ({ page }) => {
  await page.goto("/native-tageditor.html");
  await expect(page.locator("#app")).toBeVisible();
  await expect(page.locator(".sidebar")).toBeVisible();
  await expect(page.locator("#sd-native-editor-entry")).toBeVisible();
  await expect(page.locator(".de-shell-embedded")).toBeVisible();
  await expect(page.locator("#dataset-path")).toBeVisible();
});
