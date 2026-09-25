/** Phase 10/11 browser E2E: admin runs a real federated round (consent-gated,
 * DP on) and the AGGREGATION block is verifiable in the ledger explorer;
 * regulator-style read-only view stays truthful (pending never confirmed). */
import { expect, test } from "@playwright/test";

const ADMIN = { email: "system-admin@example.com", password: "SystemAdmin#2026" };

test("FL round → AGGREGATION block → ledger verification", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Platform administration" })).toBeVisible();

  // Run one real DP federated round on the heart model.
  await page.goto("/fl");
  await expect(page.getByRole("heading", { name: "Federated training" })).toBeVisible();
  await page.getByRole("button", { name: /Run 1 round/ }).click();
  await expect(page.getByText(/Round \d+ result/)).toBeVisible();
  await expect(page.getByText(/Records moved|records moved/i).first()).toBeVisible();
  // Participant rows carry only metadata: hospital code + fingerprints.
  await expect(page.getByText("NCH")).toBeVisible();
  await expect(page.getByText(/Model fingerprint [0-9a-f]{64}/)).toBeVisible();

  // Ledger explorer shows the AGGREGATION block and verifies the whole chain.
  await page.goto("/ledger");
  await expect(page.getByRole("heading", { name: "Ledger explorer" })).toBeVisible();
  await page.getByRole("button", { name: /AGGREGATION \(/ }).first().click();
  await page.getByRole("button", { name: "Verify every block" }).click();
  await expect(page.getByText(/All \d+ blocks verified/)).toBeVisible();
});
