/**
 * Plan sheet viewer with zoom/pan and annotation overlay.
 *
 * Coordinate mapping: Annotation geometry is stored in normalized coordinates [0, 1]
 * (e.g. { type: "rectangle", x: 0.2, y: 0.2, width: 0.3, height: 0.15 }).
 * Screen position = normalized * viewport size: screenX = x * pageWidth, screenY = y * pageHeight.
 * This keeps annotations stable across zoom and render size changes.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import {
  acceptSuggestion,
  batchAcceptSuggestions,
  createAnnotation,
  createAnnotationLayer,
  createExport,
  createSnapshot,
  createTakeoffFromAnnotation,
  createTakeoffItem,
  deleteAnnotation,
  deleteTakeoffItem,
  fetchAnnotationLayers,
  fetchAnnotations,
  fetchExportRecords,
  fetchPlanSheetCadPreview,
  fetchPlanSheet,
  fetchSnapshots,
  fetchSuggestions,
  fetchTakeoffItems,
  fetchTakeoffSummary,
  lockSnapshot,
  planSheetFileUrl,
  rejectSuggestion,
  triggerAnalysis,
  updateAnnotation,
  updateAnnotationLayer,
  updatePlanSheet,
  updateTakeoffItem,
} from "../services/preconstruction";
import type {
  AISuggestion,
  AnnotationItem,
  AnnotationLayer as LayerType,
  ExportRecord,
  PlanSheetCadPreviewItem,
  PlanSheet,
  RevisionSnapshot,
  TakeoffItem,
  TakeoffSummary,
} from "../types/api";

// PDF.js worker: CDN URL matching pdfjs-dist version in package.json
if (typeof window !== "undefined" && !pdfjsLib.GlobalWorkerOptions.workerSrc) {
  pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.0.379/pdf.worker.min.mjs";
}

type Props = {
  sheetId: string;
  planSetId: string;
  onBack: () => void;
};

type AnalysisProvider = "mock" | "openai_vision" | "cad_dxf";
const CAD_CANVAS_BASE_WIDTH = 1400;
const CAD_CANVAS_BASE_HEIGHT = 900;

function normToScreen(
  x: number,
  y: number,
  pageWidth: number,
  pageHeight: number
): { x: number; y: number } {
  return { x: x * pageWidth, y: y * pageHeight };
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Derive default category and unit from suggestion label/type (mirrors backend mapping). */
function defaultCategoryUnitForSuggestion(
  label: string | null | undefined,
  suggestionType: string | null | undefined
): { category: string; unit: string } {
  const labelLower = (label ?? "").trim().toLowerCase();
  const map: Record<string, { category: string; unit: string }> = {
    door: { category: "doors", unit: "count" },
    doors: { category: "doors", unit: "count" },
    window: { category: "windows", unit: "count" },
    windows: { category: "windows", unit: "count" },
    "plumbing fixture": { category: "plumbing_fixtures", unit: "count" },
    fixture: { category: "plumbing_fixtures", unit: "count" },
    fixtures: { category: "plumbing_fixtures", unit: "count" },
    "electrical fixture": { category: "electrical_fixtures", unit: "count" },
    "concrete area": { category: "concrete_areas", unit: "square_feet" },
    "concrete slab": { category: "concrete_areas", unit: "square_feet" },
    opening: { category: "openings", unit: "count" },
    openings: { category: "openings", unit: "count" },
    room: { category: "rooms", unit: "count" },
    rooms: { category: "rooms", unit: "count" },
    "linear measurement": { category: "linear_measurements", unit: "linear_feet" },
  };
  if (labelLower && labelLower in map) return map[labelLower];
  for (const [key, value] of Object.entries(map)) {
    const pattern = new RegExp(`\\b${escapeRegExp(key)}\\b`);
    if (pattern.test(labelLower)) return value;
  }
  if (suggestionType === "polygon") return { category: "concrete_areas", unit: "square_feet" };
  if (suggestionType === "polyline") return { category: "linear_measurements", unit: "linear_feet" };
  return { category: "custom", unit: "count" };
}

function drawAnnotation(
  ctx: CanvasRenderingContext2D,
  item: AnnotationItem | { geometry_json: AnnotationItem["geometry_json"]; label?: string },
  pageWidth: number,
  pageHeight: number,
  color = "rgba(59, 130, 246, 0.4)"
) {
  const g = item.geometry_json as Record<string, unknown>;
  if (!g) return;
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 2;

  if (g.type === "point") {
    const x = (g.x as number) * pageWidth;
    const y = (g.y as number) * pageHeight;
    ctx.beginPath();
    ctx.arc(x, y, 6, 0, Math.PI * 2);
    ctx.fill();
  } else if (g.type === "rectangle") {
    const x = (g.x as number) * pageWidth;
    const y = (g.y as number) * pageHeight;
    const w = (g.width as number) * pageWidth;
    const h = (g.height as number) * pageHeight;
    ctx.strokeRect(x, y, w, h);
    ctx.fillRect(x, y, w, h);
  } else if (g.type === "polygon" && Array.isArray(g.points)) {
    const points = g.points as Array<{ x: number; y: number }>;
    if (points.length < 2) return;
    ctx.beginPath();
    const first = normToScreen(points[0].x, points[0].y, pageWidth, pageHeight);
    ctx.moveTo(first.x, first.y);
    for (let i = 1; i < points.length; i++) {
      const p = normToScreen(points[i].x, points[i].y, pageWidth, pageHeight);
      ctx.lineTo(p.x, p.y);
    }
    ctx.closePath();
    ctx.stroke();
    ctx.fill();
  } else if (g.type === "polyline" && Array.isArray(g.points)) {
    const points = g.points as Array<{ x: number; y: number }>;
    if (points.length < 2) return;
    ctx.beginPath();
    const first = normToScreen(points[0].x, points[0].y, pageWidth, pageHeight);
    ctx.moveTo(first.x, first.y);
    for (let i = 1; i < points.length; i++) {
      const p = normToScreen(points[i].x, points[i].y, pageWidth, pageHeight);
      ctx.lineTo(p.x, p.y);
    }
    ctx.stroke();
  }
}

type PlacementMode = "none" | "point" | "rectangle" | "polygon" | "polyline";
type RectCorner = "nw" | "ne" | "sw" | "se";
type GeometryEditHandle =
  | { type: "point" }
  | { type: "rect_move"; offsetX: number; offsetY: number }
  | { type: "rect_corner"; corner: RectCorner }
  | { type: "vertex"; index: number };
type GeometryEditState = {
  annotationId: string;
  originalGeometry: Record<string, unknown>;
  geometry: Record<string, unknown>;
  handle: GeometryEditHandle;
};

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

const TAKEOFF_CATEGORY_OPTIONS = [
  "doors",
  "door_hardware",
  "windows",
  "openings",
  "rooms",
  "plumbing_fixtures",
  "electrical_fixtures",
  "concrete_areas",
  "linear_measurements",
  "custom",
] as const;

const TAKEOFF_UNIT_OPTIONS = ["count", "square_feet", "linear_feet", "cubic_yards", "each", "custom"] as const;

const TAKEOFF_REVIEW_STATE_OPTIONS = ["pending", "accepted", "edited", "rejected"] as const;

