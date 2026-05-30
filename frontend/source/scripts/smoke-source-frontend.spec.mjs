import { expect, test } from "@playwright/test";

const shellRoutes = [
  "/",
  "/other/settings.html",
  "/lora/anima-finetune.html",
  "/lora/index.html",
  "/lora/basic.html",
  "/lora/master.html",
  "/lora/flux.html",
  "/dreambooth/index.html",
  "/lora/params.html",
  "/tensorboard.html",
  "/lora/tools.html",
  "/task.html",
  "/help/guide.html",
  "/other/about.html",
  "/other/changelog.html",
  "/missing-route",
];

for (const route of shellRoutes) {
  test(`source shell loads ${route}`, async ({ page }) => {
    await page.goto(route);
    await expect(page.locator("#app")).toBeVisible();
    await expect(page.locator(".sidebar")).toBeVisible();
  });
}

for (const route of [
  "/tensorboard.html",
  "/lora/tools.html",
  "/task.html",
  "/help/guide.html",
  "/other/about.html",
  "/other/changelog.html",
]) {
  test(`source utility page has owned content ${route}`, async ({ page }) => {
    await page.goto(route);
    await expect(page.locator("#app")).toBeVisible();
    await expect(page.locator(".source-static-page")).toBeVisible();
    await expect(page.locator(".source-static-actions")).toBeVisible();
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

test("anima source route loads train form", async ({ page }) => {
  await page.goto("/lora/anima-finetune.html");
  await expect(page.locator("#app")).toBeVisible();
  await expect(page.locator("#anima-train-form")).toBeVisible();
  await expect(page.locator("#anima-pretrained-model")).toBeVisible();
  await expect(page.locator("#anima-train-data-dir")).toBeVisible();
  await expect(page.locator("[data-training-role='file']")).toHaveCount(4);
  await expect(page.locator("[data-training-role='folder']")).toHaveCount(4);
  await expect(page.locator(".anima-preview-panel")).toBeVisible();
  await expect(page.locator("#anima-preview-code")).toContainText('model_train_type = "anima-finetune"');
  await expect(page.locator("#anima-sample-sampler")).toBeVisible();
  await expect(page.locator("#anima-fp8-base")).toBeVisible();
  await expect(page.getByRole("button", { name: "Reset Config" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Export Config" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Import Config" })).toBeVisible();
});

test("anima schema visibility and table controls work", async ({ page }) => {
  await page.goto("/lora/anima-finetune.html");
  await expect(page.locator("#anima-positive-prompts")).toBeVisible();
  await page.locator("#anima-enable-preview").uncheck();
  await expect(page.locator("#anima-positive-prompts")).toHaveCount(0);

  await expect(page.locator("#anima-logit-mean")).toHaveCount(0);
  await page.locator("#anima-weighting-scheme").selectOption("logit_normal");
  await expect(page.locator("#anima-logit-mean")).toBeVisible();

  await page.locator("#anima-optimizer-args-custom").getByRole("button", { name: "Add Row" }).click();
  await expect(page.locator("#anima-optimizer-args-custom-0")).toBeVisible();
  await page.locator("#anima-optimizer-args-custom-0").fill("weight_decay=0.01");
  await expect(page.locator("#anima-preview-code")).toContainText('optimizer_args_custom = ["weight_decay=0.01"]');
});
