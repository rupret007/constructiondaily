const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

function getCookie(name: string): string {
  const cookie = document.cookie.split("; ").find((item) => item.startsWith(`${name}=`));
  return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
}

function firstErrorString(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    for (const item of value) {
      const message = firstErrorString(item);
      if (message) return message;
    }
    return "";
  }
  if (!value || typeof value !== "object") return "";

  const record = value as Record<string, unknown>;
  const priorityFields = ["detail", "non_field_errors", "message", "error"];
  for (const field of priorityFields) {
    const message = firstErrorString(record[field]);
    if (message) return message;
  }
  for (const nested of Object.values(record)) {
    const message = firstErrorString(nested);
    if (message) return message;
  }
  return "";
}

function messageFromJson(payload: unknown): string {
  return firstErrorString(payload);
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
