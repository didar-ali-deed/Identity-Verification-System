import { createRequire } from "node:module";
import { mkdirSync, copyFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(new URL("../frontend/package.json", import.meta.url));
const { chromium, devices } = require("@playwright/test");
const root = fileURLToPath(new URL("../", import.meta.url));
const output = path.join(root, "docs", "screenshots");
mkdirSync(output, { recursive: true });
const browser = await chromium.launch();
try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 }, reducedMotion: "reduce",
    recordVideo: { dir: path.join(root, "frontend", "test-results", "showcase"), size: { width: 1280, height: 978 } },
  });
  const page = await context.newPage();
  const url = process.env.SHOWCASE_URL ?? "http://127.0.0.1:5173/demo";
  await page.goto(url);
  await page.getByRole("heading", { name: "Every decision has evidence." }).waitFor();
  await page.screenshot({ path: path.join(output, "approved.png"), fullPage: true });
  await page.waitForTimeout(2000);
  for (const [name, image] of [["OCR needs review", "review"], ["Identity mismatch", "rejected"], ["Liveness unavailable", "unavailable"]]) {
    await page.getByRole("button", { name: new RegExp(name) }).click();
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(output, `${image}.png`), fullPage: true });
  }
  await page.getByRole("button", { name: /Liveness & Anti-Spoofing/ }).click();
  await page.waitForTimeout(2000);
  const video = page.video();
  await context.close();
  if (video) copyFileSync(await video.path(), path.join(root, "docs", "demo.webm"));
  const mobile = await browser.newContext({ ...devices["Pixel 7"], reducedMotion: "reduce" });
  const mobilePage = await mobile.newPage();
  await mobilePage.goto(url);
  await mobilePage.getByRole("heading", { name: "Every decision has evidence." }).waitFor();
  await mobilePage.screenshot({ path: path.join(output, "mobile.png"), fullPage: true });
  await mobile.close();
  console.log("Saved synthetic screenshots and docs/demo.webm");
} finally { await browser.close(); }
