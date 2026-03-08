import { apiRequest } from "./api";
import type { Project } from "../types/api";

type PaginatedResponse<T> = {
  results?: T[];
};

export async function fetchProjects(): Promise<Project[]> {
  const response = await apiRequest<Project[] | PaginatedResponse<Project>>("/projects/");
  return Array.isArray(response) ? response : response.results ?? [];
}
