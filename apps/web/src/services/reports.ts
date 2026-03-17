import { apiRequest } from "./api";
import type { DailyReport } from "../types/api";

type PaginatedResponse<T> = {
  results?: T[];
};

export async function fetchReports(projectId: string): Promise<DailyReport[]> {
  const response = await apiRequest<DailyReport[] | PaginatedResponse<DailyReport>>(
    `/reports/daily/?project=${projectId}`
  );
  return Array.isArray(response) ? response : response.results ?? [];
}

export async function fetchReport(reportId: string): Promise<DailyReport> {
  return apiRequest<DailyReport>(`/reports/daily/${reportId}/`);
}

export async function createReport(payload: Partial<DailyReport>): Promise<DailyReport> {
  return apiRequest<DailyReport>("/reports/daily/", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateReport(reportId: string, payload: Partial<DailyReport>): Promise<DailyReport> {
  return apiRequest<DailyReport>(`/reports/daily/${reportId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function transitionReport(
  reportId: string,
  action: "submit" | "review" | "reject" | "approve" | "sign" | "lock",
  reason = "",
  revision?: number
): Promise<DailyReport> {
  return apiRequest<DailyReport>(`/reports/daily/${reportId}/${action}/`, {
    method: "POST",
    body: JSON.stringify({ reason, revision })
  });
}

export async function syncWeather(reportId: string): Promise<DailyReport> {
  return apiRequest<DailyReport>(`/reports/daily/${reportId}/sync-weather/`, {
    method: "POST",
    body: JSON.stringify({})
  });
}
