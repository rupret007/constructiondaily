import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("sign in and create a preconstruction plan set", async ({ page }) => {
  const planSetName = `E2E Smoke ${Date.now()}`;

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByLabel("Username").fill("e2e_pm");
  await page.getByLabel("Password").fill("e2e-pass-123");
  await page.getByRole("button", { name: "Login" }).click();

  await expect(page.getByRole("heading", { name: "Construction Daily Report" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Daily Reports" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Preconstruction" })).toBeVisible();

  await page.getByRole("button", { name: "Preconstruction" }).click();
  await expect(page.getByRole("heading", { name: "Preconstruction" })).toBeVisible();

  await page.getByRole("button", { name: "Create plan set" }).click();
  await page.getByLabel("Plan set name").fill(planSetName);
  await page.getByRole("button", { name: "Create", exact: true }).click();

  await expect(page.getByText(planSetName)).toBeVisible();
  await expect(page.getByText("Select a plan set to view and upload sheets.")).toBeVisible();
});

test("preconstruction: upload sheet, open viewer, run analysis, copilot, snapshot and export", async ({
  page,
}) => {
  const planSetName = `E2E Precon ${Date.now()}`;
  const minimalPdf = path.join(__dirname, "fixtures", "minimal.pdf");

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByLabel("Username").fill("e2e_pm");
  await page.getByLabel("Password").fill("e2e-pass-123");
  await page.getByRole("button", { name: "Login" }).click();
  await expect(page.getByRole("heading", { name: "Construction Daily Report" })).toBeVisible();

  await page.getByRole("button", { name: "Preconstruction" }).click();
  await expect(page.getByRole("heading", { name: "Preconstruction" })).toBeVisible();

  await page.getByRole("button", { name: "Create plan set" }).click();
  await page.getByLabel("Plan set name").fill(planSetName);
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByText(planSetName)).toBeVisible();
  await page.getByText(planSetName).click();
  const fileInput = page.getByLabel("Upload plan file");
  await fileInput.setInputFiles(minimalPdf);
  await expect(page.getByRole("button", { name: "Open", exact: true })).toBeVisible({ timeout: 15000 });
  await page.getByRole("button", { name: "Open", exact: true }).first().click();

  await expect(page.getByLabel("Analysis prompt")).toBeVisible({ timeout: 10000 });
  await page.getByLabel("Analysis prompt").fill("doors");
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page.getByText(/Running\.\.\.|Pending:|Accepted:/)).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/Pending:|Accepted:|Rejected:|Edited:/)).toBeVisible({ timeout: 20000 });

  const batchBtn = page.getByRole("button", { name: "Accept all high-confidence (>=85%)" });
  if (await batchBtn.isEnabled()) {
    await batchBtn.click();
    await expect(page.getByRole("button", { name: "Accepting..." })).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole("button", { name: "Accepting..." })).toBeHidden({ timeout: 15000 });
  }

  await page.getByLabel("Ask sheet copilot").fill("how many doors pending?");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sheet copilot" }).locator("..").getByText(/\d+|pending|takeoff|door/i).first(),
  ).toBeVisible({ timeout: 15000 });

  await page.getByRole("button", { name: "Create snapshot", exact: true }).click();
  await expect(page.getByText(/Snapshot \d{4}-\d{2}-\d{2}|Draft/)).toBeVisible({ timeout: 10000 });

  await page.getByRole("button", { name: "Export JSON", exact: true }).click();
  await expect(page.getByText(/plan_set_id|sheets|captured_at/).first()).toBeVisible({ timeout: 10000 });
});
