import { expect, test } from "@playwright/test";

test("resume an application and replace unreadable passport evidence", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("access_token", "synthetic-token"));
  let passportId = "old-passport";
  let replaced = false;
  let reset = false;
  const fields = { full_name: "ALEX SAMPLE", dob: "19900101", nationality: "PAK", gender: "Male", expiry_date: "20300101" };
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    let data: unknown;
    if (url.pathname.endsWith("/auth/me")) {
      data = { id: "synthetic-user", full_name: "Alex Sample", email: "alex@example.com", role: "user", is_active: true };
    } else if (url.pathname.endsWith("/idv/status")) {
      data = { id: reset ? "fresh-app" : "synthetic-app", status: "pending", documents: reset ? [] : [{ id: passportId, doc_type: "passport" }, { id: "id-card", doc_type: "national_id" }] };
    } else if (url.pathname.includes("/idv/document/")) {
      const id = url.pathname.split("/").pop();
      data = { id, ocr_ready: true, extracted_fields: id === "old-passport" ? { ...fields, full_name: "-7 :" } : fields };
    } else if (url.pathname.endsWith("/idv/reset")) {
      expect(url.searchParams.get("application_id")).toBe("synthetic-app");
      reset = true;
      data = { id: "fresh-app", status: "pending", documents: [] };
    } else if (url.pathname.endsWith("/idv/upload-document")) {
      expect(url.searchParams.get("replace_existing")).toBe("true");
      passportId = "new-passport";
      replaced = true;
      data = { id: passportId, doc_type: "passport", application_id: "synthetic-app" };
    } else {
      throw new Error(`Unexpected API request: ${url.pathname}`);
    }
    await route.fulfill({ json: data });
  });
  await page.goto("/idv");
  await expect(page.getByRole("heading", { name: "Document Review" })).toBeVisible();
  await expect(page.getByText("-7 :", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/Missing OCR data is not an identity mismatch/)).toBeVisible();
  await page.getByRole("button", { name: "Replace passport", exact: true }).click();
  await page.locator('input[type="file"]').setInputFiles({ name: "synthetic.png", mimeType: "image/png", buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j0ZkAAAAASUVORK5CYII=", "base64") });
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Document Review" })).toBeVisible();
  await expect(page.getByText(/Missing OCR data is not an identity mismatch/)).toHaveCount(0);
  expect(replaced).toBe(true);
  page.once("dialog", dialog => dialog.dismiss());
  await page.getByRole("button", { name: "Reset verification", exact: true }).click();
  expect(reset).toBe(false);
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "Reset verification", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Upload Your Passport" })).toBeVisible();
  expect(reset).toBe(true);
});
