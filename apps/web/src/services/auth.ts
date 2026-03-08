import { apiRequest } from "./api";
import type { ApiUser, SessionResponse } from "../types/api";

export async function login(username: string, password: string): Promise<ApiUser> {
  return apiRequest<ApiUser>("/auth/login/", {
    method: "POST",
    body: JSON.stringify({ username, password })
  });
}

export async function logout(): Promise<void> {
  await apiRequest<void>("/auth/logout/", { method: "POST" });
}

export async function getSession(): Promise<SessionResponse> {
  return apiRequest<SessionResponse>("/auth/session/");
}
