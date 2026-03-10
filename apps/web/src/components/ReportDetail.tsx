import { useEffect, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { DailyReport } from "../types/api";

type Props = {
  report: DailyReport | null;
  onSave: (payload: Partial<DailyReport>) => Promise<void>;
  onAction: (
    action: "submit" | "review" | "reject" | "approve" | "sign" | "lock",
    reason?: string
  ) => Promise<void>;
  onSyncWeather: () => Promise<void>;
};

const inputClasses =
  "flex h-11 min-h-[44px] w-full rounded-md border border-input bg-background px-3 py-2 text-base ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50";

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
      <Card>
        <CardHeader>
          <CardTitle>Report Details</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Select a report to view and edit details.
          </p>
        </CardContent>
      </Card>
    );
  }

  const canEdit = report.status !== "locked";

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Report {report.report_date} - {report.status}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <label htmlFor="report-location" className="text-sm font-medium text-foreground">
            Location
          </label>
          <Input
            id="report-location"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            disabled={!canEdit}
          />
        </div>
        <div className="space-y-2">
          <label htmlFor="report-summary" className="text-sm font-medium text-foreground">
            Summary
          </label>
          <textarea
            id="report-summary"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            rows={7}
            disabled={!canEdit}
            className={`${inputClasses} min-h-[120px] resize-y`}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={!canEdit}
            onClick={() =>
              void onSave({
                location,
                summary,
              })
            }
          >
            Save
          </Button>
          <Button variant="outline" disabled={!canEdit} onClick={() => void onSyncWeather()}>
            Sync Weather
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">
          Weather: {report.weather_summary || "No weather data"} {report.temperature_high_c ?? "-"} /{" "}
          {report.temperature_low_c ?? "-"} C, {report.precipitation_mm ?? "-"} mm rain
        </p>
        {!!report.rejection_reason && (
          <Alert variant="destructive">Rejection: {report.rejection_reason}</Alert>
        )}
        <div className="flex flex-wrap gap-2 pt-2">
          <Button
            size="sm"
            variant="secondary"
            disabled={report.status !== "draft"}
            onClick={() => void onAction("submit")}
          >
            Submit
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={report.status !== "submitted"}
            onClick={() => void onAction("review")}
          >
            Review
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={report.status !== "submitted" && report.status !== "reviewed"}
            onClick={() => void onAction("reject", reason)}
          >
            Reject
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={report.status !== "reviewed"}
            onClick={() => void onAction("approve")}
          >
            Approve
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={report.status !== "approved"}
            onClick={() => void onAction("sign")}
          >
            Sign
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={report.status !== "approved"}
            onClick={() => void onAction("lock")}
          >
            Lock
          </Button>
        </div>
        <div className="space-y-2">
          <label htmlFor="report-reason" className="text-sm font-medium text-foreground">
            Rejection reason (used for reject action)
          </label>
          <Input
            id="report-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
      </CardContent>
    </Card>
  );
}
