/**
 * PDF sheet viewer with zoom/pan and annotation overlay.
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
  createTakeoffItem,
  deleteAnnotation,
  fetchAnnotationLayers,
  fetchAnnotations,
  fetchExportRecords,
  fetchPlanSheet,
  fetchSnapshots,
  fetchSuggestions,
  fetchTakeoffItems,
  lockSnapshot,
  planSheetFileUrl,
  rejectSuggestion,
  triggerAnalysis,
  updateAnnotationLayer,
} from "../services/preconstruction";
import type {
  AISuggestion,
  AnnotationItem,
  AnnotationLayer as LayerType,
  ExportRecord,
  PlanSheet,
  RevisionSnapshot,
  TakeoffItem,
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

export function SheetViewer({ sheetId, planSetId, onBack }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [sheet, setSheet] = useState<PlanSheet | null>(null);
  const [layers, setLayers] = useState<LayerType[]>([]);
  const [annotations, setAnnotations] = useState<AnnotationItem[]>([]);
  const [takeoffItems, setTakeoffItems] = useState<TakeoffItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [scale, setScale] = useState(1.2);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef({ x: 0, y: 0 });
  const [pdfDoc, setPdfDoc] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [, setPageWidth] = useState(612);
  const [, setPageHeight] = useState(792);
  const [addTakeoffCategory, setAddTakeoffCategory] = useState("doors");
  const [addTakeoffQuantity, setAddTakeoffQuantity] = useState("1");
  const [addTakeoffUnit, setAddTakeoffUnit] = useState("count");
  const [creating, setCreating] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiRunning, setAiRunning] = useState(false);
  const [batchAccepting, setBatchAccepting] = useState(false);
  const [placementMode, setPlacementMode] = useState<"none" | "point" | "rectangle">("none");
  const [placementLabel, setPlacementLabel] = useState("");
  const [rectDragStart, setRectDragStart] = useState<{ x: number; y: number } | null>(null);
  const [rectDragCurrent, setRectDragCurrent] = useState<{ x: number; y: number } | null>(null);
  const [suggestions, setSuggestions] = useState<AISuggestion[]>([]);
  const [snapshots, setSnapshots] = useState<RevisionSnapshot[]>([]);
  const [exports, setExports] = useState<ExportRecord[]>([]);
  const [exportPayload, setExportPayload] = useState<string | null>(null);
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null);
  const [editingSuggestionId, setEditingSuggestionId] = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [editCategory, setEditCategory] = useState("doors");
  const [editUnit, setEditUnit] = useState("count");
  const [editQuantity, setEditQuantity] = useState("1");

  const loadSheetAndData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [sheetData, layersData] = await Promise.all([
        fetchPlanSheet(sheetId),
        fetchAnnotationLayers(sheetId),
      ]);
      setSheet(sheetData);
      setLayers(layersData);
      const width = sheetData.width != null ? Number(sheetData.width) : 612;
      const height = sheetData.height != null ? Number(sheetData.height) : 792;
      setPageWidth(width);
      setPageHeight(height);
      const annList = await fetchAnnotations(sheetId);
      setAnnotations(annList);
      const takeoffList = await fetchTakeoffItems(planSetId, sheetId);
      setTakeoffItems(takeoffList);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load sheet.");
    } finally {
      setLoading(false);
    }
  }, [sheetId, planSetId]);

  useEffect(() => {
    void loadSheetAndData();
  }, [loadSheetAndData]);

  const addAnnotationWithGeometry = async (
    geometry_json: Record<string, unknown>,
    annotationType: "point" | "rectangle",
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

  const handleCanvasMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button !== 0 || creating) return;
    if (placementMode === "point") {
      const coords = getNormalizedCoords(e);
      if (coords) {
        e.stopPropagation();
        void addAnnotationWithGeometry(
          { type: "point", x: coords.x, y: coords.y },
          "point",
          placementLabel || "Point"
        );
        setPlacementMode("none");
      }
    } else if (placementMode === "rectangle") {
      const coords = getNormalizedCoords(e);
      if (coords) {
        e.stopPropagation();
        setRectDragStart(coords);
        setRectDragCurrent(coords);
      }
    }
  };

  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (placementMode === "rectangle" && rectDragStart) {
      const coords = getNormalizedCoords(e);
      if (coords) {
        e.stopPropagation();
        setRectDragCurrent(coords);
      }
    }
  };

  const handleCanvasMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button !== 0) return;
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
      setPlacementMode("none");
      setRectDragStart(null);
      setRectDragCurrent(null);
    }
  };

  const addAnnotation = (annotationType: "point" | "rectangle", label: string) => {
    if (placementMode !== "none") {
      setPlacementMode("none");
      setRectDragStart(null);
      setRectDragCurrent(null);
    }
    setPlacementLabel(label);
    setPlacementMode(annotationType);
  };

  const handleDeleteAnnotation = async (annotationId: string) => {
    if (!window.confirm("Delete this annotation? This cannot be undone.")) return;
    try {
      await deleteAnnotation(annotationId);
      setSelectedAnnotationId((id) => (id === annotationId ? null : id));
      await loadSheetAndData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete.");
    }
  };

  const handleCreateTakeoffFromAnnotation = async (annotation: AnnotationItem) => {
    if (!sheet) return;
    setCreating(true);
    try {
      await createTakeoffItem({
        project: sheet.project,
        plan_set: planSetId,
        plan_sheet: sheetId,
        category: addTakeoffCategory,
        unit: addTakeoffUnit,
        quantity: addTakeoffQuantity,
        notes: `From annotation: ${annotation.label || annotation.id}`,
      });
      setAddTakeoffQuantity("1");
      const list = await fetchTakeoffItems(planSetId, sheetId);
      setTakeoffItems(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add takeoff.");
    } finally {
      setCreating(false);
    }
  };

  const handleAddTakeoff = async () => {
    if (!sheet) return;
    setCreating(true);
    try {
      await createTakeoffItem({
        project: sheet.project,
        plan_set: planSetId,
        plan_sheet: sheetId,
        category: addTakeoffCategory,
        unit: addTakeoffUnit,
        quantity: addTakeoffQuantity,
      });
      setAddTakeoffQuantity("1");
      const list = await fetchTakeoffItems(planSetId, sheetId);
      setTakeoffItems(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add takeoff.");
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
      setRectDragStart(null);
      setRectDragCurrent(null);
      setPlacementMode("none");
    };
    window.addEventListener("mouseup", onGlobalMouseUp);
    return () => window.removeEventListener("mouseup", onGlobalMouseUp);
  }, [rectDragStart, placementMode]);

  useEffect(() => {
    if (sheetId) void loadSuggestions();
  }, [sheetId, loadSuggestions]);
  useEffect(() => {
    void loadSnapshotsAndExports();
  }, [loadSnapshotsAndExports]);

  const handleRunAnalysis = async () => {
    setAiRunning(true);
    setError("");
    try {
      await triggerAnalysis(sheetId, aiPrompt);
      await loadSuggestions();
      await loadSheetAndData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed.");
    } finally {
      setAiRunning(false);
    }
  };

  const handleAcceptSuggestion = async (suggestionId: string) => {
    try {
      await acceptSuggestion(suggestionId);
      await loadSuggestions();
      await loadSheetAndData();
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
    try {
      await acceptSuggestion(suggestionId, {
        label: editLabel,
        category: editCategory,
        unit: editUnit,
        quantity: editQuantity,
      });
      setEditingSuggestionId(null);
      await loadSuggestions();
      await loadSheetAndData();
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
        await loadSheetAndData();
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

  useEffect(() => {
    if (!sheet) return;
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
      const drawOverlays = () => {
      const visibleLayers = layers.filter((l) => l.is_visible);
      const layerIds = new Set(visibleLayers.map((l) => l.id));
      const toDraw = annotations.filter((a) => layerIds.has(a.layer));
      toDraw.forEach((item) => drawAnnotation(ctx, item, pw, ph));
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
      };
      const task = page.render(renderContext);
      if (task.promise) {
        task.promise.then(drawOverlays);
      } else {
        drawOverlays();
      }
    });
  }, [pdfDoc, scale, layers, annotations, rectDragStart, rectDragCurrent]);

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
              : isPanning
                ? "grabbing"
                : "grab",
        }}
        onMouseDown={(e) => {
          if (e.button !== 0 || placementMode !== "none") return;
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
                setRectDragStart(null);
                setRectDragCurrent(null);
                setPlacementMode("none");
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
          <h4>Takeoff summary</h4>
          {takeoffItems.length === 0 ? (
            <p className="empty-hint">No takeoff items on this sheet yet.</p>
          ) : (
            <ul style={{ listStyle: "none", padding: 0 }}>
              {takeoffItems.map((t) => (
                <li key={t.id}>
                  {t.category}: {t.quantity} {t.unit}
                </li>
              ))}
            </ul>
          )}
          <div className="row" style={{ marginTop: "0.5rem" }}>
            <select
              value={addTakeoffCategory}
              onChange={(e) => setAddTakeoffCategory(e.target.value)}
              aria-label="Category"
            >
              <option value="doors">Doors</option>
              <option value="windows">Windows</option>
              <option value="plumbing_fixtures">Plumbing</option>
              <option value="concrete_areas">Concrete</option>
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
              <option value="each">Each</option>
            </select>
            <button type="button" onClick={() => void handleAddTakeoff()} disabled={creating}>
              Add takeoff
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
        {placementMode !== "none" && (
          <span style={{ fontSize: "0.9rem", color: "#64748b" }}>
            {placementMode === "point"
              ? "Click on the plan to place a point"
              : "Click and drag on the plan to draw a rectangle"}
          </span>
        )}
        {placementMode !== "none" && (
          <button type="button" onClick={() => setPlacementMode("none")}>
            Cancel
          </button>
        )}
      </div>
      <div className="row sheet-viewer-sidebars">
        <div className="card" style={{ flex: "0 0 220px" }}>
          <h4>Annotations</h4>
          {annotations.length === 0 ? (
            <p className="empty-hint">No annotations yet. Add a point or rectangle above.</p>
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
                <div className="row">
                  <button type="button" onClick={() => void handleCreateTakeoffFromAnnotation(ann)} disabled={creating}>
                    Create takeoff from this
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
