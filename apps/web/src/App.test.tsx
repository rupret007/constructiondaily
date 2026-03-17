import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import App from "./App";
import { ApiRequestError } from "./services/api";

vi.mock("./services/auth", () => ({
  getSession: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("./services/projects", () => ({
  fetchProjects: vi.fn(),
}));

vi.mock("./services/reports", () => ({
  fetchReports: vi.fn(),
  fetchReport: vi.fn(),
  createReport: vi.fn(),
  updateReport: vi.fn(),
  transitionReport: vi.fn(),
  syncWeather: vi.fn(),
}));

vi.mock("./hooks/useOfflineSync", () => ({
  useOfflineSync: () => ({
    isOnline: true,
    lastFlushedCount: 0,
    lastFlushId: 0,
    queuedCount: 0,
  }),
}));

vi.mock("./offline/queue", () => ({
  enqueueMutation: vi.fn(),
}));

const { getSession } = await import("./services/auth");
const { fetchProjects } = await import("./services/projects");

describe("App 401 handling", () => {
  it("shows login form when a key API call returns 401", async () => {
    vi.mocked(getSession).mockResolvedValue({
      authenticated: true,
      user: { id: 1, username: "testuser", first_name: "Test", last_name: "User" },
    });
    vi.mocked(fetchProjects).mockRejectedValue(new ApiRequestError("Unauthorized", 401));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    });
  });
});
