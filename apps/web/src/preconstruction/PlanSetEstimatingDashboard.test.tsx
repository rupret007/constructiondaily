import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PlanSetEstimatingDashboard } from "./PlanSetEstimatingDashboard";
import type { PlanSetEstimatingDashboard as PlanSetEstimatingDashboardResponse } from "../types/api";

const fetchPlanSetEstimatingDashboard = vi.fn();

vi.mock("../services/preconstruction", () => ({
  fetchPlanSetEstimatingDashboard: (...args: unknown[]) => fetchPlanSetEstimatingDashboard(...args),
}));

function buildDashboard(
  planSetId: string,
  planSetName: string,
  {
    sheetId = "sheet-1",
    sheetNumber = "A101",
    latestAnalysisStatus = "completed",
    pendingSuggestions = 5,
    totalItems = 9,
    pendingItems = 3,
  }: {
    sheetId?: string;
    sheetNumber?: string;
    latestAnalysisStatus?: string | null;
    pendingSuggestions?: number;
    totalItems?: number;
    pendingItems?: number;
  } = {}
): PlanSetEstimatingDashboardResponse {
  return {
    plan_set_id: planSetId,
    plan_set_name: planSetName,
    plan_set_status: "ready",
    version_label: "Bid 2",
    summary: {
      total_items: totalItems,
      pending_items: pendingItems,
      accepted_items: 4,
      rejected_items: 1,
      edited_items: 1,
      manual_items: 5,
      ai_assisted_items: 4,
      linked_annotation_items: 6,
      unit_totals: [],
      category_totals: [],
      review_state_totals: [],
      source_totals: [],
    },
    coverage: {
      total_sheet_count: 1,
      calibrated_sheet_count: 1,
      parsed_sheet_count: 1,
      analyzed_sheet_count: latestAnalysisStatus === "completed" ? 1 : 0,
      sheets_with_takeoff_count: 1,
      pending_suggestion_count: pendingSuggestions,
      unassigned_takeoff_items: 0,
    },
    discipline_rollups: [
      {
        discipline: "Architectural",
        sheet_count: 1,
        calibrated_sheet_count: 1,
        parsed_sheet_count: 1,
        analyzed_sheet_count: latestAnalysisStatus === "completed" ? 1 : 0,
        takeoff_total_items: totalItems,
        pending_items: pendingItems,
        pending_suggestions: pendingSuggestions,
      },
    ],
    sheet_rollups: [
      {
        id: sheetId,
        title: `${sheetNumber} plan`,
        sheet_number: sheetNumber,
        discipline: "Architectural",
        file_type: "pdf",
        parse_status: "parsed",
        calibrated: true,
        total_items: totalItems,
        pending_items: pendingItems,
        accepted_items: 2,
        edited_items: 1,
        rejected_items: 0,
        linked_annotation_items: 4,
        pending_suggestions: pendingSuggestions,
        latest_analysis_status: latestAnalysisStatus,
        latest_analysis_at: latestAnalysisStatus ? "2026-03-15T20:00:00Z" : null,
        top_categories: [
          {
            category: "doors",
            unit: "count",
            item_count: 4,
            quantity_total: "4.0000",
          },
        ],
      },
    ],
    unassigned_summary: {
      total_items: 0,
      pending_items: 0,
      accepted_items: 0,
      rejected_items: 0,
      edited_items: 0,
      manual_items: 0,
      ai_assisted_items: 0,
      linked_annotation_items: 0,
      unit_totals: [],
      category_totals: [],
      review_state_totals: [],
      source_totals: [],
    },
    latest_snapshot: {
      id: "snap-1",
      name: "Pricing Snapshot",
      status: "locked",
      created_at: "2026-03-15T18:00:00Z",
    },
    latest_export: {
      id: "export-1",
      export_type: "csv",
      status: "generated",
      created_at: "2026-03-15T19:00:00Z",
    },
  };
}

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("PlanSetEstimatingDashboard", () => {
  beforeEach(() => {
    fetchPlanSetEstimatingDashboard.mockReset();
  });

  it("loads plan-set rollups and opens a selected sheet", async () => {
    const onOpenSheet = vi.fn();
    fetchPlanSetEstimatingDashboard.mockResolvedValue(buildDashboard("set-1", "Pricing Set"));

    render(
      <PlanSetEstimatingDashboard
        planSetId="set-1"
        planSetName="Pricing Set"
        onOpenSheet={onOpenSheet}
      />
    );

    expect(fetchPlanSetEstimatingDashboard).toHaveBeenCalledWith("set-1");
    expect(await screen.findByText(/cross-sheet estimating view for pricing set/i)).toBeInTheDocument();
    expect(screen.getByText("Takeoff rows")).toBeInTheDocument();
    expect(screen.getAllByText(/3 pending review/i).length).toBeGreaterThan(0);
    expect(screen.getByText("Architectural")).toBeInTheDocument();
    expect(screen.getByText("A101")).toBeInTheDocument();
    expect(screen.getByText(/pricing snapshot \| locked/i)).toBeInTheDocument();
    expect(screen.getByText(/doors 4.0000 count/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /open sheet/i }));

    expect(onOpenSheet).toHaveBeenCalledWith("sheet-1");
  });

  it("reloads when refresh is clicked", async () => {
    fetchPlanSetEstimatingDashboard.mockResolvedValue(buildDashboard("set-1", "Pricing Set"));

    render(
      <PlanSetEstimatingDashboard
        planSetId="set-1"
        planSetName="Pricing Set"
        onOpenSheet={() => {}}
      />
    );

    expect(await screen.findByText(/estimating dashboard/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /refresh/i }));

    await waitFor(() => expect(fetchPlanSetEstimatingDashboard).toHaveBeenCalledTimes(2));
  });

  it("clears loaded data when the selected plan set changes", async () => {
    const secondLoad = createDeferred<PlanSetEstimatingDashboardResponse>();
    fetchPlanSetEstimatingDashboard
      .mockResolvedValueOnce(buildDashboard("set-1", "Pricing Set", { sheetNumber: "A101" }))
      .mockImplementationOnce(() => secondLoad.promise);

    const { rerender } = render(
      <PlanSetEstimatingDashboard
        planSetId="set-1"
        planSetName="Pricing Set"
        onOpenSheet={() => {}}
      />
    );

    expect(await screen.findByText("A101")).toBeInTheDocument();

    rerender(
      <PlanSetEstimatingDashboard
        planSetId="set-2"
        planSetName="Addendum Set"
        onOpenSheet={() => {}}
      />
    );

    expect(screen.getByText(/cross-sheet estimating view for addendum set/i)).toBeInTheDocument();
    expect(screen.getByText(/loading estimator dashboard/i)).toBeInTheDocument();
    expect(screen.queryByText("A101")).not.toBeInTheDocument();

    secondLoad.resolve(buildDashboard("set-2", "Addendum Set", { sheetId: "sheet-2", sheetNumber: "B201" }));

    expect(await screen.findByText("B201")).toBeInTheDocument();
  });

  it("ignores stale responses after a quick plan-set switch", async () => {
    const firstLoad = createDeferred<PlanSetEstimatingDashboardResponse>();
    const secondLoad = createDeferred<PlanSetEstimatingDashboardResponse>();
    fetchPlanSetEstimatingDashboard.mockImplementation((planSetId: string) => {
      if (planSetId === "set-1") {
        return firstLoad.promise;
      }
      return secondLoad.promise;
    });

    const { rerender } = render(
      <PlanSetEstimatingDashboard
        planSetId="set-1"
        planSetName="Pricing Set"
        onOpenSheet={() => {}}
      />
    );

    rerender(
      <PlanSetEstimatingDashboard
        planSetId="set-2"
        planSetName="Addendum Set"
        onOpenSheet={() => {}}
      />
    );

    firstLoad.resolve(buildDashboard("set-1", "Pricing Set", { sheetNumber: "A101" }));

    await waitFor(() => {
      expect(screen.getByText(/cross-sheet estimating view for addendum set/i)).toBeInTheDocument();
      expect(screen.queryByText("A101")).not.toBeInTheDocument();
    });

    secondLoad.resolve(buildDashboard("set-2", "Addendum Set", { sheetId: "sheet-2", sheetNumber: "B201" }));

    expect(await screen.findByText("B201")).toBeInTheDocument();
  });
});
