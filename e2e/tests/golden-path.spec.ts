/** Golden path per Implementation Plan §24: patient login → upload → doctor
 * request → patient approval → authorized doctor view/download → revoke →
 * doctor denied (403, no bytes) → denial visible in patient audit history. */
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import fs from "fs";

const BE = "http://localhost:8000/api/v1";
const ADMIN = { email: "system-admin@example.com", password: "SystemAdmin#2026" };
const run = `e2e${Date.now()}`;
const patient = { email: `p-${run}@example.com`, password: "TestPass#123", name: "Pat E2E" };
const doctor = { email: `d-${run}@example.com`, password: "TestPass#123", name: "Doc E2E" };
const recordTitle = `E2E Blood Panel ${run}`;

const PDF = Buffer.from(
  "%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n" + "A".repeat(256),
  "utf-8",
);

async function apiLogin(request: APIRequestContext, email: string, password: string) {
  const res = await request.post(`${BE}/auth/login`, { data: { email, password } });
  expect(res.status(), `login ${email}`).toBe(200);
  return (await res.json()).access_token as string;
}

async function adminFindUsers(request: APIRequestContext) {
  const token = await apiLogin(request, ADMIN.email, ADMIN.password);
  const res = await request.get(`${BE}/admin/users`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return (await res.json()) as { id: number; email: string; role: string }[];
}

async function logout(page: Page) {
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login/);
}

async function registerViaUI(page: Page, role: "Patient" | "Doctor",
  name: string, email: string, password: string) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByLabel("I am a").selectOption({ label: role });
  await page.getByRole("button", { name: "Create account" }).click();
}

test("golden path: upload → request → approve → bind → access → revoke → denied+audit",
  async ({ page, request }) => {
    // 1) Patient registers → lands on patient dashboard
    await registerViaUI(page, "Patient", patient.name, patient.email, patient.password);
    await expect(page.getByRole("heading", { name: "Your health dashboard" })).toBeVisible();
    await logout(page);

    // 2) Doctor registers → lands on doctor workspace
    await registerViaUI(page, "Doctor", doctor.name, doctor.email, doctor.password);
    await expect(page.getByRole("heading", { name: "Doctor workspace" })).toBeVisible();
    await logout(page);

    // 3) Patient creates a record (success only after server confirmation)
    await page.goto("/login");
    await page.getByLabel("Email").fill(patient.email);
    await page.getByLabel("Password").fill(patient.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Your health dashboard" })).toBeVisible();
    await page.goto("/patient/records");
    await page.getByPlaceholder("e.g. Annual blood panel").fill(recordTitle);
    await page.getByRole("button", { name: "Create" }).click();
    await expect(page.getByText("Record created.")).toBeVisible();

    // 4) Upload a valid PDF into the record
    await page.getByRole("link", { name: new RegExp(recordTitle) }).click();
    await page.locator('input[type="file"]').setInputFiles({
      name: "report.pdf", mimeType: "application/pdf", buffer: PDF,
    });
    await page.getByRole("button", { name: "Upload" }).click();
    await expect(page.getByText("Report stored securely.")).toBeVisible();
    await expect(page.getByText(/Protected file #\d+/)).toBeVisible();

    // 5) Look up ids via admin API (realistic directory lookup)
    const users = await adminFindUsers(request);
    const patientId = users.find((u) => u.email === patient.email)!.id;
    const doctorId = users.find((u) => u.email === doctor.email)!.id;
    const token = await apiLogin(request, patient.email, patient.password);
    const records = await (await request.get(`${BE}/records`, {
      headers: { Authorization: `Bearer ${token}` },
    })).json();
    const recordId = records.find((r: { title: string }) => r.title === recordTitle).id as number;

    // 6) Doctor sends an access request (PENDING never grants access)
    await logout(page);
    await page.goto("/login");
    await page.getByLabel("Email").fill(doctor.email);
    await page.getByLabel("Password").fill(doctor.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Doctor workspace" })).toBeVisible();
    await page.getByLabel("Patient ID").fill(String(patientId));
    await page.getByLabel(/Record ID/).fill(String(recordId));
    await page.getByLabel("Purpose").fill("E2E second opinion");
    await page.getByRole("button", { name: "Send request" }).click();
    await expect(page.getByText(/Request sent/)).toBeVisible();
    await expect(page.getByText("PENDING").first()).toBeVisible();
    // No authorized records while pending
    await expect(page.getByText("No authorized records.")).toBeVisible();
    await logout(page);

    // 7) Patient approves with a 30-day window
    await page.goto("/login");
    await page.getByLabel("Email").fill(patient.email);
    await page.getByLabel("Password").fill(patient.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.goto("/patient/privacy");
    await page.getByLabel("Access duration").selectOption("30");
    await page.getByRole("button", { name: "Approve" }).click();
    await expect(page.getByText(/Permission granted/)).toBeVisible();
    await expect(
      page.locator("li").filter({ hasText: `Doctor #${doctorId}` }).filter({ hasText: "ACTIVE" }),
    ).toHaveCount(1);
    await logout(page);

    // 8) System admin binds the institutional care relationship
    await page.goto("/login");
    await page.getByLabel("Email").fill(ADMIN.email);
    await page.getByLabel("Password").fill(ADMIN.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.getByLabel("Patient ID").fill(String(patientId));
    await page.getByLabel("Doctor ID").fill(String(doctorId));
    await page.getByRole("button", { name: "Bind", exact: true }).click();
    await expect(page.getByText(/Care relationship bound/)).toBeVisible();
    await logout(page);

    // 9) Doctor now sees the authorized record and downloads the file
    await page.goto("/login");
    await page.getByLabel("Email").fill(doctor.email);
    await page.getByLabel("Password").fill(doctor.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Doctor workspace" })).toBeVisible();
    await expect(page.getByText(recordTitle)).toBeVisible();
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Download" }).first().click(),
    ]);
    const dlPath = await download.path();
    expect(fs.statSync(dlPath!).size).toBeGreaterThan(100);

    // 10) Patient revokes — immediate block on the next protected request
    await logout(page);
    await page.goto("/login");
    await page.getByLabel("Email").fill(patient.email);
    await page.getByLabel("Password").fill(patient.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Your health dashboard" })).toBeVisible();
    await page.goto("/patient/privacy");
    const row = page.locator("li").filter({ hasText: `Doctor #${doctorId}` }).filter({ hasText: "ACTIVE" });
    await row.getByRole("button", { name: "Revoke", exact: true }).click();
    await row.getByRole("button", { name: "Confirm revoke?" }).click();
    await expect(page.getByText(/Permission revoked/)).toBeVisible();
    await expect(
      page.locator("li").filter({ hasText: `Doctor #${doctorId}` }).filter({ hasText: "REVOKED" }),
    ).toHaveCount(1);
    await logout(page);

    // 11) Doctor retry → controlled 403, no medical bytes returned
    const dToken = await apiLogin(request, doctor.email, doctor.password);
    const denied = await request.get(`${BE}/records/${recordId}`, {
      headers: { Authorization: `Bearer ${dToken}` },
    });
    expect(denied.status()).toBe(403);

    // 12) Denial is visible in the patient's access history (audited like grants)
    await page.goto("/login");
    await page.getByLabel("Email").fill(patient.email);
    await page.getByLabel("Password").fill(patient.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Your health dashboard" })).toBeVisible();
    await page.goto("/patient/history");
    await expect(
      page.locator("tr").filter({ hasText: "RECORD_ACCESS" }).filter({ hasText: "REJECTED" }),
    ).toHaveCount(1);
  });
