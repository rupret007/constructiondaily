import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SheetCopilotPanel } from "./SheetCopilotPanel";

const queryPreconstructionCopilot = vi.fn();

vi.mock("../services/preconstruction", () => ({
  queryPreconstructionCopilot: (...args: unknown[]) => queryPreconstructionCopilot(...args),
}));

describe("SheetCopilotPanel", () => {
  beforeEach(() => {
    queryPreconstructionCopilot.mockReset();
  });

  it("executes a returned analysis action plan", async () => {
    const onRunAnalysis = vi.fn().mockResolvedValue(undefined);
    queryPreconstructionCopilot.mockResolvedValue({
      status: "grounded",
      answer: "I can run analysis on this sheet.",
      scope: {
        project_id: "project-1",
        project_code: "BID-1",
        project_name: "Building A",
        plan_set_id: "set-1",
        plan_set_name: "Bid Set",
        plan_sheet_id: "sheet-1",
        plan_sheet_name: "A101",
      },
      citations: [],
      suggested_prompts: [],
      action_plan: {
        kind: "run_analysis",
        label: "Run sheet analysis",
        detail: "Trigger a new run.",
        prompt: "Find all doors on A101",
        provider_name: "mock",
      },
    });

    render(
      <SheetCopilotPanel
        projectId="project-1"
        planSetId="set-1"
        sheetId="sheet-1"
        sheetLabel="A101"
        analysisProvider="mock"
        onRunAnalysis={onRunAnalysis}
        onBatchAccept={vi.fn().mockResolvedValue(undefined)}
        onCreateTakeoffFromAnnotation={vi.fn().mockResolvedValue(undefined)}
        onCreateSnapshot={vi.fn().mockResolvedValue(undefined)}
        onExport={vi.fn().mockResolvedValue(undefined)}
      />
    );

    await userEvent.type(screen.getByLabelText(/ask sheet copilot/i), "Find all doors on A101");
    await userEvent.click(screen.getByRole("button", { name: /run/i }));

    await waitFor(() => expect(onRunAnalysis).toHaveBeenCalledWith("Find all doors on A101", "mock"));
    expect(await screen.findByText(/executed: run sheet analysis/i)).toBeInTheDocument();
  });

  it("renders limited guidance when no action plan is returned", async () => {
    const onCreateTakeoffFromAnnotation = vi.fn().mockResolvedValue(undefined);
    queryPreconstructionCopilot.mockResolvedValue({
      status: "limited",
      answer: "Select an annotation first.",
      scope: {
        project_id: "project-1",
        project_code: "BID-1",
        project_name: "Building A",
        plan_set_id: "set-1",
        plan_set_name: "Bid Set",
        plan_sheet_id: "sheet-1",
        plan_sheet_name: "A101",
      },
      citations: [],
      suggested_prompts: [],
    });

    render(
      <SheetCopilotPanel
        projectId="project-1"
        planSetId="set-1"
        sheetId="sheet-1"
        sheetLabel="A101"
        analysisProvider="mock"
        onRunAnalysis={vi.fn().mockResolvedValue(undefined)}
        onBatchAccept={vi.fn().mockResolvedValue(undefined)}
        onCreateTakeoffFromAnnotation={onCreateTakeoffFromAnnotation}
        onCreateSnapshot={vi.fn().mockResolvedValue(undefined)}
        onExport={vi.fn().mockResolvedValue(undefined)}
      />
    );

    await userEvent.type(screen.getByLabelText(/ask sheet copilot/i), "Create takeoff package from this annotation");
    await userEvent.click(screen.getByRole("button", { name: /run/i }));

    expect(await screen.findByText(/select an annotation first/i)).toBeInTheDocument();
    expect(onCreateTakeoffFromAnnotation).not.toHaveBeenCalled();
  });
});
