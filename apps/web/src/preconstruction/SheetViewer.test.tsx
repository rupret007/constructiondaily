import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { SheetViewer } from "./SheetViewer";
import type {
  AISuggestion,
  AnnotationItem,
  AnnotationLayer,
  ExportRecord,
  PlanSheet,
  RevisionSnapshot,
  TakeoffItem,
  TakeoffSummary,
} from "../types/api";

const acceptSuggestion = vi.fn();
const batchAcceptSuggestions = vi.fn();
const createAnnotation = vi.fn();
const createAnnotationLayer = vi.fn();
const createExport = vi.fn();
const createSnapshot = vi.fn();
const createTakeoffFromAnnotation = vi.fn();
const createTakeoffItem = vi.fn();
const deleteAnnotation = vi.fn();
const deleteTakeoffItem = vi.fn();
const fetchAnnotationLayers = vi.fn();
const fetchAnnotations = vi.fn();
const fetchExportRecords = vi.fn();
const fetchPlanSheetCadPreview = vi.fn();
const fetchPlanSheet = vi.fn();
const fetchSnapshots = vi.fn();
const fetchSuggestions = vi.fn();
const fetchTakeoffItems = vi.fn();
const fetchTakeoffSummary = vi.fn();
const lockSnapshot = vi.fn();
const planSheetFileUrl = vi.fn();
const rejectSuggestion = vi.fn();
const triggerAnalysis = vi.fn();
const updateAnnotation = vi.fn();
const updateAnnotationLayer = vi.fn();
const updatePlanSheet = vi.fn();
const updateTakeoffItem = vi.fn();

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: vi.fn(() => ({
    promise: Promise.reject(new Error("PDF loading is not expected in this test.")),
    destroy: vi.fn(),
  })),
}));

vi.mock("./SheetCopilotPanel", () => ({
  SheetCopilotPanel: ({ sheetLabel }: { sheetLabel: string }) => (
    <div data-testid="sheet-copilot">{sheetLabel}</div>
  ),
}));

