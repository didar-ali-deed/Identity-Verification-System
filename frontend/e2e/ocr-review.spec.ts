import { expect, test } from "@playwright/test";

test("ambiguous OCR names require review while differently formatted DOBs match", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("access_token", "synthetic-token"));
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown;
    if (path.endsWith("/auth/me")) data = { id: "user", role: "user", full_name: "Alex Ili", email: "alex@example.com" };
    else if (path.endsWith("/idv/status")) data = { id: "app", status: "pending", documents: [{ id: "passport", doc_type: "passport" }, { id: "id-card", doc_type: "national_id" }] };
    else if (path.includes("/idv/document/")) {
      const passport = path.endsWith("/passport");
      data = { ocr_ready: true, extracted_fields: { full_name: passport ? "ALEX ILL" : "ALEX ILI", dob: passport ? "01 JAN 1990" : "01.01.1990", nationality: passport ? "PAKISTANI" : "Pakistan", gender: "Male", expiry_date: passport ? "01 JAN 2034" : "06.10.2035" } };
    } else throw new Error(`Unexpected API request: ${path}`);
    await route.fulfill({ json: data });
  });
  await page.goto("/idv");
  await expect(page.getByRole("row").filter({ hasText: "Full Name" }).getByText("Check OCR", { exact: true })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "Date of Birth" }).getByText("Match", { exact: true })).toBeVisible();
  await expect(page.getByText(/this is not a verified match/)).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "Nationality / Country of Stay" }).getByText("Not compared", { exact: true })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "Expiry Date" }).getByText("Valid", { exact: true })).toBeVisible();
  await expect(page.getByText("Mismatch", { exact: true })).toHaveCount(0);
});
