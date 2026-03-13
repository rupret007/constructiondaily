import { expect, test } from "@playwright/test";

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
