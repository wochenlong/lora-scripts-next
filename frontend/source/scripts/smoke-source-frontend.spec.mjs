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

test("dataset editor fallback route loads native editor", async ({ page }) => {
  await page.goto("/dataset-editor.html");
  await expect(page.locator("#app")).toBeVisible();
  await expect(page.locator("#sd-native-editor-entry")).toBeVisible();
  await expect(page.locator("#dataset-path")).toBeVisible();
});

test("tagger source route loads progress dock", async ({ page }) => {
  await page.goto("/tagger.html");
  await expect(page.locator("#app")).toBeVisible();
  await expect(page.locator(".schema-container form")).toBeVisible();
  await expect(page.locator("#sd-tagger-dock")).toBeVisible();
  await expect(page.locator("[data-start-btn]")).toBeVisible();
});
