import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { PreconstructionDashboard } from "./PreconstructionDashboard";
import type { PlanSet, PlanSheet, Project } from "../types/api";

const createPlanSet = vi.fn();
const fetchPlanSets = vi.fn();
const fetchPlanSheets = vi.fn();
const uploadPlanSheet = vi.fn();

vi.mock("../services/preconstruction", () => ({
  createPlanSet: (...args: unknown[]) => createPlanSet(...args),
  fetchPlanSets: (...args: unknown[]) => fetchPlanSets(...args),
  fetchPlanSheets: (...args: unknown[]) => fetchPlanSheets(...args),
  uploadPlanSheet: (...args: unknown[]) => uploadPlanSheet(...args),
}));

vi.mock("./PlanSetEstimatingDashboard", () => ({
  PlanSetEstimatingDashboard: ({ planSetId }: { planSetId: string }) => (
    <div data-testid="estimating-dashboard">{planSetId}</div>
  ),
}));

vi.mock("./ProjectDocumentPanel", () => ({
  ProjectDocumentPanel: ({ projectId, planSetId }: { projectId: string; planSetId?: string }) => (
    <div data-testid="project-documents">{`${projectId}:${planSetId ?? "none"}`}</div>
  ),
}));

vi.mock("./PreconstructionCopilotPanel", () => ({
  PreconstructionCopilotPanel: ({ projectId, planSetId }: { projectId: string; planSetId?: string }) => (
    <div data-testid="preconstruction-copilot">{`${projectId}:${planSetId ?? "none"}`}</div>
  ),
}));

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const projects: Project[] = [
  {
    id: "project-1",
    code: "P1",
    name: "Project One",
    location: "Site 1",
    latitude: null,
    longitude: null,
    is_active: true,
  },
  {
    id: "project-2",
    code: "P2",
    name: "Project Two",
    location: "Site 2",
    latitude: null,
    longitude: null,
    is_active: true,
  },
];

const planSetOne: PlanSet = {
  id: "set-1",
  project: "project-1",
  name: "Pricing Set",
  description: "",
  status: "ready",
  version_label: "Bid 2",
  created_at: "2026-03-17T10:00:00Z",
  updated_at: "2026-03-17T10:00:00Z",
};

const sheetOne: PlanSheet = {
  id: "sheet-1",
  project: "project-1",
  plan_set: "set-1",
  title: "Level 1 Plan",
  sheet_number: "A101",
  discipline: "Architectural",
  storage_key: "plans/project-1/a101.pdf",
  page_count: 1,
  sheet_index: 1,
  width: null,
  height: null,
  calibrated_width: null,
  calibrated_height: null,
  calibrated_unit: "feet",
  parse_status: "parsed",
  preview_image: "",
  file_extension: "pdf",
  file_type: "pdf",
  created_at: "2026-03-17T10:00:00Z",
  updated_at: "2026-03-17T10:00:00Z",
};

function DashboardHarness() {
  const [selectedProjectId, setSelectedProjectId] = useState("project-1");

  return (
    <PreconstructionDashboard
      projectId={selectedProjectId}
      projects={projects}
      selectedProjectId={selectedProjectId}
      onProjectChange={setSelectedProjectId}
      onOpenSheet={() => {}}
      error=""
      onClearError={() => {}}
      onError={() => {}}
    />
  );
}

describe("PreconstructionDashboard", () => {
  beforeEach(() => {
    createPlanSet.mockReset();
    fetchPlanSets.mockReset();
    fetchPlanSheets.mockReset();
    uploadPlanSheet.mockReset();
  });

  it("clears plan-set scoped UI immediately when the project changes", async () => {
    const secondProjectLoad = createDeferred<PlanSet[]>();
    fetchPlanSets.mockImplementation((projectId: string) => {
      if (projectId === "project-1") {
        return Promise.resolve([planSetOne]);
      }
      return secondProjectLoad.promise;
    });
    fetchPlanSheets.mockResolvedValue([sheetOne]);

    render(<DashboardHarness />);

    await userEvent.click(await screen.findByRole("button", { name: /pricing set/i }));

    expect(await screen.findByTestId("estimating-dashboard")).toHaveTextContent("set-1");
    expect(screen.getByTestId("project-documents")).toHaveTextContent("project-1:set-1");
    expect(screen.getByTestId("preconstruction-copilot")).toHaveTextContent("project-1:set-1");

    await userEvent.selectOptions(screen.getByLabelText(/select project/i), "project-2");

    await waitFor(() => {
      expect(screen.queryByTestId("estimating-dashboard")).not.toBeInTheDocument();
      expect(screen.getByText(/select a plan set to view and upload sheets/i)).toBeInTheDocument();
      expect(screen.getByTestId("project-documents")).toHaveTextContent("project-2:none");
      expect(screen.getByTestId("preconstruction-copilot")).toHaveTextContent("project-2:none");
    });

    expect(fetchPlanSets).toHaveBeenCalledWith("project-2");
  });
});
