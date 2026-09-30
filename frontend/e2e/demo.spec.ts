import { expect, test } from "@playwright/test";

test("public demo explains all four outcomes without a backend", async ({ page }) => {
  const errors: string[] = [];
  const apiRequests: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => { if (new URL(request.url()).pathname.startsWith("/api/v1/")) apiRequests.push(request.url()); });
  await page.goto("/demo");
  await expect(page.getByRole("heading", { name: "Every decision has evidence." })).toBeVisible();
  const evidence = page.getByRole("region", { name: "Verification evidence" });
  await expect(evidence.getByText("APPROVED", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: /OCR needs review/ }).click();
  await expect(evidence.getByText("MANUAL REVIEW", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Identity mismatch/ }).click();
  await expect(evidence.getByText("REJECTED", { exact: true }).first()).toBeVisible();
  await expect(evidence.getByText("ID_MISMATCH", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Liveness unavailable/ }).click();
  await expect(evidence.getByText("REJECTED", { exact: true }).first()).toBeVisible();
  await expect(evidence.getByText("SELFIE_LIVENESS_FAIL", { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
  expect(apiRequests).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("evidence expands and demo is reachable from login", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("link", { name: "Explore the synthetic demo" }).click();
  const stage = page.getByRole("button", { name: /Liveness & Anti-Spoofing/ });
  await stage.click();
  await expect(stage).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText(/"frame_scores"/)).toBeVisible();
});

test("phone camera submits three frames and stops after success", async ({ page }) => {
  let frameCount = 0;
  await page.route("**/api/v1/idv/mobile-upload/synthetic-token", async route => {
    const body = route.request().postData() ?? "";
    frameCount = (body.match(/name="frames"/g) ?? []).length + (body.includes('name="file"') ? 1 : 0);
    await route.fulfill({ json: { id: "synthetic" } });
  });
  await page.goto("/m/synthetic-token");
  await page.getByRole("button", { name: "Enable camera" }).click();
  await page.getByRole("button", { name: "Capture frames" }).click();
  await page.getByRole("button", { name: "Submit three frames" }).click();
  await expect(page.getByRole("heading", { name: "Frames received" })).toBeVisible();
  expect(frameCount).toBe(3);
  await expect(page.locator("video")).toHaveCount(0);
});
