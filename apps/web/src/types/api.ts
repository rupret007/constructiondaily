export type ApiUser = {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email?: string;
};

export type Project = {
  id: string;
  name: string;
  code: string;
  location: string;
  latitude: number | null;
  longitude: number | null;
  is_active: boolean;
};

export type DailyReport = {
  id: string;
  project: string;
  report_date: string;
  location: string;
  status: "draft" | "submitted" | "reviewed" | "approved" | "locked";
  summary: string;
  weather_source: string;
  weather_summary: string;
  temperature_high_c: number | null;
  temperature_low_c: number | null;
  precipitation_mm: number | null;
  wind_max_kph: number | null;
  rejection_reason: string;
  revision: number;
  prepared_by?: ApiUser;
};

export type SessionResponse = {
  authenticated: boolean;
  user?: ApiUser;
  csrfToken?: string;
};

export type OfflineMutation = {
  id: string;
  method: "POST" | "PUT" | "PATCH" | "DELETE";
  endpoint: string;
  payload: Record<string, unknown>;
  createdAt: number;
};

// ----- Preconstruction Plan Annotation -----

export type PlanSet = {
  id: string;
  project: string;
  name: string;
  description: string;
  status: "draft" | "processing" | "ready" | "archived";
  version_label: string;
  created_by?: ApiUser;
  updated_by?: ApiUser;
  created_at: string;
  updated_at: string;
};

export type PlanSheet = {
  id: string;
  project: string;
  plan_set: string;
  title: string;
  sheet_number: string;
  discipline: string;
  storage_key: string;
  page_count: number;
  sheet_index: number;
  width: number | null;
  height: number | null;
  calibrated_width: number | null;
  calibrated_height: number | null;
  calibrated_unit: "feet" | "meters";
  parse_status: string;
  preview_image: string;
  file_extension: string;
  file_type: "pdf" | "dxf" | "dwg" | "unknown";
  created_by?: ApiUser;
  created_at: string;
  updated_at: string;
};

export type ProjectDocument = {
  id: string;
  project: string;
  plan_set: string | null;
  title: string;
  document_type: "spec" | "addendum" | "rfi" | "submittal" | "vendor" | "scope" | "other";
  original_filename: string;
  storage_key: string;
  mime_type: string;
  file_extension: string;
  size_bytes: number;
  page_count: number;
  parse_status: "uploaded" | "parsed" | "failed";
  parse_error: string;
  created_by?: ApiUser;
  updated_by?: ApiUser;
  created_at: string;
  updated_at: string;
};

export type PlanSheetCadPreviewItem = {
  id: number;
  entity_type: string;
  layer: string;
  label: string;
  confidence: number;
  geometry_json: GeometryJson;
};

export type PlanSheetCadPreview = {
  source_type: "dxf" | "dwg";
  item_count: number;
  bounds: {
    min_x: number;
    min_y: number;
    max_x: number;
    max_y: number;
  } | null;
  items: PlanSheetCadPreviewItem[];
};

export type AnnotationLayer = {
  id: string;
  project: string;
  plan_set: string;
  plan_sheet: string;
  name: string;
  color: string;
  category: string;
  is_visible: boolean;
  is_locked: boolean;
  created_by?: ApiUser;
  created_at: string;
  updated_at: string;
};

export type GeometryJson = Record<string, unknown>;

export type AnnotationItem = {
  id: string;
  project: string;
  plan_sheet: string;
  layer: string;
  annotation_type: "point" | "rectangle" | "polygon" | "polyline" | "text";
  geometry_json: GeometryJson;
  label: string;
  notes: string;
  source: "manual" | "ai";
  confidence: number | null;
  review_state: string;
  linked_takeoff_item: string | null;
  created_by?: ApiUser;
  updated_by?: ApiUser;
  created_at: string;
  updated_at: string;
};

export type TakeoffItem = {
  id: string;
  project: string;
  plan_set: string;
  plan_sheet: string | null;
  category: string;
  subcategory: string;
  unit: string;
  quantity: string;
  confidence: number | null;
  notes: string;
  cost_code: string;
  bid_package: string;
  source: string;
  review_state: string;
  created_by?: ApiUser;
  updated_by?: ApiUser;
  created_at: string;
  updated_at: string;
};

export type TakeoffSummary = {
  total_items: number;
  pending_items: number;
  accepted_items: number;
  rejected_items: number;
  edited_items: number;
  manual_items: number;
  ai_assisted_items: number;
  linked_annotation_items: number;
  unit_totals: Array<{
    unit: string;
    item_count: number;
    quantity_total: string;
  }>;
  category_totals: Array<{
    category: string;
    unit: string;
    item_count: number;
    quantity_total: string;
  }>;
  review_state_totals: Array<{
    review_state: string;
    item_count: number;
  }>;
  source_totals: Array<{
    source: string;
    item_count: number;
  }>;
};

export type PreconstructionCopilotCitation = {
  kind: string;
  id: string;
  label: string;
  detail: string;
};

export type PreconstructionCopilotResponse = {
  status: "grounded" | "limited" | "needs_documents";
  answer: string;
  scope: {
    project_id: string;
    project_code: string;
    project_name: string;
    plan_set_id: string | null;
    plan_set_name: string | null;
    plan_sheet_id: string | null;
    plan_sheet_name: string | null;
  };
  citations: PreconstructionCopilotCitation[];
  suggested_prompts: string[];
};

export type AIAnalysisRun = {
  id: string;
  project: string;
  plan_set: string;
  plan_sheet: string;
  provider_name: string;
  user_prompt: string;
  status: string;
  request_payload_json: Record<string, unknown>;
  response_payload_json: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
  created_by?: ApiUser;
  created_at: string;
  updated_at: string;
};

export type AISuggestion = {
  id: string;
  analysis_run: string;
  project: string;
  plan_sheet: string;
  suggestion_type: string;
  geometry_json: GeometryJson;
  label: string;
  rationale: string;
  confidence: number | null;
  accepted_annotation: string | null;
  decision_state: string;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
};

export type RevisionSnapshot = {
  id: string;
  project: string;
  plan_set: string;
  name: string;
  status: string;
  snapshot_payload_json: Record<string, unknown>;
  created_by?: ApiUser;
  created_at: string;
};

export type ExportRecord = {
  id: string;
  project: string;
  plan_set: string;
  revision_snapshot: string | null;
  export_type: string;
  status: string;
  storage_key: string;
  metadata_json: Record<string, unknown>;
  created_by?: ApiUser;
  created_at: string;
};
