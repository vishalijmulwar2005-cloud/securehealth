/** Security-guard UI states: unauthenticated boundary, wrong-role boundary,
 * and client-side upload allowlist rejection. */
import { expect, test } from "@playwright/test";

const run = `guard${Date.now()}`;

test("unauthenticated /patient resolves to a controlled sign-in boundary", async ({ page }) => {
  await page.goto("/patient");
  await expect(page.getByRole("heading", { name: "Sign in required" })).toBeVisible();
  // No protected metadata leaks into the boundary state.
  await expect(page.getByText("E2E Blood Panel")).toHaveCount(0);
});

test("wrong role gets a controlled unavailable state (never the other portal)", async ({ page }) => {
  const email = `rp-${run}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Role Guard");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("TestPass#123");
  await page.getByLabel("I am a").selectOption({ label: "Patient" });
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Your health dashboard" })).toBeVisible();

  await page.goto("/doctor");
  await expect(page.getByText("Not available for your role")).toBeVisible();
  // Unauthorized deep links never reveal the doctor portal's content.
  await expect(page.getByText("Request access to patient records")).toHaveCount(0);
});

test("upload input rejects disallowed types before any server call", async ({ page }) => {
  const email = `up-${run}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Upload Guard");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("TestPass#123");
  await page.getByLabel("I am a").selectOption({ label: "Patient" });
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Your health dashboard" })).toBeVisible();

  await page.goto("/patient/records");
  await page.getByPlaceholder("e.g. Annual blood panel").fill(`Guard record ${run}`);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByText("Record created.")).toBeVisible();
  await page.getByRole("link", { name: new RegExp(`Guard record ${run}`) }).click();

  await page.locator('input[type="file"]').setInputFiles({
    name: "evil.exe", mimeType: "application/octet-stream", buffer: Buffer.from("MZ" + "x".repeat(64)),
  });
  await expect(page.getByText("Allowed types: PDF, PNG, JPEG, DICOM.")).toBeVisible();
  // Upload never became possible — no storage success is shown.
  await expect(page.getByText("Report stored securely.")).toHaveCount(0);
});
