import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PreconstructionCopilotPanel } from "./PreconstructionCopilotPanel";

const queryPreconstructionCopilot = vi.fn();

vi.mock("../services/preconstruction", () => ({
  queryPreconstructionCopilot: (...args: unknown[]) => queryPreconstructionCopilot(...args),
}));

describe("PreconstructionCopilotPanel", () => {
  beforeEach(() => {
    queryPreconstructionCopilot.mockReset();
  });

  it("renders the scoped welcome message", () => {
    render(
      <PreconstructionCopilotPanel
        projectId="project-1"
        projectLabel="BID-1 - Building A"
        planSetId="set-1"
        planSetName="Pricing Set"
      />
    );

    expect(screen.getByText(/grounded in live preconstruction data/i)).toBeInTheDocument();
    expect(screen.getByText(/ask about plan set pricing set/i)).toBeInTheDocument();
  });

  it("submits a question and renders the grounded response with citations", async () => {
    queryPreconstructionCopilot.mockResolvedValue({
      status: "grounded",
      answer: "I found 3 pending door takeoff rows in plan set Pricing Set.",
      scope: {
        project_id: "project-1",
        project_code: "BID-1",
        project_name: "Building A",
        plan_set_id: "set-1",
        plan_set_name: "Pricing Set",
        plan_sheet_id: null,
        plan_sheet_name: null,
      },
      citations: [
        {
          kind: "takeoff_summary",
          id: "summary-1",
          label: "Takeoff summary",
          detail: "3 rows, 3 pending, 0 accepted.",
        },
      ],
      suggested_prompts: ["Which sheets in this plan set are calibrated?"],
    });

    render(
      <PreconstructionCopilotPanel
        projectId="project-1"
        projectLabel="BID-1 - Building A"
        planSetId="set-1"
        planSetName="Pricing Set"
      />
    );

    await userEvent.type(screen.getByLabelText(/ask estimator copilot/i), "How many pending doors?");
    await userEvent.click(screen.getByRole("button", { name: /^ask$/i }));

    expect(queryPreconstructionCopilot).toHaveBeenCalledWith({
      project: "project-1",
      plan_set: "set-1",
      question: "How many pending doors?",
    });
    expect(await screen.findByText(/i found 3 pending door takeoff rows/i)).toBeInTheDocument();
    expect(screen.getByText(/takeoff summary/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /which sheets in this plan set are calibrated/i })).toBeInTheDocument();
  });
});
