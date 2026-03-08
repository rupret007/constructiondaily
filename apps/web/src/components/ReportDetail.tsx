import { useEffect, useState } from "react";
import type { DailyReport } from "../types/api";

type Props = {
  report: DailyReport | null;
  onSave: (payload: Partial<DailyReport>) => Promise<void>;
  onAction: (action: "submit" | "review" | "reject" | "approve" | "sign" | "lock", reason?: string) => Promise<void>;
  onSyncWeather: () => Promise<void>;
};

export function ReportDetail({ report, onSave, onAction, onSyncWeather }: Props) {
  const [summary, setSummary] = useState("");
  const [location, setLocation] = useState("");
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (!report) return;
    setSummary(report.summary ?? "");
    setLocation(report.location ?? "");
    setReason("");
  }, [report?.id, report?.summary, report?.location]);

  if (!report) {
    return (
      <section className="card">
        <h2>Report Details</h2>
        <p>Select a report to view and edit details.</p>
      </section>
    );
  }

  const canEdit = report.status !== "locked";

  return (
    <section className="card">
      <h2>
        Report {report.report_date} - {report.status}
      </h2>
      <label>
        Location
        <input value={location} onChange={(event) => setLocation(event.target.value)} disabled={!canEdit} />
      </label>
      <label>
        Summary
        <textarea value={summary} onChange={(event) => setSummary(event.target.value)} rows={7} disabled={!canEdit} />
      </label>
      <div className="row">
        <button
          disabled={!canEdit}
          onClick={() =>
            void onSave({
              location,
              summary
            })
          }
        >
          Save
        </button>
        <button disabled={!canEdit} onClick={() => void onSyncWeather()}>
          Sync Weather
        </button>
      </div>
      <p className="weather-line">
        Weather: {report.weather_summary || "No weather data"} {report.temperature_high_c ?? "-"} /{" "}
        {report.temperature_low_c ?? "-"} C, {report.precipitation_mm ?? "-"} mm rain
      </p>
      {!!report.rejection_reason && <p className="error-text">Rejection: {report.rejection_reason}</p>}
      <div className="row action-row">
        <button disabled={report.status !== "draft"} onClick={() => void onAction("submit")}>
          Submit
        </button>
        <button disabled={report.status !== "submitted"} onClick={() => void onAction("review")}>
          Review
        </button>
        <button disabled={report.status !== "submitted"} onClick={() => void onAction("reject", reason)}>
          Reject
        </button>
        <button disabled={report.status !== "reviewed"} onClick={() => void onAction("approve")}>
          Approve
        </button>
        <button disabled={report.status !== "approved"} onClick={() => void onAction("sign")}>
          Sign
        </button>
        <button disabled={report.status !== "approved"} onClick={() => void onAction("lock")}>
          Lock
        </button>
      </div>
      <label>
        Rejection reason (used for reject action)
        <input value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
    </section>
  );
}
