import { apiRequest } from "./api";
import type {
  AIAnalysisRun,
  AISuggestion,
  AnnotationItem,
  AnnotationLayer,
  ExportRecord,
  PlanSetEstimatingDashboard,
  PreconstructionCopilotResponse,
  PlanSet,
  PlanSheetCadPreview,
  PlanSheet,
  ProjectDocument,
  RevisionSnapshot,
  TakeoffItem,
  TakeoffSummary,
} from "../types/api";

const P = "/preconstruction";

export async function fetchPlanSets(projectId: string): Promise<PlanSet[]> {
  const response = await apiRequest<PlanSet[]>(`${P}/sets/?project=${projectId}`);
  return Array.isArray(response) ? response : [];
}

export async function createPlanSet(payload: {
  project: string;
  name: string;
  description?: string;
  version_label?: string;
}): Promise<PlanSet> {
  return apiRequest<PlanSet>(`${P}/sets/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchPlanSet(planSetId: string): Promise<PlanSet> {
  return apiRequest<PlanSet>(`${P}/sets/${planSetId}/`);
}

export async function updatePlanSet(
  planSetId: string,
  payload: Partial<Pick<PlanSet, "name" | "description" | "status" | "version_label">>
): Promise<PlanSet> {
  return apiRequest<PlanSet>(`${P}/sets/${planSetId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deletePlanSet(planSetId: string): Promise<void> {
  return apiRequest<void>(`${P}/sets/${planSetId}/`, { method: "DELETE" });
}

export async function fetchPlanSheets(planSetId: string): Promise<PlanSheet[]> {
  const response = await apiRequest<PlanSheet[]>(`${P}/sheets/?plan_set=${planSetId}`);
  return Array.isArray(response) ? response : [];
}

export async function fetchProjectDocuments(
  projectId: string,
  options?: { planSetId?: string; scopedToPlanSet?: boolean }
): Promise<ProjectDocument[]> {
  const params = new URLSearchParams({ project: projectId });
  if (options?.scopedToPlanSet && options.planSetId) {
    params.set("scope_plan_set", options.planSetId);
  } else if (options?.planSetId) {
    params.set("plan_set", options.planSetId);
  }
  const response = await apiRequest<ProjectDocument[]>(`${P}/documents/?${params.toString()}`);
  return Array.isArray(response) ? response : [];
}

export async function uploadProjectDocument(
  projectId: string,
  file: File,
  options: {
    document_type: ProjectDocument["document_type"];
    title?: string;
    plan_set?: string | null;
  }
): Promise<ProjectDocument> {
  const form = new FormData();
  form.append("project", projectId);
  form.append("document_type", options.document_type);
  form.append("file", file);
  if (options.title) form.append("title", options.title);
  if (options.plan_set) form.append("plan_set", options.plan_set);
  return apiRequest<ProjectDocument>(`${P}/documents/`, {
    method: "POST",
    body: form,
  });
}

export function projectDocumentFileUrl(documentId: string): string {
  const base = import.meta.env.VITE_API_BASE ?? "/api";
  return `${base}${P}/documents/${documentId}/file/`;
}

export async function uploadPlanSheet(
  planSetId: string,
  file: File,
  options?: { title?: string; sheet_number?: string; discipline?: string; sheet_index?: number }
): Promise<PlanSheet> {
  const form = new FormData();
  form.append("plan_set", planSetId);
  form.append("file", file);
  if (options?.title) form.append("title", options.title);
  if (options?.sheet_number) form.append("sheet_number", options.sheet_number);
  if (options?.discipline) form.append("discipline", options.discipline);
  if (options?.sheet_index != null) form.append("sheet_index", String(options.sheet_index));
  return apiRequest<PlanSheet>(`${P}/sheets/`, {
    method: "POST",
    body: form,
  });
}

export async function fetchPlanSheet(sheetId: string): Promise<PlanSheet> {
  return apiRequest<PlanSheet>(`${P}/sheets/${sheetId}/`);
}

export async function updatePlanSheet(
  sheetId: string,
  payload: Partial<Pick<PlanSheet, "title" | "sheet_number" | "discipline" | "sheet_index" | "calibrated_width" | "calibrated_height" | "calibrated_unit">>
): Promise<PlanSheet> {
  return apiRequest<PlanSheet>(`${P}/sheets/${sheetId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function planSheetFileUrl(sheetId: string): string {
  const base = import.meta.env.VITE_API_BASE ?? "/api";
  return `${base}${P}/sheets/${sheetId}/file/`;
}

export async function fetchPlanSheetCadPreview(sheetId: string): Promise<PlanSheetCadPreview> {
  return apiRequest<PlanSheetCadPreview>(`${P}/sheets/${sheetId}/cad_preview/`);
}

export async function fetchAnnotationLayers(planSheetId: string): Promise<AnnotationLayer[]> {
  const response = await apiRequest<AnnotationLayer[]>(`${P}/layers/?plan_sheet=${planSheetId}`);
  return Array.isArray(response) ? response : [];
}

export async function createAnnotationLayer(payload: {
  project: string;
  plan_set: string;
  plan_sheet: string;
  name: string;
  color?: string;
  category?: string;
}): Promise<AnnotationLayer> {
  return apiRequest<AnnotationLayer>(`${P}/layers/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAnnotationLayer(
  layerId: string,
  payload: Partial<Pick<AnnotationLayer, "name" | "color" | "category" | "is_visible" | "is_locked">>
): Promise<AnnotationLayer> {
  return apiRequest<AnnotationLayer>(`${P}/layers/${layerId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function fetchAnnotations(planSheetId: string, layerId?: string): Promise<AnnotationItem[]> {
  let url = `${P}/annotations/?plan_sheet=${planSheetId}`;
  if (layerId) url += `&layer=${layerId}`;
  const response = await apiRequest<AnnotationItem[]>(url);
  return Array.isArray(response) ? response : [];
}

export async function createAnnotation(payload: {
  project: string;
  plan_sheet: string;
  layer: string;
  annotation_type: AnnotationItem["annotation_type"];
  geometry_json: AnnotationItem["geometry_json"];
  label?: string;
  notes?: string;
}): Promise<AnnotationItem> {
  return apiRequest<AnnotationItem>(`${P}/annotations/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAnnotation(
  annotationId: string,
  payload: Partial<Pick<AnnotationItem, "geometry_json" | "label" | "notes">>
): Promise<AnnotationItem> {
  return apiRequest<AnnotationItem>(`${P}/annotations/${annotationId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteAnnotation(annotationId: string): Promise<void> {
  return apiRequest<void>(`${P}/annotations/${annotationId}/`, { method: "DELETE" });
}

export async function createTakeoffFromAnnotation(
  annotationId: string,
  assemblyProfile: "auto" | "none" | "door_set" | "window_set" | "fixture_set" = "auto"
): Promise<{ primary_takeoff: TakeoffItem; extra_takeoffs: TakeoffItem[]; assembly_profile: string }> {
  return apiRequest<{ primary_takeoff: TakeoffItem; extra_takeoffs: TakeoffItem[]; assembly_profile: string }>(
    `${P}/annotations/${annotationId}/create_takeoff/`,
    {
      method: "POST",
      body: JSON.stringify({ assembly_profile: assemblyProfile }),
    }
  );
}

type TakeoffQueryFilters = {
  category?: string;
  source?: string;
  review_state?: string;
  bid_package?: string;
  cost_code?: string;
};

function buildTakeoffQuery(planSetId: string, planSheetId?: string, filters?: TakeoffQueryFilters): string {
  const params = new URLSearchParams({ plan_set: planSetId });
  if (planSheetId) params.set("plan_sheet", planSheetId);
  if (filters?.category) params.set("category", filters.category);
  if (filters?.source) params.set("source", filters.source);
  if (filters?.review_state) params.set("review_state", filters.review_state);
  if (filters?.bid_package) params.set("bid_package", filters.bid_package);
  if (filters?.cost_code) params.set("cost_code", filters.cost_code);
  return params.toString();
}

export async function fetchTakeoffItems(
  planSetId: string,
  planSheetId?: string,
  filters?: TakeoffQueryFilters
): Promise<TakeoffItem[]> {
  const url = `${P}/takeoff/?${buildTakeoffQuery(planSetId, planSheetId, filters)}`;
  const response = await apiRequest<TakeoffItem[]>(url);
  return Array.isArray(response) ? response : [];
}

export async function fetchTakeoffSummary(
  planSetId: string,
  planSheetId?: string,
  filters?: TakeoffQueryFilters
): Promise<TakeoffSummary> {
  return apiRequest<TakeoffSummary>(`${P}/takeoff/summary/?${buildTakeoffQuery(planSetId, planSheetId, filters)}`);
}

export async function fetchPlanSetEstimatingDashboard(
  planSetId: string,
  filters?: TakeoffQueryFilters
): Promise<PlanSetEstimatingDashboard> {
  const params = new URLSearchParams({ plan_set: planSetId });
  if (filters?.category) params.set("category", filters.category);
  if (filters?.source) params.set("source", filters.source);
  if (filters?.review_state) params.set("review_state", filters.review_state);
  if (filters?.bid_package) params.set("bid_package", filters.bid_package);
  if (filters?.cost_code) params.set("cost_code", filters.cost_code);
  return apiRequest<PlanSetEstimatingDashboard>(`${P}/takeoff/dashboard/?${params.toString()}`);
}

export async function createTakeoffItem(payload: {
  project: string;
  plan_set: string;
  plan_sheet?: string | null;
  category?: string;
  subcategory?: string;
  unit?: string;
  quantity: string | number;
  notes?: string;
  cost_code?: string;
  bid_package?: string;
}): Promise<TakeoffItem> {
  return apiRequest<TakeoffItem>(`${P}/takeoff/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateTakeoffItem(
  takeoffId: string,
  payload: Partial<Pick<TakeoffItem, "category" | "subcategory" | "unit" | "quantity" | "notes" | "cost_code" | "bid_package" | "review_state">>
): Promise<TakeoffItem> {
  return apiRequest<TakeoffItem>(`${P}/takeoff/${takeoffId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteTakeoffItem(takeoffId: string): Promise<void> {
  return apiRequest<void>(`${P}/takeoff/${takeoffId}/`, { method: "DELETE" });
}

export async function queryPreconstructionCopilot(payload: {
  project: string;
  plan_set?: string | null;
  plan_sheet?: string | null;
  annotation?: string | null;
  provider_name?: "mock" | "openai_vision" | "cad_dxf" | null;
  question: string;
}): Promise<PreconstructionCopilotResponse> {
  return apiRequest<PreconstructionCopilotResponse>(`${P}/copilot/query/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function triggerAnalysis(
  planSheetId: string,
  userPrompt: string,
  providerName?: "mock" | "openai_vision" | "cad_dxf"
): Promise<AIAnalysisRun> {
  return apiRequest<AIAnalysisRun>(`${P}/analysis/`, {
    method: "POST",
    body: JSON.stringify({
      plan_sheet: planSheetId,
      user_prompt: userPrompt,
      ...(providerName ? { provider_name: providerName } : {}),
    }),
  });
}

export async function fetchSuggestions(planSheetId: string, analysisRunId?: string): Promise<AISuggestion[]> {
  let url = `${P}/suggestions/?plan_sheet=${planSheetId}`;
  if (analysisRunId) url += `&analysis_run=${analysisRunId}`;
  const response = await apiRequest<AISuggestion[]>(url);
  return Array.isArray(response) ? response : [];
}

export type AcceptSuggestionOptions = {
  layer_id?: string;
  geometry_json?: Record<string, unknown>;
  label?: string;
  category?: string;
  unit?: string;
  quantity?: string;
};

export async function acceptSuggestion(
  suggestionId: string,
  options?: AcceptSuggestionOptions
): Promise<{ annotation: AnnotationItem; takeoff: TakeoffItem }> {
  return apiRequest<{ annotation: AnnotationItem; takeoff: TakeoffItem }>(
    `${P}/suggestions/${suggestionId}/accept/`,
    {
      method: "POST",
      body: JSON.stringify(options ?? {}),
    }
  );
}

export async function rejectSuggestion(suggestionId: string): Promise<AISuggestion> {
  return apiRequest<AISuggestion>(`${P}/suggestions/${suggestionId}/reject/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export type BatchAcceptResult = {
  accepted_count: number;
  annotations: AnnotationItem[];
  takeoff_items: TakeoffItem[];
};

export async function batchAcceptSuggestions(
  planSheetId: string,
  minConfidence?: number
): Promise<BatchAcceptResult> {
  return apiRequest<BatchAcceptResult>(`${P}/suggestions/batch_accept/`, {
    method: "POST",
    body: JSON.stringify({
      plan_sheet: planSheetId,
      min_confidence: minConfidence ?? 0.85,
    }),
  });
}

export async function fetchSnapshots(planSetId: string): Promise<RevisionSnapshot[]> {
  const response = await apiRequest<RevisionSnapshot[]>(`${P}/snapshots/?plan_set=${planSetId}`);
  return Array.isArray(response) ? response : [];
}

export async function createSnapshot(payload: {
  project: string;
  plan_set: string;
  name: string;
}): Promise<RevisionSnapshot> {
  return apiRequest<RevisionSnapshot>(`${P}/snapshots/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function lockSnapshot(snapshotId: string): Promise<RevisionSnapshot> {
  return apiRequest<RevisionSnapshot>(`${P}/snapshots/${snapshotId}/lock/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function createExport(payload: {
  plan_set: string;
  export_type: "json" | "csv" | "pdf_metadata";
  revision_snapshot?: string | null;
}): Promise<ExportRecord & { payload?: unknown }> {
  return apiRequest<ExportRecord & { payload?: unknown }>(`${P}/exports/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchExportRecords(planSetId: string): Promise<ExportRecord[]> {
  const response = await apiRequest<ExportRecord[]>(`${P}/exports/?plan_set=${planSetId}`);
  return Array.isArray(response) ? response : [];
}
