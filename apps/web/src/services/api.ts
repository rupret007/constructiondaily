const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

function getCookie(name: string): string {
  const cookie = document.cookie.split("; ").find((item) => item.startsWith(`${name}=`));
  return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
}

function messageFromJson(payload: unknown): string {
  if (!payload || typeof payload !== "object") return "";
  const record = payload as Record<string, unknown>;
  if (typeof record.detail === "string") {
    return record.detail;
  }
  if (typeof record.non_field_errors === "string") {
    return record.non_field_errors;
  }
  if (Array.isArray(record.non_field_errors)) {
    const first = record.non_field_errors.find((item) => typeof item === "string");
    return typeof first === "string" ? first : "";
  }
  const firstStringField = Object.values(record).find((item) => typeof item === "string");
  if (typeof firstStringField === "string") {
    return firstStringField;
  }
  return "";
}

export async function apiRequest<T>(endpoint: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  headers.set("Accept", "application/json");

  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const method = init.method ?? "GET";
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method.toUpperCase())) {
    const csrfToken = getCookie("csrftoken");
    if (csrfToken) {
      headers.set("X-CSRFToken", csrfToken);
    }
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...init,
    headers,
    credentials: "include"
  });

  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const payload = (await response.json()) as unknown;
      const message = messageFromJson(payload);
      throw new Error(message || `Request failed (${response.status}).`);
    }
    const text = (await response.text()).trim();
    throw new Error(text || `Request failed (${response.status}).`);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
