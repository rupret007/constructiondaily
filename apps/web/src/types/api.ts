export type ApiUser = {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email?: string;
};

export type Project = {
  id: string;
  name: string;
  code: string;
  location: string;
  latitude: number | null;
  longitude: number | null;
  is_active: boolean;
};

export type DailyReport = {
  id: string;
  project: string;
  report_date: string;
  location: string;
  status: "draft" | "submitted" | "reviewed" | "approved" | "locked";
  summary: string;
  weather_source: string;
  weather_summary: string;
  temperature_high_c: number | null;
  temperature_low_c: number | null;
  precipitation_mm: number | null;
  wind_max_kph: number | null;
  rejection_reason: string;
  revision: number;
  prepared_by?: ApiUser;
};

export type SessionResponse = {
  authenticated: boolean;
  user?: ApiUser;
};

export type OfflineMutation = {
  id: string;
  method: "POST" | "PUT" | "PATCH" | "DELETE";
  endpoint: string;
  payload: Record<string, unknown>;
  createdAt: number;
};