function formatTokenLabel(value: string): string {
  if (value === "ai_assisted") return "AI assisted";
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function matchesTakeoffWorkspaceFilters(
  takeoff: Pick<TakeoffItem, "category" | "source" | "review_state">,
  filters: { category: string; source: string; reviewState: string }
): boolean {
  if (filters.category !== "all" && takeoff.category !== filters.category) return false;
  if (filters.source !== "all" && takeoff.source !== filters.source) return false;
  if (filters.reviewState !== "all" && takeoff.review_state !== filters.reviewState) return false;
  return true;
}

export function SheetViewer({ sheetId, planSetId, onBack }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const takeoffWorkspaceRequestRef = useRef(0);
  const [sheet, setSheet] = useState<PlanSheet | null>(null);
  const [layers, setLayers] = useState<LayerType[]>([]);
  const [annotations, setAnnotations] = useState<AnnotationItem[]>([]);
  const [takeoffItems, setTakeoffItems] = useState<TakeoffItem[]>([]);
  const [takeoffSummary, setTakeoffSummary] = useState<TakeoffSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [scale, setScale] = useState(1.2);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef({ x: 0, y: 0 });
  const [pdfDoc, setPdfDoc] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [cadPreviewItems, setCadPreviewItems] = useState<PlanSheetCadPreviewItem[]>([]);
  const [, setPageWidth] = useState(612);
  const [, setPageHeight] = useState(792);
  const [addTakeoffCategory, setAddTakeoffCategory] = useState("doors");
  const [addTakeoffQuantity, setAddTakeoffQuantity] = useState("1");
  const [addTakeoffUnit, setAddTakeoffUnit] = useState("count");
  const [annotationAssemblyProfile, setAnnotationAssemblyProfile] = useState<"auto" | "none" | "door_set" | "window_set" | "fixture_set">("auto");
  const [creating, setCreating] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiRunning, setAiRunning] = useState(false);
  const [batchAccepting, setBatchAccepting] = useState(false);
  const [placementMode, setPlacementMode] = useState<PlacementMode>("none");
  const [placementLabel, setPlacementLabel] = useState("");
  const [rectDragStart, setRectDragStart] = useState<{ x: number; y: number } | null>(null);
  const [rectDragCurrent, setRectDragCurrent] = useState<{ x: number; y: number } | null>(null);
  const [draftPathPoints, setDraftPathPoints] = useState<Array<{ x: number; y: number }>>([]);
  const [geometryEdit, setGeometryEdit] = useState<GeometryEditState | null>(null);
  const [suggestions, setSuggestions] = useState<AISuggestion[]>([]);
  const [snapshots, setSnapshots] = useState<RevisionSnapshot[]>([]);
  const [exports, setExports] = useState<ExportRecord[]>([]);
  const [exportPayload, setExportPayload] = useState<string | null>(null);
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null);
  const [selectedTakeoffId, setSelectedTakeoffId] = useState<string | null>(null);
  const [takeoffCategoryFilter, setTakeoffCategoryFilter] = useState("all");
  const [takeoffSourceFilter, setTakeoffSourceFilter] = useState("all");
  const [takeoffReviewFilter, setTakeoffReviewFilter] = useState("all");
  const [editTakeoffCategory, setEditTakeoffCategory] = useState("doors");
  const [editTakeoffSubcategory, setEditTakeoffSubcategory] = useState("");
  const [editTakeoffUnit, setEditTakeoffUnit] = useState("count");
  const [editTakeoffQuantity, setEditTakeoffQuantity] = useState("1");
  const [editTakeoffCostCode, setEditTakeoffCostCode] = useState("");
  const [editTakeoffBidPackage, setEditTakeoffBidPackage] = useState("");
  const [editTakeoffReviewState, setEditTakeoffReviewState] = useState("pending");
  const [editTakeoffNotes, setEditTakeoffNotes] = useState("");
  const [editingSuggestionId, setEditingSuggestionId] = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [editCategory, setEditCategory] = useState("doors");
  const [editUnit, setEditUnit] = useState("count");
  const [editQuantity, setEditQuantity] = useState("1");
  const [analysisProvider, setAnalysisProvider] = useState<AnalysisProvider>("mock");
  const [calibrationWidth, setCalibrationWidth] = useState("");
  const [calibrationHeight, setCalibrationHeight] = useState("");
  const [calibrationUnit, setCalibrationUnit] = useState<"feet" | "meters">("feet");
  const [savingCalibration, setSavingCalibration] = useState(false);

  const loadSheetAndData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [sheetData, layersData] = await Promise.all([
        fetchPlanSheet(sheetId),
        fetchAnnotationLayers(sheetId),
      ]);
      setSheet(sheetData);
      setAnalysisProvider((prev) => {
        if (sheetData.file_type === "dxf" || sheetData.file_type === "dwg") {
          if (prev === "openai_vision") return "cad_dxf";
          return prev;
        }
        if (sheetData.file_type === "pdf" && prev === "cad_dxf") {
          return "mock";
        }
        return prev;
      });
      setCalibrationWidth(sheetData.calibrated_width != null ? String(sheetData.calibrated_width) : "");
      setCalibrationHeight(sheetData.calibrated_height != null ? String(sheetData.calibrated_height) : "");
      setCalibrationUnit(sheetData.calibrated_unit ?? "feet");
      setLayers(layersData);
      const width = sheetData.file_type === "pdf"
        ? (sheetData.width != null ? Number(sheetData.width) : 612)
        : CAD_CANVAS_BASE_WIDTH;
      const height = sheetData.file_type === "pdf"
        ? (sheetData.height != null ? Number(sheetData.height) : 792)
        : CAD_CANVAS_BASE_HEIGHT;
      setPageWidth(width);
      setPageHeight(height);
      if (sheetData.file_type === "dxf" || sheetData.file_type === "dwg") {
        try {
          const preview = await fetchPlanSheetCadPreview(sheetId);
          setCadPreviewItems(preview.items ?? []);
        } catch (previewError) {
          setCadPreviewItems([]);
          setError(previewError instanceof Error ? previewError.message : "Failed to load CAD preview.");
        }
      } else {
        setCadPreviewItems([]);
      }
      const annList = await fetchAnnotations(sheetId);
      setAnnotations(annList);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load sheet.");
    } finally {
      setLoading(false);
    }
  }, [sheetId, planSetId]);

  const loadTakeoffWorkspace = useCallback(async (preferredTakeoffId?: string | null) => {
    const requestId = ++takeoffWorkspaceRequestRef.current;
    const filters = {
      ...(takeoffCategoryFilter !== "all" ? { category: takeoffCategoryFilter } : {}),
      ...(takeoffSourceFilter !== "all" ? { source: takeoffSourceFilter } : {}),
      ...(takeoffReviewFilter !== "all" ? { review_state: takeoffReviewFilter } : {}),
    };
    try {
      const [list, summary] = await Promise.all([
        fetchTakeoffItems(planSetId, sheetId, filters),
        fetchTakeoffSummary(planSetId, sheetId, filters),
      ]);
      if (requestId !== takeoffWorkspaceRequestRef.current) return list;
      setTakeoffItems(list);
      setTakeoffSummary(summary);
      setSelectedTakeoffId((current) => {
        const nextSelectedId = preferredTakeoffId ?? current;
        if (nextSelectedId && list.some((item) => item.id === nextSelectedId)) return nextSelectedId;
        return list[0]?.id ?? null;
      });
      return list;
    } catch (e) {
      if (requestId !== takeoffWorkspaceRequestRef.current) return [];
      setTakeoffItems([]);
      setTakeoffSummary(null);
      setSelectedTakeoffId(null);
      setError(e instanceof Error ? e.message : "Failed to load takeoff workspace.");
      return [];
    }
  }, [planSetId, sheetId, takeoffCategoryFilter, takeoffSourceFilter, takeoffReviewFilter]);

  const focusTakeoffInWorkspace = useCallback(async (takeoff: Pick<TakeoffItem, "id" | "category" | "source" | "review_state">) => {
    const matchesCurrentFilters = matchesTakeoffWorkspaceFilters(takeoff, {
      category: takeoffCategoryFilter,
      source: takeoffSourceFilter,
      reviewState: takeoffReviewFilter,
    });
    if (matchesCurrentFilters) {
      await loadTakeoffWorkspace(takeoff.id);
      return;
    }
    setSelectedTakeoffId(takeoff.id);
    setTakeoffCategoryFilter("all");
    setTakeoffSourceFilter("all");
    setTakeoffReviewFilter("all");
  }, [loadTakeoffWorkspace, takeoffCategoryFilter, takeoffReviewFilter, takeoffSourceFilter]);

  const refreshSheetAndWorkspace = useCallback(async () => {
    await Promise.all([loadSheetAndData(), loadTakeoffWorkspace()]);
  }, [loadSheetAndData, loadTakeoffWorkspace]);

  useEffect(() => {
    void loadSheetAndData();
  }, [loadSheetAndData]);

  useEffect(() => {
    void loadTakeoffWorkspace();
  }, [loadTakeoffWorkspace]);

  useEffect(() => {
    const selected = takeoffItems.find((item) => item.id === selectedTakeoffId) ?? null;
    if (!selected) {
      setEditTakeoffCategory("doors");
      setEditTakeoffSubcategory("");
      setEditTakeoffUnit("count");
      setEditTakeoffQuantity("1");
      setEditTakeoffCostCode("");
      setEditTakeoffBidPackage("");
      setEditTakeoffReviewState("pending");
      setEditTakeoffNotes("");
      return;
    }
    setEditTakeoffCategory(selected.category || "custom");
    setEditTakeoffSubcategory(selected.subcategory || "");
    setEditTakeoffUnit(selected.unit || "count");
    setEditTakeoffQuantity(selected.quantity || "1");
    setEditTakeoffCostCode(selected.cost_code || "");
    setEditTakeoffBidPackage(selected.bid_package || "");
    setEditTakeoffReviewState(selected.review_state || "pending");
    setEditTakeoffNotes(selected.notes || "");
  }, [selectedTakeoffId, takeoffItems]);

  const addAnnotationWithGeometry = async (
    geometry_json: Record<string, unknown>,
    annotationType: "point" | "rectangle" | "polygon" | "polyline",
    label: string
  ) => {
    if (!sheet) return;
    setCreating(true);
    try {
      let layer = layers[0];
      if (!layer) {
        layer = await createAnnotationLayer({
          project: sheet.project,
          plan_set: planSetId,
          plan_sheet: sheetId,
          name: "Default",
        });
        setLayers((prev) => [...prev, layer]);
      }
      await createAnnotation({
        project: sheet.project,
        plan_sheet: sheetId,
        layer: layer.id,
        annotation_type: annotationType,
        geometry_json,
        label,
      });
      await loadSheetAndData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add annotation.");
    } finally {
      setCreating(false);
    }
  };

  const getNormalizedCoords = (e: React.MouseEvent<HTMLCanvasElement>): { x: number; y: number } | null => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height || !Number.isFinite(rect.width) || !Number.isFinite(rect.height)) return null;
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || x > 1 || y < 0 || y > 1) return null;
    return { x, y };
  };

  const clearPlacementState = useCallback(() => {
    setPlacementMode("none");
    setRectDragStart(null);
    setRectDragCurrent(null);
    setDraftPathPoints([]);
  }, []);

  const commitGeometryEdit = useCallback(async (edit: GeometryEditState) => {
    const before = JSON.stringify(edit.originalGeometry);
    const after = JSON.stringify(edit.geometry);
    if (before === after) return;
    try {
      await updateAnnotation(edit.annotationId, { geometry_json: edit.geometry });
      await loadSheetAndData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update annotation geometry.");
    }
  }, [loadSheetAndData]);

  const applyGeometryEdit = useCallback((edit: GeometryEditState, coords: { x: number; y: number }) => {
    const clamped = { x: clamp01(coords.x), y: clamp01(coords.y) };
    const geometry = edit.originalGeometry;

    if (edit.handle.type === "point") {
      return { ...geometry, type: "point", x: clamped.x, y: clamped.y };
    }

    if (edit.handle.type === "rect_move" && geometry.type === "rectangle") {
      const width = asNumber(geometry.width);
      const height = asNumber(geometry.height);
      if (width == null || height == null) return edit.geometry;
      const x = clamp01(clamped.x - edit.handle.offsetX);
      const y = clamp01(clamped.y - edit.handle.offsetY);
      return {
        ...geometry,
        type: "rectangle",
        x: Math.min(x, 1 - width),
        y: Math.min(y, 1 - height),
        width,
        height,
      };
    }

    if (edit.handle.type === "rect_corner" && geometry.type === "rectangle") {
      const x = asNumber(geometry.x);
      const y = asNumber(geometry.y);
      const width = asNumber(geometry.width);
      const height = asNumber(geometry.height);
      if (x == null || y == null || width == null || height == null) return edit.geometry;
      const left = x;
      const right = x + width;
      const top = y;
      const bottom = y + height;
      let nx = clamped.x;
      let ny = clamped.y;
      let ax = left;
      let ay = top;
      if (edit.handle.corner === "nw") {
        ax = right;
        ay = bottom;
      } else if (edit.handle.corner === "ne") {
        ax = left;
        ay = bottom;
      } else if (edit.handle.corner === "sw") {
        ax = right;
        ay = top;
      } else if (edit.handle.corner === "se") {
        ax = left;
        ay = top;
      }
      nx = clamp01(nx);
      ny = clamp01(ny);
      const rx = Math.min(nx, ax);
      const ry = Math.min(ny, ay);
      const rw = Math.max(0.001, Math.abs(ax - nx));
      const rh = Math.max(0.001, Math.abs(ay - ny));
      return { ...geometry, type: "rectangle", x: rx, y: ry, width: rw, height: rh };
    }

    if (edit.handle.type === "vertex" && Array.isArray(geometry.points)) {
      const vertexIndex = edit.handle.index;
      const points = geometry.points as Array<{ x: number; y: number }>;
      if (vertexIndex < 0 || vertexIndex >= points.length) return edit.geometry;
      const nextPoints = points.map((point, idx) => (idx === vertexIndex ? clamped : point));
      return { ...geometry, points: nextPoints };
    }

    return edit.geometry;
  }, []);

  const startGeometryEdit = useCallback(
    (coords: { x: number; y: number }): GeometryEditState | null => {
      if (!selectedAnnotationId) return null;
      const annotation = annotations.find((item) => item.id === selectedAnnotationId);
      if (!annotation) return null;
      const geometry = annotation.geometry_json as Record<string, unknown>;
      const canvas = canvasRef.current;
      if (!canvas) return null;
      const thresholdPx = 10;
      const pointPx = normToScreen(coords.x, coords.y, canvas.width, canvas.height);

      if (geometry.type === "point") {
        const gx = asNumber(geometry.x);
        const gy = asNumber(geometry.y);
        if (gx == null || gy == null) return null;
        const gpx = normToScreen(gx, gy, canvas.width, canvas.height);
        const distance = Math.hypot(gpx.x - pointPx.x, gpx.y - pointPx.y);
        if (distance <= thresholdPx) {
          return {
            annotationId: annotation.id,
            originalGeometry: geometry,
            geometry,
            handle: { type: "point" },
          };
        }
        return null;
      }

      if (geometry.type === "rectangle") {
        const x = asNumber(geometry.x);
        const y = asNumber(geometry.y);
        const width = asNumber(geometry.width);
        const height = asNumber(geometry.height);
        if (x == null || y == null || width == null || height == null) return null;
        const corners: Record<RectCorner, { x: number; y: number }> = {
          nw: normToScreen(x, y, canvas.width, canvas.height),
          ne: normToScreen(x + width, y, canvas.width, canvas.height),
          sw: normToScreen(x, y + height, canvas.width, canvas.height),
          se: normToScreen(x + width, y + height, canvas.width, canvas.height),
        };
        for (const corner of ["nw", "ne", "sw", "se"] as RectCorner[]) {
          const distance = Math.hypot(corners[corner].x - pointPx.x, corners[corner].y - pointPx.y);
          if (distance <= thresholdPx) {
            return {
              annotationId: annotation.id,
              originalGeometry: geometry,
              geometry,
              handle: { type: "rect_corner", corner },
            };
          }
        }
        if (coords.x >= x && coords.x <= x + width && coords.y >= y && coords.y <= y + height) {
          return {
            annotationId: annotation.id,
            originalGeometry: geometry,
            geometry,
            handle: { type: "rect_move", offsetX: coords.x - x, offsetY: coords.y - y },
          };
        }
        return null;
      }

      if ((geometry.type === "polygon" || geometry.type === "polyline") && Array.isArray(geometry.points)) {
        const points = geometry.points as Array<{ x: unknown; y: unknown }>;
        for (let i = 0; i < points.length; i++) {
          const px = asNumber(points[i]?.x);
          const py = asNumber(points[i]?.y);
          if (px == null || py == null) continue;
          const p = normToScreen(px, py, canvas.width, canvas.height);
          const distance = Math.hypot(p.x - pointPx.x, p.y - pointPx.y);
          if (distance <= thresholdPx) {
            return {
              annotationId: annotation.id,
              originalGeometry: geometry,
              geometry,
              handle: { type: "vertex", index: i },
            };
          }
        }
      }
      return null;
    },
    [annotations, selectedAnnotationId]
  );

  const handleCanvasMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button !== 0 || creating) return;
    const coords = getNormalizedCoords(e);
    if (!coords) return;

    if (placementMode === "point") {
      e.stopPropagation();
      void addAnnotationWithGeometry(
        { type: "point", x: coords.x, y: coords.y },
        "point",
        placementLabel || "Point"
      );
      clearPlacementState();
      return;
    }

    if (placementMode === "rectangle") {
      e.stopPropagation();
      setRectDragStart(coords);
      setRectDragCurrent(coords);
      return;
    }

    if (placementMode === "polygon" || placementMode === "polyline") {
      e.stopPropagation();
      setDraftPathPoints((prev) => [...prev, coords]);
      return;
    }

    const edit = startGeometryEdit(coords);
    if (edit) {
      e.stopPropagation();
      setGeometryEdit(edit);
    }
  };

  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const coords = getNormalizedCoords(e);
    if (!coords) return;

    if (geometryEdit) {
      e.stopPropagation();
      setGeometryEdit((current) => {
        if (!current) return current;
        const updatedGeometry = applyGeometryEdit(current, coords);
        return { ...current, geometry: updatedGeometry };
      });
      return;
    }

    if (placementMode === "rectangle" && rectDragStart) {
      e.stopPropagation();
      setRectDragCurrent(coords);
    }
  };

  const handleCanvasMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button !== 0) return;
    if (geometryEdit) {
      // Let the global mouseup listener commit and clear edit state once.
      return;
    }
    if (placementMode === "rectangle" && rectDragStart && rectDragCurrent) {
      const x = Math.min(rectDragStart.x, rectDragCurrent.x);
      const y = Math.min(rectDragStart.y, rectDragCurrent.y);
      const width = Math.abs(rectDragCurrent.x - rectDragStart.x);
      const height = Math.abs(rectDragCurrent.y - rectDragStart.y);
      if (width > 0.01 && height > 0.01) {
        void addAnnotationWithGeometry(
          { type: "rectangle", x, y, width, height },
          "rectangle",
          placementLabel || "New area"
        );
      }
      clearPlacementState();
    }
  };

  const addAnnotation = (annotationType: PlacementMode, label: string) => {
    if (placementMode !== "none") clearPlacementState();
    setPlacementLabel(label);
    setPlacementMode(annotationType);
  };

  const finishPathAnnotation = () => {
    if (placementMode !== "polygon" && placementMode !== "polyline") return;
    const minPoints = placementMode === "polygon" ? 3 : 2;
    if (draftPathPoints.length < minPoints) {
      setError(
        placementMode === "polygon"
          ? "Polygon requires at least 3 points."
          : "Polyline requires at least 2 points."
      );
      return;
    }
    const points = [...draftPathPoints];
    void addAnnotationWithGeometry(
      { type: placementMode, points },
      placementMode,
      placementLabel || (placementMode === "polygon" ? "New polygon" : "New polyline")
    );
    clearPlacementState();
  };

  const handleDeleteAnnotation = async (annotationId: string) => {
    if (!window.confirm("Delete this annotation? This cannot be undone.")) return;
    try {
      await deleteAnnotation(annotationId);
      setSelectedAnnotationId((id) => (id === annotationId ? null : id));
      await refreshSheetAndWorkspace();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete.");
    }
  };

  const handleCreateTakeoffFromAnnotation = async (annotation: AnnotationItem) => {
    if (!sheet) return;
    setCreating(true);
    setError("");
    try {
      const created = await createTakeoffFromAnnotation(annotation.id, annotationAssemblyProfile);
      await focusTakeoffInWorkspace(created.primary_takeoff);
      const annList = await fetchAnnotations(sheetId);
      setAnnotations(annList);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add takeoff.");
    } finally {
      setCreating(false);
    }
  };

  const handleAddTakeoff = async () => {
    if (!sheet) return;
    setCreating(true);
    setError("");
    try {
      const created = await createTakeoffItem({
        project: sheet.project,
        plan_set: planSetId,
        plan_sheet: sheetId,
        category: addTakeoffCategory,
        unit: addTakeoffUnit,
        quantity: addTakeoffQuantity,
      });
      setAddTakeoffQuantity("1");
      await focusTakeoffInWorkspace(created);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add takeoff.");
    } finally {
      setCreating(false);
    }
  };

  const handleSaveTakeoff = async () => {
    if (!selectedTakeoffId) return;
    setCreating(true);
    setError("");
    try {
      const updated = await updateTakeoffItem(selectedTakeoffId, {
        category: editTakeoffCategory,
        subcategory: editTakeoffSubcategory,
        unit: editTakeoffUnit,
        quantity: editTakeoffQuantity,
        cost_code: editTakeoffCostCode,
        bid_package: editTakeoffBidPackage,
        review_state: editTakeoffReviewState,
        notes: editTakeoffNotes,
      });
      await focusTakeoffInWorkspace(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save takeoff.");
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteTakeoff = async () => {
    if (!selectedTakeoffId) return;
    if (!window.confirm("Delete this takeoff item?")) return;
    setCreating(true);
    setError("");
    try {
      await deleteTakeoffItem(selectedTakeoffId);
      await loadTakeoffWorkspace();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete takeoff.");
    } finally {
      setCreating(false);
    }
  };

  const loadSuggestions = useCallback(async () => {
    const list = await fetchSuggestions(sheetId);
    setSuggestions(list);
  }, [sheetId]);

  const handleLayerVisibilityToggle = async (layer: LayerType) => {
    try {
      await updateAnnotationLayer(layer.id, { is_visible: !layer.is_visible });
      const list = await fetchAnnotationLayers(sheetId);
      setLayers(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update layer.");
    }
  };

  const loadSnapshotsAndExports = useCallback(async () => {
    const [s, e] = await Promise.all([fetchSnapshots(planSetId), fetchExportRecords(planSetId)]);
    setSnapshots(s);
    setExports(e);
  }, [planSetId]);

  useEffect(() => {
    if (!rectDragStart || placementMode !== "rectangle") return;
    const onGlobalMouseUp = () => {
      clearPlacementState();
    };
    window.addEventListener("mouseup", onGlobalMouseUp);
    return () => window.removeEventListener("mouseup", onGlobalMouseUp);
  }, [rectDragStart, placementMode, clearPlacementState]);

  useEffect(() => {
    if (!geometryEdit) return;
    const onGlobalMouseUp = () => {
      setGeometryEdit((current) => {
        if (!current) return current;
        void commitGeometryEdit(current);
        return null;
      });
    };
    window.addEventListener("mouseup", onGlobalMouseUp);
    return () => window.removeEventListener("mouseup", onGlobalMouseUp);
  }, [geometryEdit, commitGeometryEdit]);

  useEffect(() => {
    if (sheetId) void loadSuggestions();
  }, [sheetId, loadSuggestions]);
  useEffect(() => {
    void loadSnapshotsAndExports();
  }, [loadSnapshotsAndExports]);

  const handleSaveCalibration = async () => {
    if (!sheet) return;
    setSavingCalibration(true);
    setError("");
    try {
      const width = calibrationWidth.trim();
      const height = calibrationHeight.trim();
      const widthNum = width === "" ? null : Number(width);
      const heightNum = height === "" ? null : Number(height);
      if (widthNum != null && (!Number.isFinite(widthNum) || widthNum <= 0)) {
        throw new Error("Calibrated width must be a positive number.");
      }
      if (heightNum != null && (!Number.isFinite(heightNum) || heightNum <= 0)) {
        throw new Error("Calibrated height must be a positive number.");
      }
      if ((widthNum != null && heightNum == null) || (widthNum == null && heightNum != null)) {
        throw new Error("Provide both calibrated width and calibrated height, or leave both empty.");
      }
      const updated = await updatePlanSheet(sheetId, {
        calibrated_width: widthNum,
        calibrated_height: heightNum,
        calibrated_unit: calibrationUnit,
      });
      setSheet(updated);
      setCalibrationWidth(updated.calibrated_width != null ? String(updated.calibrated_width) : "");
      setCalibrationHeight(updated.calibrated_height != null ? String(updated.calibrated_height) : "");
      setCalibrationUnit(updated.calibrated_unit ?? "feet");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save calibration.");
    } finally {
      setSavingCalibration(false);
    }
  };

  const handleRunAnalysis = async () => {
    if ((sheet?.file_type === "dxf" || sheet?.file_type === "dwg") && analysisProvider === "openai_vision") {
      setError("OpenAI vision analysis currently supports PDF plan sheets only.");
      return;
    }
    if (sheet?.file_type === "pdf" && analysisProvider === "cad_dxf") {
      setError("CAD analysis requires a DXF or DWG plan sheet.");
      return;
    }
    setAiRunning(true);
    setError("");
    try {
      await triggerAnalysis(sheetId, aiPrompt, analysisProvider);
      await loadSuggestions();
      await loadSheetAndData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed.");
    } finally {
      setAiRunning(false);
    }
  };

  const handleAcceptSuggestion = async (suggestionId: string) => {
    setError("");
    try {
      const result = await acceptSuggestion(suggestionId);
      await loadSuggestions();
      await loadSheetAndData();
      await focusTakeoffInWorkspace(result.takeoff);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to accept.");
    }
  };

  const handleRejectSuggestion = async (suggestionId: string) => {
    if (!window.confirm("Reject this suggestion? This cannot be undone.")) return;
    try {
      await rejectSuggestion(suggestionId);
      setEditingSuggestionId(null);
      await loadSuggestions();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reject.");
    }
  };

  const startEditingSuggestion = (s: AISuggestion) => {
    setEditingSuggestionId(s.id);
    setEditLabel(s.label || "");
    const { category, unit } = defaultCategoryUnitForSuggestion(s.label, s.suggestion_type);
    setEditCategory(category);
    setEditUnit(unit);
    setEditQuantity("1");
  };

  const handleAcceptWithEdits = async (suggestionId: string) => {
    setError("");
    try {
      const result = await acceptSuggestion(suggestionId, {
        label: editLabel,
        category: editCategory,
        unit: editUnit,
        quantity: editQuantity,
      });
      setEditingSuggestionId(null);
      await loadSuggestions();
      await loadSheetAndData();
      await focusTakeoffInWorkspace(result.takeoff);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to accept with edits.");
    }
  };

  const handleBatchAccept = async () => {
    setBatchAccepting(true);
    setError("");
    try {
      const result = await batchAcceptSuggestions(sheetId, 0.85);
      if (result.accepted_count > 0) {
        await loadSuggestions();
        await refreshSheetAndWorkspace();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to batch accept.");
    } finally {
      setBatchAccepting(false);
    }
  };

  const handleCreateSnapshot = async () => {
    if (!sheet) return;
    setCreating(true);
    try {
      await createSnapshot({ project: sheet.project, plan_set: planSetId, name: `Snapshot ${new Date().toISOString().slice(0, 10)}` });
      await loadSnapshotsAndExports();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create snapshot.");
    } finally {
      setCreating(false);
    }
  };

  const handleLockSnapshot = async (snapshotId: string) => {
    try {
      await lockSnapshot(snapshotId);
      await loadSnapshotsAndExports();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to lock.");
    }
  };

  const handleExport = async (exportType: "json" | "csv") => {
    setCreating(true);
    setError("");
    try {
      const result = await createExport({ plan_set: planSetId, export_type: exportType });
      setExportPayload(typeof result.payload === "string" ? result.payload : JSON.stringify(result.payload, null, 2));
      await loadSnapshotsAndExports();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed.");
    } finally {
      setCreating(false);
    }
  };

  const drawCadReference = useCallback((ctx: CanvasRenderingContext2D, pw: number, ph: number) => {
    cadPreviewItems.forEach((item) => {
      drawAnnotation(
        ctx,
        { geometry_json: item.geometry_json, label: item.label },
        pw,
        ph,
        "rgba(15, 23, 42, 0.18)"
      );
    });
  }, [cadPreviewItems]);

  const drawInteractiveOverlays = useCallback((ctx: CanvasRenderingContext2D, pw: number, ph: number) => {
    const visibleLayers = layers.filter((l) => l.is_visible);
    const layerIds = new Set(visibleLayers.map((l) => l.id));
    const toDraw = annotations.filter((a) => layerIds.has(a.layer));
    toDraw.forEach((item) => {
      if (geometryEdit && item.id === geometryEdit.annotationId) {
        drawAnnotation(
          ctx,
          { geometry_json: geometryEdit.geometry, label: item.label },
          pw,
          ph,
          "rgba(16, 185, 129, 0.35)"
        );
        return;
      }
      drawAnnotation(ctx, item, pw, ph);
    });

    if (rectDragStart && rectDragCurrent) {
      const x = Math.min(rectDragStart.x, rectDragCurrent.x);
      const y = Math.min(rectDragStart.y, rectDragCurrent.y);
      const width = Math.abs(rectDragCurrent.x - rectDragStart.x);
      const height = Math.abs(rectDragCurrent.y - rectDragStart.y);
      drawAnnotation(
        ctx,
        { geometry_json: { type: "rectangle", x, y, width, height }, label: "" },
        pw,
        ph,
        "rgba(59, 130, 246, 0.3)"
      );
    }

    if ((placementMode === "polygon" || placementMode === "polyline") && draftPathPoints.length > 0) {
      drawAnnotation(
        ctx,
        { geometry_json: { type: placementMode, points: draftPathPoints }, label: "" },
        pw,
        ph,
        "rgba(59, 130, 246, 0.3)"
      );
      ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
      draftPathPoints.forEach((point) => {
        const p = normToScreen(point.x, point.y, pw, ph);
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    const selected = toDraw.find((a) => a.id === selectedAnnotationId);
    if (selected) {
      const selectedGeometry =
        geometryEdit && geometryEdit.annotationId === selected.id
          ? geometryEdit.geometry
          : (selected.geometry_json as Record<string, unknown>);
      const drawHandle = (xNorm: number, yNorm: number) => {
        const p = normToScreen(xNorm, yNorm, pw, ph);
        const size = 8;
        ctx.fillStyle = "#f8fafc";
        ctx.strokeStyle = "#0f172a";
        ctx.lineWidth = 1;
        ctx.fillRect(p.x - size / 2, p.y - size / 2, size, size);
        ctx.strokeRect(p.x - size / 2, p.y - size / 2, size, size);
      };
      if (selectedGeometry.type === "point") {
        const x = asNumber(selectedGeometry.x);
        const y = asNumber(selectedGeometry.y);
        if (x != null && y != null) drawHandle(x, y);
      } else if (selectedGeometry.type === "rectangle") {
        const x = asNumber(selectedGeometry.x);
        const y = asNumber(selectedGeometry.y);
        const width = asNumber(selectedGeometry.width);
        const height = asNumber(selectedGeometry.height);
        if (x != null && y != null && width != null && height != null) {
          drawHandle(x, y);
          drawHandle(x + width, y);
          drawHandle(x, y + height);
          drawHandle(x + width, y + height);
        }
      } else if ((selectedGeometry.type === "polygon" || selectedGeometry.type === "polyline") && Array.isArray(selectedGeometry.points)) {
        const points = selectedGeometry.points as Array<{ x: unknown; y: unknown }>;
        points.forEach((point) => {
          const x = asNumber(point.x);
          const y = asNumber(point.y);
          if (x != null && y != null) drawHandle(x, y);
        });
      }
    }
  }, [
    layers,
    annotations,
    geometryEdit,
    rectDragStart,
    rectDragCurrent,
    placementMode,
    draftPathPoints,
    selectedAnnotationId,
  ]);

  useEffect(() => {
    if (!sheet) return;
    if (sheet.file_type !== "pdf") {
      setPdfDoc(null);
      return;
    }
    const url = planSheetFileUrl(sheetId);
    pdfjsLib.getDocument({ url, withCredentials: true }).promise.then((doc) => {
      setPdfDoc(doc);
    }).catch((e) => {
      setError(e instanceof Error ? e.message : "Failed to load PDF.");
    });
  }, [sheet, sheetId]);

  useEffect(() => {
    if (!pdfDoc || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    pdfDoc.getPage(1).then((page) => {
      const viewport = page.getViewport({ scale });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const renderContext = { canvasContext: ctx, viewport };
      const pw = viewport.width;
      const ph = viewport.height;
      const drawOverlays = () => drawInteractiveOverlays(ctx, pw, ph);
      const task = page.render(renderContext);
      if (task.promise) {
        task.promise.then(drawOverlays);
      } else {
        drawOverlays();
      }
    });
  }, [
    pdfDoc,
    scale,
    drawInteractiveOverlays,
  ]);

  useEffect(() => {
    if (!sheet || sheet.file_type === "pdf" || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = Math.max(700, Math.round(CAD_CANVAS_BASE_WIDTH * scale));
    const height = Math.max(450, Math.round(CAD_CANVAS_BASE_HEIGHT * scale));
    canvas.width = width;
    canvas.height = height;

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);

    // Lightweight construction-grid background for CAD canvas readability.
    ctx.strokeStyle = "rgba(148, 163, 184, 0.18)";
    ctx.lineWidth = 1;
    const gridStep = Math.max(30, Math.round(60 * scale));
    for (let x = 0; x <= width; x += gridStep) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 0; y <= height; y += gridStep) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    drawCadReference(ctx, width, height);
    drawInteractiveOverlays(ctx, width, height);
  }, [sheet, scale, drawCadReference, drawInteractiveOverlays]);

  const selectedTakeoff = takeoffItems.find((item) => item.id === selectedTakeoffId) ?? null;

  if (loading && !sheet) {
    return (
      <section className="card">
        <button type="button" onClick={onBack}>Back to plan set</button>
        <p>Loading sheet...</p>
      </section>
    );
  }

  if (error && !sheet) {
    return (
      <section className="card">
        <button type="button" onClick={onBack}>Back to plan set</button>
        <p className="error-text">{error}</p>
      </section>
    );
  }

  return (
    <section className="card sheet-viewer-container">
      <div className="row">
        <button type="button" onClick={onBack}>Back to plan set</button>
        <span>Zoom:</span>
        <button type="button" onClick={() => setScale((s) => Math.max(0.5, s - 0.2))}>-</button>
        <span>{Math.round(scale * 100)}%</span>
        <button type="button" onClick={() => setScale((s) => Math.min(3, s + 0.2))}>+</button>
      </div>
      {error && <p className="error-text">{error}</p>}
      {sheet?.file_type !== "pdf" && (
        <p className="empty-hint">
          CAD preview mode is active. Entity geometry is rendered from parsed DXF data (DWG requires configured
          converter on the backend).
        </p>
      )}
      <div
        ref={containerRef}
        className="sheet-viewer-canvas-wrap"
        style={{
          overflow: "auto",
          maxHeight: "70vh",
          cursor:
            placementMode !== "none"
              ? placementMode === "point"
                ? "crosshair"
                : "crosshair"
              : geometryEdit
                ? "grabbing"
              : isPanning
                ? "grabbing"
                : "grab",
        }}
        onMouseDown={(e) => {
          if (e.button !== 0 || placementMode !== "none" || geometryEdit) return;
          setIsPanning(true);
          panStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
        }}
        onMouseMove={(e) => {
          if (!isPanning) return;
          setPan({ x: e.clientX - panStartRef.current.x, y: e.clientY - panStartRef.current.y });
        }}
        onMouseUp={() => setIsPanning(false)}
        onMouseLeave={() => setIsPanning(false)}
      >
        <div style={{ transform: `translate(${pan.x}px, ${pan.y}px)`, display: "inline-block" }}>
          <canvas
            ref={canvasRef}
            style={{ display: "block" }}
            onMouseDown={handleCanvasMouseDown}
            onMouseMove={handleCanvasMouseMove}
            onMouseUp={handleCanvasMouseUp}
            onMouseLeave={() => {
              if (placementMode === "rectangle" && rectDragStart) {
                clearPlacementState();
              }
            }}
          />
        </div>
      </div>
      <div className="row sheet-viewer-sidebars">
        <div className="card" style={{ flex: "0 0 200px" }}>
          <h4>Layers</h4>
          {layers.length === 0 ? (
            <p className="empty-hint">No layers yet.</p>
          ) : (
            <ul style={{ listStyle: "none", padding: 0 }}>
              {layers.map((layer) => (
                <li key={layer.id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={layer.is_visible}
                      onChange={() => void handleLayerVisibilityToggle(layer)}
                      aria-label={`Toggle ${layer.name} visibility`}
                    />
                    {layer.name}
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="card" style={{ flex: "1" }}>
          <h4>Takeoff workspace</h4>
          {takeoffSummary && (
            <>
              <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
                <div className="card" style={{ flex: "1 1 120px", margin: 0 }}>
                  <strong>{takeoffSummary.total_items}</strong>
                  <div className="empty-hint">Visible items</div>
                </div>
                <div className="card" style={{ flex: "1 1 120px", margin: 0 }}>
                  <strong>{takeoffSummary.pending_items}</strong>
                  <div className="empty-hint">Pending review</div>
                </div>
                <div className="card" style={{ flex: "1 1 120px", margin: 0 }}>
                  <strong>{takeoffSummary.ai_assisted_items}</strong>
                  <div className="empty-hint">AI-assisted</div>
                </div>
                <div className="card" style={{ flex: "1 1 120px", margin: 0 }}>
                  <strong>{takeoffSummary.linked_annotation_items}</strong>
                  <div className="empty-hint">Linked to annotation</div>
                </div>
              </div>
              <p className="empty-hint" style={{ marginTop: 0 }}>
                Unit totals:{" "}
                {takeoffSummary.unit_totals.length > 0
                  ? takeoffSummary.unit_totals.map((row) => `${row.quantity_total} ${formatTokenLabel(row.unit)} (${row.item_count})`).join(" | ")
                  : "No quantified items yet."}
              </p>
              {takeoffSummary.category_totals.length > 0 && (
                <p className="empty-hint" style={{ marginTop: 0 }}>
                  Category rollup:{" "}
                  {takeoffSummary.category_totals
                    .slice(0, 6)
                    .map((row) => `${formatTokenLabel(row.category)} ${row.quantity_total} ${formatTokenLabel(row.unit)}`)
                    .join(" | ")}
                  {takeoffSummary.category_totals.length > 6 ? " | ..." : ""}
                </p>
              )}
            </>
          )}
          <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
            <select
              value={takeoffReviewFilter}
              onChange={(e) => setTakeoffReviewFilter(e.target.value)}
              aria-label="Takeoff review filter"
            >
              <option value="all">All review states</option>
              {TAKEOFF_REVIEW_STATE_OPTIONS.map((state) => (
                <option key={state} value={state}>
                  {formatTokenLabel(state)}
                </option>
              ))}
            </select>
            <select
              value={takeoffSourceFilter}
              onChange={(e) => setTakeoffSourceFilter(e.target.value)}
              aria-label="Takeoff source filter"
            >
              <option value="all">All sources</option>
              <option value="manual">Manual</option>
              <option value="ai_assisted">AI assisted</option>
            </select>
            <select
              value={takeoffCategoryFilter}
              onChange={(e) => setTakeoffCategoryFilter(e.target.value)}
              aria-label="Takeoff category filter"
            >
              <option value="all">All categories</option>
              {TAKEOFF_CATEGORY_OPTIONS.map((category) => (
                <option key={category} value={category}>
                  {formatTokenLabel(category)}
                </option>
              ))}
            </select>
          </div>
          <div className="row sheet-viewer-sidebars" style={{ alignItems: "flex-start", gap: "0.75rem" }}>
            <div style={{ flex: "0 0 280px" }}>
              {takeoffItems.length === 0 ? (
                <p className="empty-hint">No takeoff items match the current filters on this sheet yet.</p>
              ) : (
                <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                  {takeoffItems.map((t) => (
                    <li key={t.id} style={{ marginBottom: "0.5rem" }}>
                      <button
                        type="button"
                        className={`report-row ${selectedTakeoffId === t.id ? "selected" : ""}`}
                        style={{ width: "100%", textAlign: "left" }}
                        onClick={() => setSelectedTakeoffId(t.id)}
                      >
                        <strong>{formatTokenLabel(t.category)}</strong>
                        <div style={{ fontSize: "0.9rem" }}>{t.quantity} {formatTokenLabel(t.unit)}</div>
                        <div className="empty-hint">
                          {formatTokenLabel(t.review_state)} | {formatTokenLabel(t.source)}
                          {t.cost_code ? ` | CC ${t.cost_code}` : ""}
                          {t.bid_package ? ` | ${t.bid_package}` : ""}
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div style={{ flex: "1" }}>
              <h5 style={{ marginTop: 0, marginBottom: "0.5rem" }}>Selected takeoff</h5>
              {selectedTakeoff ? (
                <>
                  <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
                    <select value={editTakeoffCategory} onChange={(e) => setEditTakeoffCategory(e.target.value)} aria-label="Takeoff category">
                      {TAKEOFF_CATEGORY_OPTIONS.map((category) => (
                        <option key={category} value={category}>
                          {formatTokenLabel(category)}
                        </option>
                      ))}
                    </select>
                    <input
                      type="text"
                      value={editTakeoffSubcategory}
                      onChange={(e) => setEditTakeoffSubcategory(e.target.value)}
                      placeholder="Subcategory"
                      aria-label="Takeoff subcategory"
                      style={{ minWidth: "10rem" }}
                    />
                    <input
                      type="text"
                      value={editTakeoffQuantity}
                      onChange={(e) => setEditTakeoffQuantity(e.target.value)}
                      placeholder="Qty"
                      aria-label="Takeoff quantity"
                      style={{ width: "5rem" }}
                    />
                    <select value={editTakeoffUnit} onChange={(e) => setEditTakeoffUnit(e.target.value)} aria-label="Takeoff unit">
                      {TAKEOFF_UNIT_OPTIONS.map((unit) => (
                        <option key={unit} value={unit}>
                          {formatTokenLabel(unit)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap", marginTop: "0.5rem" }}>
                    <input
                      type="text"
                      value={editTakeoffCostCode}
                      onChange={(e) => setEditTakeoffCostCode(e.target.value)}
                      placeholder="Cost code"
                      aria-label="Takeoff cost code"
                      style={{ minWidth: "8rem" }}
                    />
                    <input
                      type="text"
                      value={editTakeoffBidPackage}
                      onChange={(e) => setEditTakeoffBidPackage(e.target.value)}
                      placeholder="Bid package"
                      aria-label="Takeoff bid package"
                      style={{ minWidth: "10rem" }}
                    />
                    <select value={editTakeoffReviewState} onChange={(e) => setEditTakeoffReviewState(e.target.value)} aria-label="Takeoff review state">
                      {TAKEOFF_REVIEW_STATE_OPTIONS.map((state) => (
                        <option key={state} value={state}>
                          {formatTokenLabel(state)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <textarea
                    value={editTakeoffNotes}
                    onChange={(e) => setEditTakeoffNotes(e.target.value)}
                    placeholder="Estimator notes"
                    aria-label="Takeoff notes"
                    style={{ width: "100%", minHeight: "5rem", marginTop: "0.5rem" }}
                  />
                  <p className="empty-hint" style={{ marginTop: "0.5rem" }}>
                    Source: {formatTokenLabel(selectedTakeoff.source)} | Current review state: {formatTokenLabel(selectedTakeoff.review_state)}
                  </p>
                  <div className="row">
                    <button type="button" onClick={() => void handleSaveTakeoff()} disabled={creating}>
                      Save takeoff
                    </button>
                    <button type="button" onClick={() => void handleDeleteTakeoff()} disabled={creating}>
                      Delete
                    </button>
                  </div>
                </>
              ) : (
                <p className="empty-hint">Select a takeoff item to edit quantity, review state, cost code, or bid package.</p>
              )}
            </div>
          </div>
          <div className="row" style={{ marginTop: "0.75rem", gap: "0.5rem", flexWrap: "wrap" }}>
            <select
              value={addTakeoffCategory}
              onChange={(e) => setAddTakeoffCategory(e.target.value)}
              aria-label="Category"
            >
              <option value="doors">Doors</option>
              <option value="door_hardware">Door hardware</option>
              <option value="windows">Windows</option>
              <option value="plumbing_fixtures">Plumbing</option>
              <option value="electrical_fixtures">Electrical</option>
              <option value="concrete_areas">Concrete</option>
              <option value="linear_measurements">Linear</option>
              <option value="custom">Custom</option>
            </select>
            <input
              type="text"
              value={addTakeoffQuantity}
              onChange={(e) => setAddTakeoffQuantity(e.target.value)}
              placeholder="Qty"
              aria-label="Quantity"
              style={{ width: "4rem" }}
            />
            <select
              value={addTakeoffUnit}
              onChange={(e) => setAddTakeoffUnit(e.target.value)}
              aria-label="Unit"
            >
              <option value="count">Count</option>
              <option value="square_feet">SF</option>
              <option value="linear_feet">LF</option>
              <option value="cubic_yards">CY</option>
              <option value="each">Each</option>
              <option value="custom">Custom</option>
            </select>
            <button type="button" onClick={() => void handleAddTakeoff()} disabled={creating}>
              Add takeoff
            </button>
          </div>
        </div>
      </div>
      <div className="row sheet-viewer-sidebars">
        <div className="card" style={{ flex: "1" }}>
          <h4>Sheet calibration</h4>
          <p className="empty-hint" style={{ marginTop: 0 }}>
            Set full-sheet real-world size to auto-calculate area/linear quantities for accepted AI suggestions.
          </p>
          <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
            <input
              type="text"
              value={calibrationWidth}
              onChange={(e) => setCalibrationWidth(e.target.value)}
              placeholder="Width"
              aria-label="Calibrated width"
              style={{ width: "6rem" }}
            />
            <input
              type="text"
              value={calibrationHeight}
              onChange={(e) => setCalibrationHeight(e.target.value)}
              placeholder="Height"
              aria-label="Calibrated height"
              style={{ width: "6rem" }}
            />
            <select
              value={calibrationUnit}
              onChange={(e) => setCalibrationUnit(e.target.value as "feet" | "meters")}
              aria-label="Calibration unit"
            >
              <option value="feet">Feet</option>
              <option value="meters">Meters</option>
            </select>
            <button type="button" onClick={() => void handleSaveCalibration()} disabled={savingCalibration}>
              {savingCalibration ? "Saving..." : "Save calibration"}
            </button>
          </div>
        </div>
      </div>
      <div className="row sheet-viewer-annotation-tools" style={{ alignItems: "center", gap: "0.5rem" }}>
        <button
          type="button"
          onClick={() => addAnnotation("point", "Point")}
          disabled={creating}
          className={placementMode === "point" ? "selected" : ""}
        >
          Add point
        </button>
        <button
          type="button"
          onClick={() => addAnnotation("rectangle", "New area")}
          disabled={creating}
          className={placementMode === "rectangle" ? "selected" : ""}
        >
          Add rectangle
        </button>
        <button
          type="button"
          onClick={() => addAnnotation("polygon", "New polygon")}
          disabled={creating}
          className={placementMode === "polygon" ? "selected" : ""}
        >
          Add polygon
        </button>
        <button
          type="button"
          onClick={() => addAnnotation("polyline", "New polyline")}
          disabled={creating}
          className={placementMode === "polyline" ? "selected" : ""}
        >
          Add polyline
        </button>
        {placementMode !== "none" && (
          <span style={{ fontSize: "0.9rem", color: "#64748b" }}>
            {placementMode === "point"
              ? "Click on the plan to place a point"
              : placementMode === "rectangle"
                ? "Click and drag on the plan to draw a rectangle"
                : placementMode === "polygon"
                  ? `Click to add polygon vertices (${draftPathPoints.length} points).`
                  : `Click to add polyline vertices (${draftPathPoints.length} points).`}
          </span>
        )}
        {(placementMode === "polygon" || placementMode === "polyline") && (
          <>
            <button
              type="button"
              onClick={finishPathAnnotation}
              disabled={creating || (placementMode === "polygon" ? draftPathPoints.length < 3 : draftPathPoints.length < 2)}
            >
              Finish shape
            </button>
            <button
              type="button"
              onClick={() => setDraftPathPoints((prev) => prev.slice(0, -1))}
              disabled={draftPathPoints.length === 0}
            >
              Undo point
            </button>
          </>
        )}
        {placementMode !== "none" && (
          <button type="button" onClick={clearPlacementState}>
            Cancel
          </button>
        )}
      </div>
      <div className="row sheet-viewer-sidebars">
        <div className="card" style={{ flex: "0 0 220px" }}>
          <h4>Annotations</h4>
          {annotations.length === 0 ? (
            <p className="empty-hint">No annotations yet. Add a point, rectangle, polygon, or polyline above.</p>
          ) : (
            <ul style={{ listStyle: "none", padding: 0 }}>
              {annotations.map((ann) => (
                <li key={ann.id}>
                  <button
                    type="button"
                    className={`report-row ${selectedAnnotationId === ann.id ? "selected" : ""}`}
                    style={{ width: "100%", textAlign: "left" }}
                    onClick={() => setSelectedAnnotationId(ann.id)}
                  >
                    {ann.label || ann.annotation_type} ({ann.source})
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="card" style={{ flex: "1" }}>
          <h4>Annotation inspector</h4>
          {selectedAnnotationId ? (() => {
            const ann = annotations.find((a) => a.id === selectedAnnotationId);
            if (!ann) return <p className="empty-hint">Select an annotation.</p>;
            return (
              <div>
                <p><strong>Type:</strong> {ann.annotation_type}</p>
                <p><strong>Label:</strong> {ann.label || "-"}</p>
                <p><strong>Notes:</strong> {ann.notes || "-"}</p>
                <p><strong>Source:</strong> {ann.source}</p>
                <p><strong>Review state:</strong> {ann.review_state}</p>
                <p className="empty-hint" style={{ margin: "0.25rem 0 0.5rem" }}>
                  Drag on-canvas handles to adjust geometry and save.
                </p>
                <div className="row" style={{ marginBottom: "0.5rem" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    Assembly:
                    <select
                      value={annotationAssemblyProfile}
                      onChange={(e) => setAnnotationAssemblyProfile(e.target.value as "auto" | "none" | "door_set" | "window_set" | "fixture_set")}
                      aria-label="Annotation assembly profile"
                    >
                      <option value="auto">Auto</option>
                      <option value="none">None (single line)</option>
                      <option value="door_set">Door set</option>
                      <option value="window_set">Window set</option>
                      <option value="fixture_set">Fixture set</option>
                    </select>
                  </label>
                </div>
                <div className="row">
                  <button type="button" onClick={() => void handleCreateTakeoffFromAnnotation(ann)} disabled={creating}>
                    Create takeoff package
                  </button>
                  <button type="button" onClick={() => void handleDeleteAnnotation(ann.id)}>
                    Delete
                  </button>
                </div>
              </div>
            );
          })() : (
            <p className="empty-hint">Select an annotation from the list to inspect or create takeoff.</p>
          )}
        </div>
      </div>

      <hr style={{ margin: "1.5rem 0" }} />
      <h4>AI suggestion review</h4>
      <div style={{ marginBottom: "0.5rem" }}>
        <span style={{ fontSize: "0.9rem", color: "#64748b", marginRight: "0.5rem" }}>Quick prompts:</span>
        {[
          "Find all doors",
          "Identify windows",
          "Highlight plumbing fixtures",
          "Mark electrical fixtures",
          "Shade concrete slab areas",
          "Outline rooms",
          "Find linear measurements",
        ].map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => setAiPrompt(prompt)}
            style={{ margin: "0.25rem 0.25rem 0.25rem 0", padding: "0.25rem 0.5rem", fontSize: "0.85rem" }}
          >
            {prompt}
          </button>
        ))}
      </div>
      <div className="row">
        <select
          value={analysisProvider}
          onChange={(e) => setAnalysisProvider(e.target.value as AnalysisProvider)}
          aria-label="Analysis provider"
        >
          <option value="mock">Mock provider</option>
          <option value="openai_vision" disabled={sheet?.file_type !== "pdf"}>
            OpenAI vision provider (PDF)
          </option>
          <option value="cad_dxf" disabled={sheet?.file_type !== "dxf" && sheet?.file_type !== "dwg"}>
            CAD provider (DXF/DWG)
          </option>
        </select>
        <input
          type="text"
          value={aiPrompt}
          onChange={(e) => setAiPrompt(e.target.value)}
          placeholder="e.g. highlight all doors, find plumbing fixtures, mark openings, identify windows"
          aria-label="Analysis prompt"
          style={{ flex: 1, minWidth: "12rem" }}
        />
        <button type="button" onClick={() => void handleRunAnalysis()} disabled={aiRunning}>
          {aiRunning ? "Running..." : "Run analysis"}
        </button>
      </div>
      {suggestions.length > 0 && (
        <>
          <div className="row" style={{ alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
            <p className="empty-hint" style={{ margin: 0 }}>
              Pending: {suggestions.filter((s) => s.decision_state === "pending").length} | Accepted: {suggestions.filter((s) => s.decision_state === "accepted").length} | Rejected: {suggestions.filter((s) => s.decision_state === "rejected").length} | Edited: {suggestions.filter((s) => s.decision_state === "edited").length}
            </p>
            <button
              type="button"
              onClick={() => void handleBatchAccept()}
              disabled={batchAccepting || suggestions.filter((s) => s.decision_state === "pending").length === 0}
            >
              {batchAccepting ? "Accepting..." : "Accept all high-confidence (>=85%)"}
            </button>
          </div>
          <ul style={{ listStyle: "none", padding: 0 }}>
            {[...suggestions]
              .sort((a, b) => (a.decision_state === "pending" ? (b.decision_state === "pending" ? 0 : -1) : b.decision_state === "pending" ? 1 : 0))
              .map((s) => (
                <li key={s.id} className="card" style={{ marginBottom: "0.75rem", padding: "0.75rem" }}>
                  <div>
                    <strong>{s.label || s.suggestion_type}</strong>
                    <span style={{ marginLeft: "0.5rem", fontSize: "0.9rem" }}>({s.suggestion_type}, {(s.confidence != null ? Number(s.confidence) * 100 : 0).toFixed(0)}%)</span>
                  </div>
                  {s.rationale && <p style={{ margin: "0.25rem 0 0.5rem", fontSize: "0.9rem", color: "#64748b" }}>{s.rationale}</p>}
                  {editingSuggestionId === s.id ? (
                    <div className="row sheet-viewer-sidebars" style={{ flexWrap: "wrap", gap: "0.5rem", marginTop: "0.5rem" }}>
                      <input
                        type="text"
                        value={editLabel}
                        onChange={(e) => setEditLabel(e.target.value)}
                        placeholder="Label"
                        aria-label="Label"
                        style={{ minWidth: "8rem" }}
                      />
                      <select value={editCategory} onChange={(e) => setEditCategory(e.target.value)} aria-label="Category">
                        <option value="doors">Doors</option>
                        <option value="windows">Windows</option>
                        <option value="openings">Openings</option>
                        <option value="rooms">Rooms</option>
                        <option value="plumbing_fixtures">Plumbing</option>
                        <option value="electrical_fixtures">Electrical</option>
                        <option value="concrete_areas">Concrete</option>
                        <option value="linear_measurements">Linear</option>
                        <option value="custom">Custom</option>
                      </select>
                      <input type="text" value={editQuantity} onChange={(e) => setEditQuantity(e.target.value)} placeholder="Qty" aria-label="Quantity" style={{ width: "4rem" }} />
                      <select value={editUnit} onChange={(e) => setEditUnit(e.target.value)} aria-label="Unit">
                        <option value="count">Count</option>
                        <option value="square_feet">SF</option>
                        <option value="linear_feet">LF</option>
                        <option value="cubic_yards">CY</option>
                        <option value="each">Each</option>
                      </select>
                      <button type="button" onClick={() => void handleAcceptWithEdits(s.id)} disabled={creating}>Accept with edits</button>
                      <button type="button" onClick={() => setEditingSuggestionId(null)}>Cancel</button>
                    </div>
                  ) : (
                    <span style={{ marginLeft: 0, fontWeight: 600 }}>
                      {s.decision_state === "pending" ? (
                        <>
                          <button type="button" onClick={() => void handleAcceptSuggestion(s.id)}>Accept</button>
                          <button type="button" onClick={() => void handleRejectSuggestion(s.id)}>Reject</button>
                          <button type="button" onClick={() => startEditingSuggestion(s)}>Edit</button>
                        </>
                      ) : (
                        <span aria-label="Decision outcome">- {s.decision_state}</span>
                      )}
                      {s.decided_at && <span style={{ marginLeft: "0.25rem", fontSize: "0.85rem" }}>({s.decided_at.slice(0, 10)})</span>}
                    </span>
                  )}
                </li>
              ))}
          </ul>
        </>
      )}

      <h4>Revision snapshots</h4>
      <div className="row">
        <button type="button" onClick={() => void handleCreateSnapshot()} disabled={creating}>
          Create snapshot
        </button>
      </div>
      {snapshots.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0 }}>
          {snapshots.map((snap) => (
            <li key={snap.id} style={{ marginBottom: "0.5rem" }}>
              {snap.name}
              <span className={snap.status === "locked" ? "snapshot-locked" : "snapshot-draft"} style={{ marginLeft: "0.5rem" }}>
                {snap.status === "locked" ? "Locked" : "Draft"}
              </span>
              {snap.status === "draft" && (
                <button type="button" onClick={() => void handleLockSnapshot(snap.id)}>Lock</button>
              )}
            </li>
          ))}
        </ul>
      )}

      <h4>Export</h4>
      <div className="row">
        <button type="button" onClick={() => void handleExport("json")} disabled={creating}>
          Export JSON
        </button>
        <button type="button" onClick={() => void handleExport("csv")} disabled={creating}>
          Export CSV
        </button>
      </div>
      {exports.length > 0 && (
        <p className="empty-hint">Recent: {exports.slice(0, 3).map((e) => `${e.export_type} (${e.created_at.slice(0, 10)})`).join(", ")}</p>
      )}
      {exportPayload != null && (
        <pre style={{ background: "#f1f5f9", padding: "0.75rem", overflow: "auto", maxHeight: "200px", fontSize: "0.85rem" }}>
          {exportPayload.slice(0, 3000)}{exportPayload.length > 3000 ? "..." : ""}
        </pre>
      )}
    </section>
  );
}