vi.mock("../services/preconstruction", () => ({
  acceptSuggestion: (...args: unknown[]) => acceptSuggestion(...args),
  batchAcceptSuggestions: (...args: unknown[]) => batchAcceptSuggestions(...args),
  createAnnotation: (...args: unknown[]) => createAnnotation(...args),
  createAnnotationLayer: (...args: unknown[]) => createAnnotationLayer(...args),
  createExport: (...args: unknown[]) => createExport(...args),
  createSnapshot: (...args: unknown[]) => createSnapshot(...args),
  createTakeoffFromAnnotation: (...args: unknown[]) => createTakeoffFromAnnotation(...args),
  createTakeoffItem: (...args: unknown[]) => createTakeoffItem(...args),
  deleteAnnotation: (...args: unknown[]) => deleteAnnotation(...args),
  deleteTakeoffItem: (...args: unknown[]) => deleteTakeoffItem(...args),
  fetchAnnotationLayers: (...args: unknown[]) => fetchAnnotationLayers(...args),
  fetchAnnotations: (...args: unknown[]) => fetchAnnotations(...args),
  fetchExportRecords: (...args: unknown[]) => fetchExportRecords(...args),
  fetchPlanSheetCadPreview: (...args: unknown[]) => fetchPlanSheetCadPreview(...args),
  fetchPlanSheet: (...args: unknown[]) => fetchPlanSheet(...args),
  fetchSnapshots: (...args: unknown[]) => fetchSnapshots(...args),
  fetchSuggestions: (...args: unknown[]) => fetchSuggestions(...args),
  fetchTakeoffItems: (...args: unknown[]) => fetchTakeoffItems(...args),
  fetchTakeoffSummary: (...args: unknown[]) => fetchTakeoffSummary(...args),
  lockSnapshot: (...args: unknown[]) => lockSnapshot(...args),
  planSheetFileUrl: (...args: unknown[]) => planSheetFileUrl(...args),
  rejectSuggestion: (...args: unknown[]) => rejectSuggestion(...args),
  triggerAnalysis: (...args: unknown[]) => triggerAnalysis(...args),
  updateAnnotation: (...args: unknown[]) => updateAnnotation(...args),
  updateAnnotationLayer: (...args: unknown[]) => updateAnnotationLayer(...args),
  updatePlanSheet: (...args: unknown[]) => updatePlanSheet(...args),
  updateTakeoffItem: (...args: unknown[]) => updateTakeoffItem(...args),
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

function buildPlanSheet(sheetId: string, planSetId: string, title: string): PlanSheet {
  return {
    id: sheetId,
    project: "project-1",
    plan_set: planSetId,
    title,
    sheet_number: `${sheetId.toUpperCase()}-001`,
    discipline: "Architectural",
    storage_key: `${planSetId}/${sheetId}.bin`,
    page_count: 1,
    sheet_index: 1,
    width: null,
    height: null,
    calibrated_width: null,
    calibrated_height: null,
    calibrated_unit: "feet",
    parse_status: "parsed",
    preview_image: "",
    file_extension: "bin",
    file_type: "unknown",
    created_at: "2026-03-17T10:00:00Z",
    updated_at: "2026-03-17T10:00:00Z",
  };
}

function buildLayer(layerId: string, sheetId: string, planSetId: string): AnnotationLayer {
  return {
    id: layerId,
    project: "project-1",
    plan_set: planSetId,
    plan_sheet: sheetId,
    name: `Layer ${layerId}`,
    color: "#2563eb",
    category: "doors",
    is_visible: true,
    is_locked: false,
    created_at: "2026-03-17T10:00:00Z",
    updated_at: "2026-03-17T10:00:00Z",
  };
}

function buildAnnotation(annotationId: string, sheetId: string, layerId: string, label: string): AnnotationItem {
  return {
    id: annotationId,
    project: "project-1",
    plan_sheet: sheetId,
    layer: layerId,
    annotation_type: "rectangle",
    geometry_json: { type: "rectangle", x: 0.2, y: 0.2, width: 0.2, height: 0.1 },
    label,
    notes: "",
    source: "manual",
    confidence: null,
    review_state: "pending",
    linked_takeoff_item: null,
    created_at: "2026-03-17T10:00:00Z",
    updated_at: "2026-03-17T10:00:00Z",
  };
}

function buildSuggestion(suggestionId: string, sheetId: string, label: string): AISuggestion {
  return {
    id: suggestionId,
    analysis_run: "run-1",
    project: "project-1",
    plan_sheet: sheetId,
    suggestion_type: "rectangle",
    geometry_json: { type: "rectangle", x: 0.2, y: 0.2, width: 0.1, height: 0.1 },
    label,
    rationale: "Detected from the plan.",
    confidence: 0.92,
    accepted_annotation: null,
    decision_state: "pending",
    decided_by: null,
    decided_at: null,
    created_at: "2026-03-17T10:00:00Z",
    updated_at: "2026-03-17T10:00:00Z",
  };
}

function buildSnapshot(snapshotId: string, planSetId: string, name: string): RevisionSnapshot {
  return {
    id: snapshotId,
    project: "project-1",
    plan_set: planSetId,
    name,
    status: "locked",
    snapshot_payload_json: {},
    created_at: "2026-03-17T10:00:00Z",
  };
}

function buildExport(exportId: string, planSetId: string, exportType: string): ExportRecord {
  return {
    id: exportId,
    project: "project-1",
    plan_set: planSetId,
    revision_snapshot: null,
    export_type: exportType,
    status: "generated",
    storage_key: `${planSetId}/${exportType}.json`,
    metadata_json: {},
    created_at: "2026-03-17T10:00:00Z",
  };
}

function buildTakeoffItem(takeoffId: string, planSetId: string, sheetId: string): TakeoffItem {
  return {
    id: takeoffId,
    project: "project-1",
    plan_set: planSetId,
    plan_sheet: sheetId,
    category: "doors",
    subcategory: "",
    unit: "count",
    quantity: "1",
    confidence: null,
    notes: "",
    cost_code: "",
    bid_package: "",
    source: "manual",
    review_state: "pending",
    created_at: "2026-03-17T10:00:00Z",
    updated_at: "2026-03-17T10:00:00Z",
  };
}

function buildTakeoffSummary(totalItems: number): TakeoffSummary {
  return {
    total_items: totalItems,
    pending_items: totalItems,
    accepted_items: 0,
    rejected_items: 0,
    edited_items: 0,
    manual_items: totalItems,
    ai_assisted_items: 0,
    linked_annotation_items: 0,
    unit_totals: [],
    category_totals: [],
    review_state_totals: [],
    source_totals: [],
  };
}

describe("SheetViewer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);

    fetchPlanSheetCadPreview.mockResolvedValue({ items: [] });
    planSheetFileUrl.mockReturnValue("/api/preconstruction/sheets/sheet/file/");

    acceptSuggestion.mockResolvedValue({ takeoff: buildTakeoffItem("takeoff-1", "set-1", "sheet-1") });
    batchAcceptSuggestions.mockResolvedValue({ accepted_count: 0 });
    createAnnotation.mockResolvedValue(undefined);
    createAnnotationLayer.mockResolvedValue(buildLayer("layer-new", "sheet-1", "set-1"));
    createExport.mockResolvedValue({ payload: "{}" });
    createSnapshot.mockResolvedValue(undefined);
    createTakeoffFromAnnotation.mockResolvedValue({
      primary_takeoff: buildTakeoffItem("takeoff-1", "set-1", "sheet-1"),
      extra_takeoffs: [],
      assembly_profile: "auto",
    });
    createTakeoffItem.mockResolvedValue(buildTakeoffItem("takeoff-1", "set-1", "sheet-1"));
    deleteAnnotation.mockResolvedValue(undefined);
    deleteTakeoffItem.mockResolvedValue(undefined);
    lockSnapshot.mockResolvedValue(undefined);
    rejectSuggestion.mockResolvedValue(undefined);
    triggerAnalysis.mockResolvedValue(undefined);
    updateAnnotation.mockResolvedValue(undefined);
    updateAnnotationLayer.mockResolvedValue(buildLayer("layer-1", "sheet-1", "set-1"));
    updatePlanSheet.mockResolvedValue(buildPlanSheet("sheet-1", "set-1", "Updated Sheet"));
    updateTakeoffItem.mockResolvedValue(buildTakeoffItem("takeoff-1", "set-1", "sheet-1"));
  });

  it("clears sheet-scoped UI immediately when the selected sheet changes", async () => {
    const sheetTwoLoad = createDeferred<PlanSheet>();

    fetchPlanSheet.mockImplementation((nextSheetId: string) => {
      if (nextSheetId === "sheet-1") {
        return Promise.resolve(buildPlanSheet("sheet-1", "set-1", "Sheet One"));
      }
      return sheetTwoLoad.promise;
    });
    fetchAnnotationLayers.mockImplementation((nextSheetId: string) => Promise.resolve([
      buildLayer(nextSheetId === "sheet-1" ? "layer-1" : "layer-2", nextSheetId, nextSheetId === "sheet-1" ? "set-1" : "set-2"),
    ]));
    fetchAnnotations.mockImplementation((nextSheetId: string) => Promise.resolve([
      buildAnnotation(
        nextSheetId === "sheet-1" ? "annotation-1" : "annotation-2",
        nextSheetId,
        nextSheetId === "sheet-1" ? "layer-1" : "layer-2",
        nextSheetId === "sheet-1" ? "Door Annotation One" : "Window Annotation Two"
      ),
    ]));
    fetchSuggestions.mockImplementation((nextSheetId: string) => Promise.resolve([
      buildSuggestion(
        nextSheetId === "sheet-1" ? "suggestion-1" : "suggestion-2",
        nextSheetId,
        nextSheetId === "sheet-1" ? "Door Suggestion One" : "Window Suggestion Two"
      ),
    ]));
    fetchSnapshots.mockImplementation((nextPlanSetId: string) => Promise.resolve([
      buildSnapshot(
        nextPlanSetId === "set-1" ? "snapshot-1" : "snapshot-2",
        nextPlanSetId,
        nextPlanSetId === "set-1" ? "Pricing Snapshot" : "Addendum Snapshot"
      ),
    ]));
    fetchExportRecords.mockImplementation((nextPlanSetId: string) => Promise.resolve([
      buildExport(
        nextPlanSetId === "set-1" ? "export-1" : "export-2",
        nextPlanSetId,
        nextPlanSetId === "set-1" ? "csv" : "json"
      ),
    ]));
    fetchTakeoffItems.mockResolvedValue([buildTakeoffItem("takeoff-1", "set-1", "sheet-1")]);
    fetchTakeoffSummary.mockResolvedValue(buildTakeoffSummary(1));

    const { rerender } = render(
      <SheetViewer sheetId="sheet-1" planSetId="set-1" onBack={() => {}} />
    );

    expect(await screen.findByText(/Door Annotation One/)).toBeInTheDocument();
    expect(screen.getAllByText("Pricing Snapshot").length).toBeGreaterThan(0);
    expect(screen.getByText(/recent: csv/i)).toBeInTheDocument();

    rerender(<SheetViewer sheetId="sheet-2" planSetId="set-2" onBack={() => {}} />);

    expect(screen.getByText(/loading sheet/i)).toBeInTheDocument();
    expect(screen.queryByText(/Door Annotation One/)).not.toBeInTheDocument();
    expect(screen.queryByText("Pricing Snapshot")).not.toBeInTheDocument();
    expect(screen.queryByText(/recent: csv/i)).not.toBeInTheDocument();

    sheetTwoLoad.resolve(buildPlanSheet("sheet-2", "set-2", "Sheet Two"));

    expect(await screen.findByText(/Window Annotation Two/)).toBeInTheDocument();
    expect(screen.getAllByText("Addendum Snapshot").length).toBeGreaterThan(0);
    expect(screen.getByText(/recent: json/i)).toBeInTheDocument();
  });

  it("ignores stale responses after a quick sheet and plan-set switch", async () => {
    const staleAnnotationsLoad = createDeferred<AnnotationItem[]>();
    const staleSuggestionsLoad = createDeferred<AISuggestion[]>();
    const staleSnapshotsLoad = createDeferred<RevisionSnapshot[]>();
    const staleExportsLoad = createDeferred<ExportRecord[]>();
    const staleTakeoffItemsLoad = createDeferred<TakeoffItem[]>();
    const staleTakeoffSummaryLoad = createDeferred<TakeoffSummary>();

    fetchPlanSheet.mockImplementation((nextSheetId: string) => Promise.resolve(
      nextSheetId === "sheet-1"
        ? buildPlanSheet("sheet-1", "set-1", "Sheet One")
        : buildPlanSheet("sheet-2", "set-2", "Sheet Two")
    ));
    fetchAnnotationLayers.mockImplementation((nextSheetId: string) => Promise.resolve([
      buildLayer(nextSheetId === "sheet-1" ? "layer-1" : "layer-2", nextSheetId, nextSheetId === "sheet-1" ? "set-1" : "set-2"),
    ]));
    fetchAnnotations.mockImplementation((nextSheetId: string) => {
      if (nextSheetId === "sheet-1") return staleAnnotationsLoad.promise;
      return Promise.resolve([buildAnnotation("annotation-2", "sheet-2", "layer-2", "Window Annotation Two")]);
    });
    fetchSuggestions.mockImplementation((nextSheetId: string) => {
      if (nextSheetId === "sheet-1") return staleSuggestionsLoad.promise;
      return Promise.resolve([buildSuggestion("suggestion-2", "sheet-2", "Window Suggestion Two")]);
    });
    fetchSnapshots.mockImplementation((nextPlanSetId: string) => {
      if (nextPlanSetId === "set-1") return staleSnapshotsLoad.promise;
      return Promise.resolve([buildSnapshot("snapshot-2", "set-2", "Addendum Snapshot")]);
    });
    fetchExportRecords.mockImplementation((nextPlanSetId: string) => {
      if (nextPlanSetId === "set-1") return staleExportsLoad.promise;
      return Promise.resolve([buildExport("export-2", "set-2", "json")]);
    });
    fetchTakeoffItems.mockImplementation((nextPlanSetId: string) => {
      if (nextPlanSetId === "set-1") return staleTakeoffItemsLoad.promise;
      return Promise.resolve([buildTakeoffItem("takeoff-2", "set-2", "sheet-2")]);
    });
    fetchTakeoffSummary.mockImplementation((nextPlanSetId: string) => {
      if (nextPlanSetId === "set-1") return staleTakeoffSummaryLoad.promise;
      return Promise.resolve(buildTakeoffSummary(1));
    });

    const { rerender } = render(
      <SheetViewer sheetId="sheet-1" planSetId="set-1" onBack={() => {}} />
    );

    rerender(<SheetViewer sheetId="sheet-2" planSetId="set-2" onBack={() => {}} />);

    expect(await screen.findByText(/Window Annotation Two/)).toBeInTheDocument();
    expect(screen.getByText("Window Suggestion Two")).toBeInTheDocument();
    expect(screen.getAllByText("Addendum Snapshot").length).toBeGreaterThan(0);
    expect(screen.getByText(/recent: json/i)).toBeInTheDocument();

    staleAnnotationsLoad.resolve([
      buildAnnotation("annotation-1", "sheet-1", "layer-1", "Door Annotation One"),
    ]);
    staleSuggestionsLoad.resolve([
      buildSuggestion("suggestion-1", "sheet-1", "Door Suggestion One"),
    ]);
    staleSnapshotsLoad.resolve([
      buildSnapshot("snapshot-1", "set-1", "Pricing Snapshot"),
    ]);
    staleExportsLoad.resolve([
      buildExport("export-1", "set-1", "csv"),
    ]);
    staleTakeoffItemsLoad.resolve([
      buildTakeoffItem("takeoff-1", "set-1", "sheet-1"),
    ]);
    staleTakeoffSummaryLoad.resolve(buildTakeoffSummary(1));

    await waitFor(() => {
      expect(screen.getByText(/Window Annotation Two/)).toBeInTheDocument();
      expect(screen.getByText("Window Suggestion Two")).toBeInTheDocument();
      expect(screen.getAllByText("Addendum Snapshot").length).toBeGreaterThan(0);
      expect(screen.getByText(/recent: json/i)).toBeInTheDocument();
      expect(screen.queryByText(/Door Annotation One/)).not.toBeInTheDocument();
      expect(screen.queryByText("Door Suggestion One")).not.toBeInTheDocument();
      expect(screen.queryByText("Pricing Snapshot")).not.toBeInTheDocument();
      expect(screen.queryByText(/recent: csv/i)).not.toBeInTheDocument();
    });
  });
});
