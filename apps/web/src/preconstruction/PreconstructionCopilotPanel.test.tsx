import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PreconstructionCopilotPanel } from "./PreconstructionCopilotPanel";
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

describe("PreconstructionCopilotPanel", () => {
  let speak: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    queryPreconstructionCopilot.mockReset();
    ({ speak } = installVoiceTestStubs());
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

  it("submits a spoken question and can read the answer aloud", async () => {
    queryPreconstructionCopilot.mockResolvedValue({
      status: "grounded",
      answer: "I found 5 calibrated sheets in Pricing Set.",
      scope: {
        project_id: "project-1",
        project_code: "BID-1",
        project_name: "Building A",
        plan_set_id: "set-1",
        plan_set_name: "Pricing Set",
        plan_sheet_id: null,
        plan_sheet_name: null,
      },
      citations: [],
      suggested_prompts: [],
    });

    render(
      <PreconstructionCopilotPanel
        projectId="project-1"
        projectLabel="BID-1 - Building A"
        planSetId="set-1"
        planSetName="Pricing Set"
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /spoken replies off/i }));
    await userEvent.click(screen.getByRole("button", { name: /start voice/i }));

    const recognition = MockSpeechRecognition.instances.at(-1);
    expect(recognition).toBeTruthy();
    act(() => {
      recognition?.emitTranscript("Which sheets are calibrated?");
    });

    await waitFor(() =>
      expect(queryPreconstructionCopilot).toHaveBeenCalledWith({
        project: "project-1",
        plan_set: "set-1",
        question: "Which sheets are calibrated?",
      })
    );
    expect(await screen.findByText(/i found 5 calibrated sheets in pricing set/i)).toBeInTheDocument();
    await waitFor(() => expect(speak).toHaveBeenCalledTimes(1));
    expect(speak.mock.calls[0][0].text).toBe("I found 5 calibrated sheets in Pricing Set.");
  });

  it("ignores stale replies after the copilot scope changes", async () => {
    const firstReply = createDeferred<{
      status: "grounded";
      answer: string;
      scope: {
        project_id: string;
        project_code: string;
        project_name: string;
        plan_set_id: string;
        plan_set_name: string;
        plan_sheet_id: null;
        plan_sheet_name: null;
      };
      citations: [];
      suggested_prompts: [];
    }>();
    queryPreconstructionCopilot.mockImplementationOnce(() => firstReply.promise);

    const { rerender } = render(
      <PreconstructionCopilotPanel
        projectId="project-1"
        projectLabel="BID-1 - Building A"
        planSetId="set-1"
        planSetName="Pricing Set"
      />
    );

    await userEvent.type(screen.getByLabelText(/ask estimator copilot/i), "How many pending doors?");
    await userEvent.click(screen.getByRole("button", { name: /^ask$/i }));

    expect(screen.getByText("How many pending doors?")).toBeInTheDocument();

    rerender(
      <PreconstructionCopilotPanel
        projectId="project-1"
        projectLabel="BID-1 - Building A"
        planSetId="set-2"
        planSetName="Addendum Set"
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/ask about plan set addendum set/i)).toBeInTheDocument();
      expect(screen.queryByText("How many pending doors?")).not.toBeInTheDocument();
    });

    firstReply.resolve({
      status: "grounded",
      answer: "Old scope answer",
      scope: {
        project_id: "project-1",
        project_code: "BID-1",
        project_name: "Building A",
        plan_set_id: "set-1",
        plan_set_name: "Pricing Set",
        plan_sheet_id: null,
        plan_sheet_name: null,
      },
      citations: [],
      suggested_prompts: [],
    });

    await waitFor(() => expect(screen.queryByText("Old scope answer")).not.toBeInTheDocument());
  });
});
