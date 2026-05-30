import { expect, test } from "@playwright/test";

const shellRoutes = [
  "/",
  "/other/settings.html",
  "/tageditor.html",
  "/lora/sd3.html",
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
  "/",
  "/tageditor.html",
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

for (const route of ["/lora/index.html", "/lora/master.html", "/lora/flux.html", "/tensorboard.html", "/task.html"]) {
  test(`source compatibility page has product-grade scaffolding ${route}`, async ({ page }) => {
    await page.goto(route);
    await expect(page.locator(".source-static-page")).toBeVisible();
    await expect(page.locator(".source-static-grid")).toBeVisible();
    await expect(page.locator(".source-static-card")).toHaveCount(3);
    await expect(page.locator(".source-static-status")).toBeVisible();
    await expect(page.locator(".source-static-meta")).toBeVisible();
  });
}

test("lora source index exposes training route hub", async ({ page }) => {
  await page.goto("/lora/index.html");
  await expect(page.locator(".source-route-list")).toBeVisible();
  await expect(page.locator(".source-route-card")).toHaveCount(6);
  await expect(page.locator('.source-route-card[href="/lora/sd3.html"]')).toContainText("Anima Stable Diffusion LoRA");
  await expect(page.locator('.source-route-card[href="/lora/anima-finetune.html"]')).toContainText("全量微调");
  await expect(page.locator('.source-route-card[href="/lora/master.html"]')).toContainText("Stable Diffusion");
  await expect(page.locator('.source-route-card[href="/lora/flux.html"]')).toContainText("Flux LoRA");
  await expect(page.locator('.source-route-card[href="/dreambooth/index.html"]')).toContainText("Dreambooth");
});

test("tools source page exposes tool route hub", async ({ page }) => {
  await page.goto("/lora/tools.html");
  await expect(page.locator(".source-route-list")).toBeVisible();
  await expect(page.locator(".source-route-card")).toHaveCount(6);
  await expect(page.locator('.source-route-card[href="/tagger.html"]')).toBeVisible();
  await expect(page.locator('.source-route-card[href="/tageditor.html"]')).toBeVisible();
  await expect(page.locator('.source-route-card[href="/native-tageditor.html"]')).toBeVisible();
  await expect(page.locator('.source-route-card[href="/dataset-editor.html"]')).toBeVisible();
  await expect(page.locator('.source-route-card[href="/tensorboard.html"]')).toBeVisible();
  await expect(page.locator('.source-route-card[href="/task.html"]')).toBeVisible();
});

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
  await expect(page.locator("#anima-clip-skip")).toHaveAttribute("type", "range");
  await expect(page.locator("#anima-clip-skip-value")).toContainText("2");
  await page.locator("#anima-train-data-dir").locator("..").getByRole("button", { name: "Browse" }).click();
  await expect(page.locator(".anima-status")).toContainText("Browse requested for train_data_dir");
  await expect(page.getByRole("button", { name: "Reset Config" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Export Config" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Import Config" })).toBeVisible();
});

test("anima source route keeps document scrolling enabled", async ({ page }) => {
  await page.goto("/lora/sd3.html");
  await expect(page.locator("#anima-train-form")).toBeVisible();

  await expect
    .poll(() => page.evaluate(() => getComputedStyle(document.body).overflowY))
    .not.toBe("hidden");

  const before = await page.evaluate(() => window.scrollY);
  await page.evaluate(() => window.scrollTo(0, 900));
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(before);
});

test("anima lora source route loads adapter schema", async ({ page }) => {
  await page.goto("/lora/sd3.html");
  await expect(page.locator("#app")).toBeVisible();
  await expect(page.locator("#anima-train-form")).toBeVisible();
  await expect(page.locator("#anima-preview-code")).toContainText('model_train_type = "anima-lora"');
  await expect(page.locator("#anima-lora-type")).toBeVisible();
  await expect(page.locator("#anima-network-weights")).toBeVisible();
  await expect(page.locator("#anima-network-args-custom")).toBeVisible();
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
