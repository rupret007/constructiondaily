import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SheetCopilotPanel } from "./SheetCopilotPanel";
import { MockSpeechRecognition, installVoiceTestStubs } from "../test/voiceTestUtils";

const queryPreconstructionCopilot = vi.fn();

vi.mock("../services/preconstruction", () => ({
  queryPreconstructionCopilot: (...args: unknown[]) => queryPreconstructionCopilot(...args),
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

describe("SheetCopilotPanel", () => {
  beforeEach(() => {
    queryPreconstructionCopilot.mockReset();
    installVoiceTestStubs();
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

  it("runs a spoken sheet command through the returned action plan", async () => {
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

    await userEvent.click(screen.getByRole("button", { name: /start voice/i }));

    const recognition = MockSpeechRecognition.instances.at(-1);
    expect(recognition).toBeTruthy();
    act(() => {
      recognition?.emitTranscript("Find all doors on A101");
    });

    await waitFor(() => expect(onRunAnalysis).toHaveBeenCalledWith("Find all doors on A101", "mock"));
    expect(await screen.findByText(/executed: run sheet analysis/i)).toBeInTheDocument();
  });

  it("resets the conversation and ignores stale replies when the sheet changes", async () => {
    const firstReply = createDeferred<{
      status: "grounded";
      answer: string;
      scope: {
        project_id: string;
        project_code: string;
        project_name: string;
        plan_set_id: string;
        plan_set_name: string;
        plan_sheet_id: string;
        plan_sheet_name: string;
      };
      citations: [];
      suggested_prompts: [];
    }>();
    queryPreconstructionCopilot.mockImplementationOnce(() => firstReply.promise);

    const { rerender } = render(
      <SheetCopilotPanel
        projectId="project-1"
        planSetId="set-1"
        sheetId="sheet-1"
        sheetLabel="A101"
        analysisProvider="mock"
        onRunAnalysis={vi.fn().mockResolvedValue(undefined)}
        onBatchAccept={vi.fn().mockResolvedValue(undefined)}
        onCreateTakeoffFromAnnotation={vi.fn().mockResolvedValue(undefined)}
        onCreateSnapshot={vi.fn().mockResolvedValue(undefined)}
        onExport={vi.fn().mockResolvedValue(undefined)}
      />
    );

    await userEvent.type(screen.getByLabelText(/ask sheet copilot/i), "Find all doors on A101");
    await userEvent.click(screen.getByRole("button", { name: /run/i }));

    expect(screen.getAllByText("Find all doors on A101").length).toBeGreaterThan(0);

    rerender(
      <SheetCopilotPanel
        projectId="project-1"
        planSetId="set-1"
        sheetId="sheet-2"
        sheetLabel="A201"
        analysisProvider="mock"
        onRunAnalysis={vi.fn().mockResolvedValue(undefined)}
        onBatchAccept={vi.fn().mockResolvedValue(undefined)}
        onCreateTakeoffFromAnnotation={vi.fn().mockResolvedValue(undefined)}
        onCreateSnapshot={vi.fn().mockResolvedValue(undefined)}
        onExport={vi.fn().mockResolvedValue(undefined)}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/scoped to a201/i)).toBeInTheDocument();
      expect(screen.queryByText("Find all doors on A101")).not.toBeInTheDocument();
    });

    firstReply.resolve({
      status: "grounded",
      answer: "Old sheet answer",
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

    await waitFor(() => expect(screen.queryByText("Old sheet answer")).not.toBeInTheDocument());
  });
});
