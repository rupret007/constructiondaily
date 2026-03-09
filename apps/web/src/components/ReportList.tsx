import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { DailyReport, Project } from "../types/api";

type Props = {
  projects: Project[];
  reports: DailyReport[];
  selectedProjectId: string;
  selectedReportId?: string;
  onProjectChange: (projectId: string) => void;
  onCreateReport: (payload: Partial<DailyReport>) => Promise<void>;
  onSelectReport: (reportId: string) => void;
};

export function ReportList({
  projects,
  reports,
  selectedProjectId,
  selectedReportId,
  onProjectChange,
  onCreateReport,
  onSelectReport,
}: Props) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const canCreateReport = Boolean(selectedProject);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Daily Reports</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={selectedProjectId}
            onChange={(e) => onProjectChange(e.target.value)}
            aria-label="Select project"
            className="flex h-11 min-h-[44px] flex-1 min-w-[200px] rounded-md border border-input bg-background px-3 py-2 text-base ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            {projects.map((project) => (
              <option value={project.id} key={project.id}>
                {project.code} — {project.name}
              </option>
            ))}
          </select>
          <Input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="min-w-[140px]"
          />
          <Button
            disabled={!canCreateReport}
            onClick={() => {
              if (!selectedProject) return;
              void onCreateReport({
                project: selectedProject.id,
                report_date: date,
                location: selectedProject.location,
                summary: "",
              });
            }}
          >
            New Report
          </Button>
        </div>
        {!canCreateReport && (
          <Alert variant="destructive">Select a project before creating a report.</Alert>
        )}
        <div className="flex flex-col gap-2">
          {reports.map((report) => (
            <Button
              key={report.id}
              type="button"
              variant={selectedReportId === report.id ? "default" : "outline"}
              className={cn(
                "h-auto min-h-11 justify-between py-3 text-left font-normal",
                "grid grid-cols-[1fr_auto_auto] gap-2",
                selectedReportId === report.id && "ring-2 ring-ring ring-offset-2"
              )}
              onClick={() => onSelectReport(report.id)}
            >
              <span>{report.report_date}</span>
              <span className="text-xs opacity-90">{report.status}</span>
              <span className="text-xs opacity-75">rev {report.revision}</span>
            </Button>
          ))}
          {reports.length === 0 && (
            <p className="py-4 text-sm text-muted-foreground">
              No reports yet for this project and date range.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
