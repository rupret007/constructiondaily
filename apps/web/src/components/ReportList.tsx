import { useState } from "react";
import type { DailyReport, Project } from "../types/api";

type Props = {
  projects: Project[];
  reports: DailyReport[];
  selectedProjectId: string;
  onProjectChange: (projectId: string) => void;
  onCreateReport: (payload: Partial<DailyReport>) => Promise<void>;
  onSelectReport: (reportId: string) => void;
};

export function ReportList({
  projects,
  reports,
  selectedProjectId,
  onProjectChange,
  onCreateReport,
  onSelectReport
}: Props) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const canCreateReport = Boolean(selectedProject);

  return (
    <section className="card">
      <h2>Daily Reports</h2>
      <div className="row">
        <select value={selectedProjectId} onChange={(event) => onProjectChange(event.target.value)}>
          {projects.map((project) => (
            <option value={project.id} key={project.id}>
              {project.code} - {project.name}
            </option>
          ))}
        </select>
        <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        <button
          disabled={!canCreateReport}
          onClick={() => {
            if (!selectedProject) return;
            void onCreateReport({
              project: selectedProject.id,
              report_date: date,
              location: selectedProject.location,
              summary: ""
            });
          }}
        >
          New Report
        </button>
      </div>
      {!canCreateReport && <p className="error-text">Select a project before creating a report.</p>}
      <div className="report-list">
        {reports.map((report) => (
          <button key={report.id} className="report-row" onClick={() => onSelectReport(report.id)}>
            <span>{report.report_date}</span>
            <span>{report.status}</span>
            <span>rev {report.revision}</span>
          </button>
        ))}
        {reports.length === 0 && <p>No reports yet for this project and date range.</p>}
      </div>
    </section>
  );
}
