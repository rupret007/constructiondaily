import { expect, test } from "@playwright/test";

async function login(page, username: string) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill("e2e-pass-123");
  await page.getByRole("button", { name: "Login" }).click();
  await expect(page.getByRole("heading", { name: "Construction Daily Report" })).toBeVisible();
}

async function logout(page) {
  await page.getByRole("button", { name: "Logout" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
}

async function createDraftReport(page, reportDate: string) {
  await page.locator('input[type="date"]').fill(reportDate);
  await page.getByRole("button", { name: "New Report" }).click();
  await expect(page.getByRole("button", { name: new RegExp(reportDate) })).toBeVisible();
  await page.getByRole("button", { name: new RegExp(reportDate) }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`Report ${reportDate} - draft`) })).toBeVisible();
}

test("daily report workflow moves through create submit review approve and lock", async ({ page }) => {
  const reportDate = "2026-03-10";

  await login(page, "e2e_super");
  await createDraftReport(page, reportDate);

  await page.getByLabel("Location").fill("Gate 3");
  await page.getByLabel("Summary").fill("Concrete forms were set and inspected.");
  await page.getByRole("button", { name: "Save" }).click();

  await expect(page.getByRole("button", { name: new RegExp(`${reportDate}.*rev 2`) })).toBeVisible();
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`Report ${reportDate} - submitted`) })).toBeVisible();
  await logout(page);

  await login(page, "e2e_pm");
  await page.getByRole("button", { name: new RegExp(reportDate) }).click();
  await page.getByRole("button", { name: "Review" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`Report ${reportDate} - reviewed`) })).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`Report ${reportDate} - approved`) })).toBeVisible();
  await logout(page);

  await login(page, "e2e_admin");
  await page.getByRole("button", { name: new RegExp(reportDate) }).click();
  await page.getByRole("button", { name: "Lock" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`Report ${reportDate} - locked`) })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
  await expect(page.getByText(/read-only/i)).toBeVisible();
});

test("review rejection returns report to draft and re-enables editing", async ({ page }) => {
  const reportDate = "2026-03-11";

  await login(page, "e2e_super");
  await createDraftReport(page, reportDate);
  await page.getByLabel("Summary").fill("Rough-in inspections pending.");
  await page.getByRole("button", { name: "Submit" }).click();
  await logout(page);

  await login(page, "e2e_pm");
  await page.getByRole("button", { name: new RegExp(reportDate) }).click();
  await page.getByLabel("Rejection reason").fill("Need labor detail before approval.");
  await page.getByRole("button", { name: "Reject" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`Report ${reportDate} - draft`) })).toBeVisible();
  await expect(page.getByText(/Need labor detail before approval\./)).toBeVisible();
  await expect(page.getByRole("button", { name: "Save" })).toBeEnabled();
});

test("stale draft save shows a conflict instead of overwriting newer server state", async ({ page }) => {
  const reportDate = "2026-03-12";

  await login(page, "e2e_super");
  await createDraftReport(page, reportDate);

  const reportId = await page.evaluate(async (date) => {
    const sessionProjects = await fetch("/api/projects/", { credentials: "include" });
    const projects = (await sessionProjects.json()) as Array<{ id: string }>;
    const reportsResponse = await fetch(`/api/reports/daily/?project=${projects[0].id}`, {
      credentials: "include",
    });
    const reports = (await reportsResponse.json()) as Array<{ id: string; report_date: string; revision: number }>;
    return reports.find((report) => report.report_date === date)?.id ?? "";
  }, reportDate);

  expect(reportId).not.toBe("");

  const externalPatch = await page.evaluate(async ({ id }) => {
    const csrfToken =
      document.cookie
        .split("; ")
        .find((item) => item.startsWith("csrftoken="))
        ?.split("=")[1] ?? "";
    const response = await fetch(`/api/reports/daily/${id}/`, {
      method: "PATCH",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": decodeURIComponent(csrfToken),
      },
      body: JSON.stringify({
        summary: "External update",
        revision: 1,
      }),
    });
    return {
      status: response.status,
      body: await response.json(),
    };
  }, { id: reportId });

  expect(externalPatch.status).toBe(200);

  await page.getByLabel("Summary").fill("Browser edit with stale revision");
  await page.getByRole("button", { name: "Save" }).click();

  await expect(page.getByText("Report has changed. Refresh and manually resolve conflicts.")).toBeVisible();
});
