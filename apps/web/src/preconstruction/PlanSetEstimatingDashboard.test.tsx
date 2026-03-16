import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PlanSetEstimatingDashboard } from "./PlanSetEstimatingDashboard";

const fetchPlanSetEstimatingDashboard = vi.fn();

vi.mock("../services/preconstruction", () => ({
  fetchPlanSetEstimatingDashboard: (...args: unknown[]) => fetchPlanSetEstimatingDashboard(...args),
}));

describe("PlanSetEstimatingDashboard", () => {
  beforeEach(() => {
    fetchPlanSetEstimatingDashboard.mockReset();
  });

  it("loads plan-set rollups and opens a selected sheet", async () => {
    const onOpenSheet = vi.fn();
    fetchPlanSetEstimatingDashboard.mockResolvedValue({
      plan_set_id: "set-1",
      plan_set_name: "Pricing Set",
      plan_set_status: "ready",
      version_label: "Bid 2",
      summary: {
        total_items: 9,
        pending_items: 3,
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
        total_sheet_count: 2,
        calibrated_sheet_count: 1,
        parsed_sheet_count: 2,
        analyzed_sheet_count: 1,
        sheets_with_takeoff_count: 2,
        pending_suggestion_count: 5,
        unassigned_takeoff_items: 1,
      },
      discipline_rollups: [
        {
          discipline: "Architectural",
          sheet_count: 2,
          calibrated_sheet_count: 1,
          parsed_sheet_count: 2,
          analyzed_sheet_count: 1,
          takeoff_total_items: 9,
          pending_items: 3,
          pending_suggestions: 5,
        },
      ],
      sheet_rollups: [
        {
          id: "sheet-1",
          title: "Level 1 Plan",
          sheet_number: "A101",
          discipline: "Architectural",
          file_type: "pdf",
          parse_status: "parsed",
          calibrated: true,
          total_items: 6,
          pending_items: 3,
          accepted_items: 2,
          edited_items: 1,
          rejected_items: 0,
          linked_annotation_items: 4,
          pending_suggestions: 5,
          latest_analysis_status: "completed",
          latest_analysis_at: "2026-03-15T20:00:00Z",
          top_categories: [
            {
              category: "doors",
              unit: "count",
              item_count: 4,
              quantity_total: "4.0000",
            },
          ],
        },
        {
          id: "sheet-2",
          title: "Level 2 Plan",
          sheet_number: "A201",
          discipline: "Architectural",
          file_type: "pdf",
          parse_status: "parsed",
          calibrated: false,
          total_items: 3,
          pending_items: 0,
          accepted_items: 2,
          edited_items: 0,
          rejected_items: 1,
          linked_annotation_items: 2,
          pending_suggestions: 0,
          latest_analysis_status: null,
          latest_analysis_at: null,
          top_categories: [],
        },
      ],
      unassigned_summary: {
        total_items: 1,
        pending_items: 1,
        accepted_items: 0,
        rejected_items: 0,
        edited_items: 0,
        manual_items: 1,
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
    });

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
    expect(screen.getByText(/doors 4.0000 count/i)).toBeInTheDocument();

    await userEvent.click(screen.getAllByRole("button", { name: /open sheet/i })[0]);

    expect(onOpenSheet).toHaveBeenCalledWith("sheet-1");
  });

  it("reloads when refresh is clicked", async () => {
    fetchPlanSetEstimatingDashboard.mockResolvedValue({
      plan_set_id: "set-1",
      plan_set_name: "Pricing Set",
      plan_set_status: "draft",
      version_label: "",
      summary: {
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
      coverage: {
        total_sheet_count: 0,
        calibrated_sheet_count: 0,
        parsed_sheet_count: 0,
        analyzed_sheet_count: 0,
        sheets_with_takeoff_count: 0,
        pending_suggestion_count: 0,
        unassigned_takeoff_items: 0,
      },
      discipline_rollups: [],
      sheet_rollups: [],
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
      latest_snapshot: null,
      latest_export: null,
    });

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
});
