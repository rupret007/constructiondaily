import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReportDetail } from "./ReportDetail";
import type { DailyReport } from "../types/api";

function makeReport(overrides: Partial<DailyReport> = {}): DailyReport {
  return {
    id: "report-1",
    project: "project-1",
    report_date: "2026-03-12",
    location: "Site A",
    status: "submitted",
    summary: "",
    weather_source: "",
    weather_summary: "",
    temperature_high_c: null,
    temperature_low_c: null,
    precipitation_mm: null,
    wind_max_kph: null,
    rejection_reason: "",
    revision: 1,
    ...overrides,
  };
}

describe("ReportDetail reject action", () => {
  it("requires a non-empty reason before enabling Reject", async () => {
    render(
      <ReportDetail
        report={makeReport()}
        onSave={async () => {}}
        onAction={async () => {}}
        onSyncWeather={async () => {}}
      />
    );

    const rejectButton = screen.getByRole("button", { name: /reject/i });
    expect(rejectButton).toBeDisabled();

    await userEvent.type(screen.getByLabelText(/rejection reason/i), "Missing signature details");
    expect(rejectButton).toBeEnabled();
  });

  it("keeps Reject disabled when status cannot be rejected", async () => {
    render(
      <ReportDetail
        report={makeReport({ status: "draft" })}
        onSave={async () => {}}
        onAction={vi.fn()}
        onSyncWeather={async () => {}}
      />
    );

    const rejectButton = screen.getByRole("button", { name: /reject/i });
    await userEvent.type(screen.getByLabelText(/rejection reason/i), "Reason present");
    expect(rejectButton).toBeDisabled();
  });
});
