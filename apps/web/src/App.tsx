import { useEffect, useState } from "react";
import { LoginForm } from "./components/LoginForm";
import { NavBar } from "./components/NavBar";
import { OfflineBadge } from "./components/OfflineBadge";
import { ReportDetail } from "./components/ReportDetail";
import { ReportList } from "./components/ReportList";
import { useOfflineSync } from "./hooks/useOfflineSync";
import { enqueueMutation } from "./offline/queue";
import { getSession, login, logout } from "./services/auth";
import { fetchProjects } from "./services/projects";
import { createReport, fetchReport, fetchReports, syncWeather, transitionReport, updateReport } from "./services/reports";
import type { ApiUser, DailyReport, Project } from "./types/api";

function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export default function App() {
  const [user, setUser] = useState<ApiUser | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [reports, setReports] = useState<DailyReport[]>([]);
  const [selectedReport, setSelectedReport] = useState<DailyReport | null>(null);
  const [error, setError] = useState("");
  const { isOnline, lastFlushedCount, queuedCount } = useOfflineSync();

  async function loadSessionAndProjects() {
    const session = await getSession();
    if (!session.authenticated || !session.user) {
      setUser(null);
      setProjects([]);
      setReports([]);
      setSelectedProjectId("");
      setSelectedReport(null);
      return;
    }
    setUser(session.user);
    const projectList = await fetchProjects();
    setProjects(projectList);
    if (projectList.length === 0) {
      setSelectedProjectId("");
      setReports([]);
      setSelectedReport(null);
      setError("No projects are assigned to your account. Contact an admin.");
      return;
    }
    const hasSelectedProject = projectList.some((project) => project.id === selectedProjectId);
    const id = hasSelectedProject ? selectedProjectId : projectList[0].id;
    setSelectedProjectId(id);
    setError("");
  }

  async function loadReports(projectId: string) {
    if (!projectId) {
      setReports([]);
      setSelectedReport(null);
      return;
    }
    const reportList = await fetchReports(projectId);
    setReports(reportList);
    if (selectedReport && !reportList.some((report) => report.id === selectedReport.id)) {
      setSelectedReport(null);
    }
  }

  useEffect(() => {
    void loadSessionAndProjects().catch((err) => {
      setError(getErrorMessage(err, "Failed to load session."));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    void loadReports(selectedProjectId).catch((err) => {
      setError(getErrorMessage(err, "Failed to load reports."));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId, lastFlushedCount]);

  async function refreshSelectedReport(reportId: string) {
    const report = await fetchReport(reportId);
    setSelectedReport(report);
    await loadReports(report.project);
  }

  async function executeOnlineOrQueue(
    method: "POST" | "PATCH",
    endpoint: string,
    payload: Record<string, unknown>,
    onlineAction: () => Promise<void>
  ) {
    if (isOnline) {
      await onlineAction();
      return;
    }
    await enqueueMutation({ method, endpoint, payload });
  }

  if (!user) {
    return (
      <main className="container">
        <LoginForm
          onSubmit={async (username, password) => {
            await login(username, password);
            await loadSessionAndProjects();
          }}
        />
      </main>
    );
  }

  return (
    <main className="container">
      <NavBar
        user={user}
        onLogout={() => {
          void logout().finally(() => {
            setUser(null);
            setProjects([]);
            setReports([]);
            setSelectedProjectId("");
            setSelectedReport(null);
            setError("");
          });
        }}
      />
      <OfflineBadge isOnline={isOnline} lastFlushedCount={lastFlushedCount} queuedCount={queuedCount} />
      {error && <p className="error-text">{error}</p>}
      <div className="layout">
        <ReportList
          projects={projects}
          selectedProjectId={selectedProjectId}
          onProjectChange={(projectId) => {
            setSelectedProjectId(projectId);
            setSelectedReport(null);
            setError("");
          }}
          reports={reports}
          onCreateReport={async (payload) => {
            setError("");
            try {
              await executeOnlineOrQueue("POST", "/reports/daily/", payload as Record<string, unknown>, async () => {
                await createReport(payload);
              });
              if (isOnline) {
                await loadReports(selectedProjectId);
              }
            } catch (err) {
              setError(getErrorMessage(err, "Failed to create report."));
            }
          }}
          onSelectReport={(reportId) => {
            setError("");
            void refreshSelectedReport(reportId).catch((err) => {
              setError(getErrorMessage(err, "Failed to load selected report."));
            });
          }}
        />
        <ReportDetail
          report={selectedReport}
          onSave={async (payload) => {
            if (!selectedReport) return;
            setError("");
            try {
              await executeOnlineOrQueue(
                "PATCH",
                `/reports/daily/${selectedReport.id}/`,
                { ...payload, revision: selectedReport.revision } as Record<string, unknown>,
                async () => {
                  await updateReport(selectedReport.id, { ...payload, revision: selectedReport.revision });
                }
              );
              if (isOnline) {
                await refreshSelectedReport(selectedReport.id);
              }
            } catch (err) {
              setError(getErrorMessage(err, "Failed to save report changes."));
            }
          }}
          onAction={async (action, reason) => {
            if (!selectedReport) return;
            setError("");
            try {
              await executeOnlineOrQueue(
                "POST",
                `/reports/daily/${selectedReport.id}/${action}/`,
                { reason: reason ?? "", revision: selectedReport.revision },
                async () => {
                  await transitionReport(selectedReport.id, action, reason ?? "");
                }
              );
              if (isOnline) {
                await refreshSelectedReport(selectedReport.id);
              }
            } catch (err) {
              setError(getErrorMessage(err, "Failed to update report status."));
            }
          }}
          onSyncWeather={async () => {
            if (!selectedReport) return;
            setError("");
            try {
              await syncWeather(selectedReport.id);
              await refreshSelectedReport(selectedReport.id);
            } catch (err) {
              setError(getErrorMessage(err, "Failed to sync weather."));
            }
          }}
        />
      </div>
    </main>
  );
}
