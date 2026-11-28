/**
 * Shared contracts between the DocuRebuild web client and the local backend.
 * Keep this package free of runtime dependencies so any client can import it.
 */

/* -------------------------------------------------------------------------- */
/*                                  Settings                                  */
/* -------------------------------------------------------------------------- */

export type ThemeMode = "system" | "light" | "dark";
export type AccentName =
  | "indigo"
  | "violet"
  | "blue"
  | "teal"
  | "emerald"
  | "amber"
  | "rose";
export type RadiusStyle = "compact" | "soft" | "rounded";
export type BlurLevel = "off" | "subtle" | "strong";
export type Density = "comfortable" | "compact";
export type FontSizePreset = "sm" | "md" | "lg";
export type MotionPreference = "full" | "reduced";
export type LanguageCode = "en" | "my" | "system";
export type DocumentFont = "serif" | "sans";
export type PdfPageSize = "a4" | "letter";
export type PdfMargin = "narrow" | "normal" | "wide";

export interface AppearanceSettings {
  theme: ThemeMode;
  accent: AccentName;
  radius: RadiusStyle;
  blur: BlurLevel;
  density: Density;
  font_size: FontSizePreset;
  motion: MotionPreference;
}

export interface EditorSettings {
  document_font: DocumentFont;
}

export interface ExportSettings {
  pdf_page_size: PdfPageSize;
  pdf_margin: PdfMargin;
}

export interface BackupSettings {
  auto_on_open: boolean;
  interval_hours: number;
  keep_copies: number;
}

export interface AppSettings {
  language: LanguageCode;
  appearance: AppearanceSettings;
  editor: EditorSettings;
  export: ExportSettings;
  backups: BackupSettings;
}

/* -------------------------------------------------------------------------- */
/*                                   Fonts                                    */
/* -------------------------------------------------------------------------- */

export type FontSource = "system" | "imported";
export type FontFamilySource = "system" | "imported" | "mixed";

export interface FontFaceSummary {
  id: string | null;
  family: string;
  style: string;
  weight: number;
  italic: boolean;
  source: FontSource;
  format: string;
  file_name: string | null;
}

export interface FontFamilySummary {
  name: string;
  source: FontFamilySource;
  faces: FontFaceSummary[];
  available: boolean;
}

export interface FontsResponse {
  families: FontFamilySummary[];
  imported_count: number;
  system_count: number;
  system_directories: string[];
}

/* -------------------------------------------------------------------------- */
/*                                  Projects                                  */
/* -------------------------------------------------------------------------- */

export interface ProjectSummary {
  id: string;
  name: string;
  description: string;
  page_count: number;
  created_at: string;
  updated_at: string;
  last_opened_at: string | null;
}

export interface ProjectDetail extends ProjectSummary {
  directory: string;
  document_updated_at: string | null;
}

/** One project that could not be moved to the trash during a bulk delete. */
export interface ProjectBulkDeleteFailure {
  id: string;
  code: string;
  message: string;
}

/** Outcome of deleting several projects in one request. */
export interface ProjectBulkDeleteResult {
  deleted: string[];
  failed: ProjectBulkDeleteFailure[];
  trash_paths: string[];
}

/** Outcome of a factory reset that erased all local application data. */
export interface FactoryResetResult {
  ok: boolean;
  data_dir: string;
  projects_removed: number;
}

/** One verified backup archive kept in the local backup vault. */
export interface ProjectBackupSummary {
  filename: string;
  byte_size: number;
  created_at: string;
}

/** Page image slots that can be repaired from a backup. */
export type PageAssetSlot = "original" | "display" | "thumbnail";

/** One page found in an inspected backup archive. */
export interface BackupPageSummary {
  id: string;
  page_number: number;
  source_kind: string;
  status: string;
  width: number | null;
  height: number | null;
  original_filename: string | null;
  /** Whether this page still exists in the inspecting project. */
  in_project: boolean;
  /** Image slots whose file is missing in the current project. */
  missing_slots: PageAssetSlot[];
  /** Missing slots the backup can actually supply. */
  restorable_slots: PageAssetSlot[];
}

/** One extracted region in a backup whose crop is missing here. */
export interface BackupElementSummary {
  id: string;
  page_id: string;
  page_number: number;
  kind: string;
  caption: string;
  verified: boolean;
  /** Whether the backup can supply the crop file. */
  restorable: boolean;
}

/** Pages, damaged region crops and document versions found in an archive. */
export interface BackupSelection {
  token: string;
  source_name: string;
  created_at: string;
  pages: BackupPageSummary[];
  elements: BackupElementSummary[];
  /** True when more damaged regions exist than one inspection lists. */
  elements_truncated: boolean;
  document: BackupDocument;
}

/** The live document stored in a backup, without its full content. */
export interface BackupDocumentSummary {
  preview: string;
  character_count: number;
  updated_at: string | null;
}

/** One stored document version found in a backup. */
export interface BackupDocumentRevision {
  id: string;
  source: string;
  preview: string;
  character_count: number;
  created_at: string;
}

export interface BackupDocument {
  current: BackupDocumentSummary;
  revisions: BackupDocumentRevision[];
}

/** Result of replacing the live document from a backup. */
export interface DocumentRestoreResult {
  restored: boolean;
  source: "current" | "revision";
  revision_id: string | null;
  updated_at: string | null;
  /** The restored record, so the editor can apply it without a reload. */
  document: DocumentRecord;
}

/** Result of appending selected pages to the current project. */
export interface PageRestoreResult {
  restored: number;
  page_numbers: number[];
}

/** Result of repairing a page's missing image files from a backup. */
export interface PageAssetRepairResult {
  page_id: string;
  page_number: number;
  restored_slots: PageAssetSlot[];
}

/** Result of repairing a region's missing crop from a backup. */
export interface ElementAssetRepairResult {
  element_id: string;
  page_id: string;
  page_number: number;
  kind: string;
  restored: boolean;
}

export type SourceKind = "image" | "pdf";
export type PageStatus = "imported" | "processing" | "ready" | "failed";
export type ImportJobStatus =
  | "queued"
  | "running"
  | "cancelling"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface ImportJob {
  id: string;
  kind: string;
  status: ImportJobStatus;
  /** Fraction from 0 to 1 based on completed pages. */
  progress: number;
  total_pages: number;
  imported_pages: number;
  current_file: string | null;
  file_count: number;
  filenames: string[];
  error: string | null;
  error_code: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface PageSummary {
  id: string;
  page_number: number;
  source_kind: SourceKind;
  status: PageStatus;
  width: number | null;
  height: number | null;
  original_asset_id: string | null;
  display_asset_id: string | null;
  thumbnail_asset_id: string | null;
  original_filename: string | null;
  rotation: number;
  /** 1-based page number inside the original PDF, or null for image pages. */
  pdf_page_number: number | null;
  /** Stored non-destructive edit operations (crop, perspective, deskew, filters). */
  edits: PageEdits;
  created_at: string;
  updated_at: string;
}

export interface PageEdits {
  geometry: PageGeometryStep[];
  filters: PageFilters;
}

export type PageGeometryType = "crop" | "perspective" | "deskew";

export interface PageGeometryStep {
  type: PageGeometryType;
  rect?: PageCropRect;
  corners?: PagePerspectiveCorners;
  angle?: number;
}

export interface PageCropRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PagePerspectiveCorners {
  [index: number]: [number, number];
}

export interface PageFilters {
  grayscale: boolean;
  contrast: number;
  brightness: number;
  sharpness: number;
  denoise: number;
  shadow_removal: boolean;
  background_cleanup: boolean;
  threshold: boolean;
  threshold_level: number;
}

export interface ProjectManifest {
  schema_version: number;
  project_id: string;
  name: string;
  created_at: string;
  app_version: string;
}

/* -------------------------------------------------------------------------- */
/*                                    OCR                                     */
/* -------------------------------------------------------------------------- */

export type OcrRunStatus = "queued" | "running" | "succeeded" | "failed";
export type OcrBlockKind =
  | "paragraph"
  | "heading"
  | "list_item"
  | "caption"
  | "equation"
  | "table"
  | "page_number"
  | "header"
  | "footer";

export interface OcrLine {
  /** Line text exactly as the engine produced it. */
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface OcrBlock {
  id: string;
  run_id: string;
  page_id: string;
  block_index: number;
  kind: OcrBlockKind;
  text: string;
  confidence: number | null;
  x: number | null;
  y: number | null;
  width: number | null;
  height: number | null;
  line_count: number;
  word_count: number;
  /** Visual line geometry; empty when the engine stored no word boxes. */
  lines: OcrLine[];
  verified: boolean;
  corrected: boolean;
  created_at: string;
  updated_at: string;
}

export interface OcrRun {
  id: string;
  page_id: string;
  status: OcrRunStatus;
  engine: string;
  engine_version: string | null;
  languages: string[];
  source_asset_id: string | null;
  rotation: number;
  mean_confidence: number | null;
  text: string;
  error: string | null;
  error_code: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  stale: boolean;
  blocks: OcrBlock[];
}

export interface OcrCapabilities {
  engine: string;
  available: boolean;
  version: string | null;
  command: string;
  tessdata_dir: string | null;
  languages: string[];
  preferred_languages: string[];
  page_segmentation_mode: number;
  page_segmentation_modes: number[];
  reason: string | null;
  setup_hint: string | null;
}

/* -------------------------------------------------------------------------- */
/*                              Table proposals                               */
/* -------------------------------------------------------------------------- */

export type TableProposalWarning = "no_confidence" | "low_confidence" | "empty_cells";

/** Alignment proposed for a cell; `null` means it cannot be observed. */
export type TableAlignment = "left" | "center" | "right";

/** One proposed cell. Empty cells stay empty; nothing is invented. */
export interface TableProposalCell {
  row: number;
  column: number;
  text: string;
  confidence: number | null;
  /** At least one word is low-confidence or has no score. */
  uncertain: boolean;
  empty: boolean;
  /**
   * Alignment inferred from the cell's word boxes inside its column band, or
   * null when the text fills the band and the choice is not observable.
   */
  alignment: TableAlignment | null;
  /**
   * Rows covered from this anchor, when the PDF draws the cell as a merge.
   * Covered coordinates are not repeated as cells; a missing value is 1.
   */
  rowspan?: number;
  /** Columns covered from this anchor. A missing value is 1. */
  colspan?: number;
}

/** Pixel region a proposal was read from, in OCR image coordinates. */
export interface TableSourceBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** A reviewable table built from stored OCR word boxes. Never saved on its own. */
export interface TableProposal {
  page_id: string;
  block_id: string;
  run_id: string;
  engine: string;
  page_width: number | null;
  page_height: number | null;
  rows: number;
  columns: number;
  has_confidence: boolean;
  uncertain_cells: number;
  empty_cells: number;
  warnings: TableProposalWarning[];
  source: TableSourceBox;
  cells: TableProposalCell[];
}

/** A table candidate that may span several blocks, typically PDF rows. */
/** A child grid sits inside one cell of the parent candidate. */
export interface TableNested {
  parent_key: string;
  /** Zero-based parent cell coordinates. */
  parent_row: number;
  parent_column: number;
}

export interface TableProposalCandidate {
  /** Stable within one response, derived from the source rectangle. */
  key: string;
  block_ids: string[];
  rows: number;
  columns: number;
  has_confidence: boolean;
  uncertain_cells: number;
  empty_cells: number;
  warnings: TableProposalWarning[];
  source: TableSourceBox;
  cells: TableProposalCell[];
  /** Set when this candidate is a nested grid inside a parent cell. */
  nested?: TableNested | null;
  /** Number of nested grids linked to this candidate. */
  nested_count?: number;
}

export interface PageTableProposals {
  page_id: string;
  run_id: string;
  engine: string;
  page_width: number | null;
  page_height: number | null;
  candidates: TableProposalCandidate[];
}

/* -------------------------------------------------------------------------- */
/*                                    AI                                      */
/* -------------------------------------------------------------------------- */

/** Provider id from the backend registry; the catalog is discovered at runtime. */
export type AiProviderId = string;

export type AiCostClass = "local" | "free" | "paid";
export type AiRotationStrategy =
  | "priority"
  | "failover"
  | "round_robin"
  | "least_recent"
  | "least_usage";

export type AiConnectionStatus =
  | "connected"
  | "untested"
  | "configuration_required"
  | "auth_failed"
  | "rate_limited"
  | "quota_exhausted"
  | "unavailable"
  | "error"
  | "disabled";

export type AiKeyStatus =
  | "ready"
  | "disabled"
  | "auth_failed"
  | "rate_limited"
  | "error";

export type AiTaskCapability = "text" | "vision";

/** Every task the unified router can route. */
export type AiTaskId =
  | "ocr_cleanup"
  | "region_proposals"
  | "equation_transcription"
  | "table_structure";

/** "default" is the fallback route used by tasks without their own route. */
export type AiRouteTask = AiTaskId | "default";

export type AiUsageTask = AiTaskId;
export type AiSuggestionStatus = "pending" | "accepted" | "rejected";
export type AiUsageOutcome = "success" | "error";
export type AiTask = "ocr_cleanup";

export interface AiProviderInfo {
  id: AiProviderId;
  name: string;
  kind: string;
  default_base_url: string;
  requires_base_url: boolean;
  supports_model_discovery: boolean;
  allows_manual_models: boolean;
  local_default: boolean;
  requires_api_key: boolean;
  docs_url: string | null;
}

export interface AiProvidersResponse {
  providers: AiProviderInfo[];
}

/** A credential stored in the encrypted local vault. The secret is never returned. */
export interface AiKey {
  id: string;
  label: string;
  enabled: boolean;
  priority: number;
  request_limit: number;
  auth_failed: boolean;
  status: AiKeyStatus;
  has_secret: boolean;
  last_used_at: string | null;
  last_success_at: string | null;
  last_error_at: string | null;
  last_error_code: string | null;
  cooldown_until: string | null;
  created_at: string | null;
}

export interface AiKeyCreate {
  label?: string;
  /** Write-only. Never echoed back in any response. */
  api_key: string;
  priority?: number;
  enabled?: boolean;
  request_limit?: number;
}

export interface AiKeyPatch {
  label?: string;
  priority?: number;
  enabled?: boolean;
  request_limit?: number;
  auth_failed?: boolean;
}

/** One model discovered from a provider with the user's own credential. */
export interface AiModel {
  id: string;
  connection_id: string;
  model_id: string;
  display_name: string | null;
  family: string | null;
  context_window: number | null;
  input_modalities: string[] | null;
  output_modalities: string[] | null;
  supports_tools: boolean | null;
  supports_streaming: boolean | null;
  pricing: Record<string, unknown> | null;
  metadata: Record<string, unknown> | null;
  source: "discovered" | "manual";
  available: boolean;
  favorite: boolean;
  last_used_at: string | null;
  discovered_at: string | null;
}

export interface AiManualModelCreate {
  model_id: string;
  display_name?: string;
  context_window?: number;
  input_modalities?: string[];
  output_modalities?: string[];
}

export interface AiModelFavoriteInput {
  model_id: string;
  favorite: boolean;
}

export interface AiConnection {
  id: string;
  provider: AiProviderId;
  provider_name: string;
  provider_kind: string;
  name: string;
  base_url: string;
  allow_remote: boolean;
  cost_class: AiCostClass;
  enabled: boolean;
  rotation_strategy: AiRotationStrategy;
  max_attempts: number;
  request_limit: number;
  monthly_budget_usd: number | null;
  settings: Record<string, unknown>;
  status: AiConnectionStatus;
  last_error_code: string | null;
  last_http_status: number | null;
  retry_after_seconds: number | null;
  last_checked_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  key_count: number;
  enabled_key_count: number;
  model_count: number;
  requires_api_key: boolean;
}

export interface AiConnectionDetail extends AiConnection {
  keys: AiKey[];
}

export interface AiConnectionsResponse {
  connections: AiConnection[];
}

export interface AiConnectionCreate {
  provider: AiProviderId;
  name?: string;
  base_url?: string;
  allow_remote?: boolean;
  cost_class?: AiCostClass;
  enabled?: boolean;
  rotation_strategy?: AiRotationStrategy;
  max_attempts?: number;
  request_limit?: number;
  monthly_budget_usd?: number | null;
}

export interface AiConnectionPatch {
  name?: string;
  base_url?: string;
  allow_remote?: boolean;
  cost_class?: AiCostClass;
  enabled?: boolean;
  rotation_strategy?: AiRotationStrategy;
  max_attempts?: number;
  request_limit?: number;
  monthly_budget_usd?: number | null;
}

export interface AiConnectionTestRequest {
  /** Write-only key supplied only for this test. */
  api_key?: string;
}

export interface AiConnectionTestResponse {
  connection_id: string;
  status: AiConnectionStatus;
  provider: AiProviderId;
  base_url: string;
  models_found: number;
  cached: boolean;
  version: string | null;
  error_code: string | null;
  http_status: number | null;
  retry_after_seconds: number | null;
  last_checked_at: string | null;
  message: string | null;
}

/** One routed task: its connection, model, fallback and warnings. */
export interface AiTaskRoute {
  task: AiRouteTask;
  connection_id: string | null;
  connection_name: string | null;
  connection_status: string | null;
  cost_class: AiCostClass | null;
  model_id: string | null;
  model_display_name: string | null;
  model_source: string | null;
  capability: AiTaskCapability;
  fallback_connection_id: string | null;
  fallback_connection_name: string | null;
  fallback_model_id: string | null;
  temperature: number;
  timeout_seconds: number;
  request_limit: number;
  configured: boolean;
  warnings: string[];
  updated_at: string | null;
}

export interface AiRoutesResponse {
  routes: AiTaskRoute[];
  default_model: string | null;
}

export interface AiRouteUpdate {
  connection_id?: string | null;
  model_id?: string | null;
  fallback_connection_id?: string | null;
  fallback_model_id?: string | null;
  temperature?: number;
  timeout_seconds?: number;
  request_limit?: number;
}

/** Minimal per-task state used to enable workspace actions and explain gaps. */
export interface AiTaskStatus {
  configured: boolean;
  connection_id: string | null;
  connection_name: string | null;
  base_url: string | null;
  model_id: string | null;
  model_display_name: string | null;
  cost_class: AiCostClass | null;
  warnings: string[];
}

export interface AiTasksResponse {
  tasks: Partial<Record<AiTaskId, AiTaskStatus>>;
}

export interface AiPreferences {
  /** Rolling 24-hour request cap. Zero means unlimited. */
  daily_request_limit: number;
  /** Verified monthly spend cap in USD. Null means no cap. */
  monthly_budget_usd: number | null;
}

export interface AiPreferencesPatch {
  daily_request_limit?: number;
  monthly_budget_usd?: number | null;
}

export interface AiOverview {
  connection_count: number;
  enabled_connection_count: number;
  key_count: number;
  model_count: number;
  configured_task_count: number;
  task_count: number;
  preferences: AiPreferences;
}

export interface AiMigrationStatus {
  needed: boolean;
  migrated: boolean;
  completed_at: string | null;
  detail: string | null;
}

export interface AiSuggestionCreate {
  /** Required before a connection marked as paid may generate a proposal. */
  confirm_paid?: boolean;
}

export interface AiSuggestion {
  id: string;
  page_id: string;
  /** Page number within the project, for cross-page review. */
  page_number: number | null;
  block_id: string;
  task: AiTask;
  original_text: string;
  proposed_text: string;
  provider: AiProviderId;
  model: string;
  base_url: string;
  status: AiSuggestionStatus;
  created_at: string;
  updated_at: string;
}

export interface AiSuggestionDecisionInput {
  status: "accepted" | "rejected";
}

export interface AiSuggestionDecisionResponse {
  suggestion: AiSuggestion;
  run: OcrRun;
}

/** Bulk decision input. Max 100 ids; each proposal is revalidated separately. */
export interface AiSuggestionBulkInput {
  ids: string[];
  status: "accepted" | "rejected";
}

/** One per-id result; a failed item keeps only its machine-readable reason. */
export interface AiSuggestionBulkItem {
  id: string;
  status: "accepted" | "rejected" | null;
  error_code: string | null;
}

export interface AiSuggestionBulkResponse {
  results: AiSuggestionBulkItem[];
  requested: number;
  succeeded: number;
  failed: number;
}

export interface AiSuggestionsResponse {
  suggestions: AiSuggestion[];
}

export interface AiUsageEntry {
  id: string;
  provider: string;
  model: string;
  task: string;
  outcome: AiUsageOutcome;
  error_code: string | null;
  project_id: string | null;
  page_id: string | null;
  block_id: string | null;
  connection_id: string | null;
  connection_name: string | null;
  key_id: string | null;
  key_label: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  estimated_cost_usd: number | null;
  cost_source: string | null;
  duration_ms: number | null;
  created_at: string;
}

export interface AiUsageTaskCount {
  /**
   * Task name as stored in the local ledger. Known tasks are listed in a stable
   * order; any other stored name follows alphabetically.
   */
  task: string;
  /** Attempts in the rolling window, including failed attempts. */
  used: number;
}

export interface AiUsageConnectionCount {
  connection_id: string;
  connection_name: string;
  provider: string;
  used: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  unpriced_requests: number;
}

export interface AiUsageResponse {
  window_hours: number;
  request_limit: number;
  used: number;
  remaining: number | null;
  successful: number;
  failed: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  unpriced_requests: number;
  monthly_cost_usd: number;
  /** Attempts per task in the rolling window. Empty before the first attempt. */
  by_task: AiUsageTaskCount[];
  by_connection: AiUsageConnectionCount[];
  recent: AiUsageEntry[];
}

export interface AiUsageHistoryEntry extends AiUsageEntry {
  /** Null when the project was deleted or the attempt had no project. */
  project_name: string | null;
}

export interface AiUsageHistoryResponse {
  entries: AiUsageHistoryEntry[];
  total: number;
  limit: number;
  offset: number;
}

/** Optional per-request paid approval for the routed region task. */
export interface AiRegionProposalsRequest {
  confirm_paid?: boolean;
}

/** Vision output is always a proposal: nothing is saved until the user accepts it. */
export interface AiRegionProposalsResponse {
  status: "ready";
  page_width: number;
  page_height: number;
  provider: AiProviderId;
  model: string;
  proposals: RegionProposal[];
}

/** Optional per-request paid approval for one equation transcription. */
export interface AiEquationRequest {
  confirm_paid?: boolean;
}

/**
 * LaTeX proposed for one equation crop. It is unverified model output: the user
 * must review the local preview before it becomes document content.
 */
export interface AiEquationResponse {
  element_id: string;
  page_id: string;
  latex: string;
  provider: AiProviderId;
  model: string;
  base_url: string;
}

/** Optional per-request paid approval for one AI table read. */
export interface AiTableRequest {
  confirm_paid?: boolean;
}

/**
 * A table grid read from one saved crop. It is unverified model output with no
 * confidence scores, shaped like a local table proposal so the same review grid
 * can show it and require acknowledgement before insertion.
 */
export interface AiTableResponse {
  element_id: string;
  page_id: string;
  provider: AiProviderId;
  model: string;
  base_url: string;
  page_width: number | null;
  page_height: number | null;
  rows: number;
  columns: number;
  uncertain_cells: number;
  empty_cells: number;
  warnings: TableProposalWarning[];
  source: TableSourceBox;
  cells: TableProposalCell[];
}

/** Languages for a locally read crop. Empty means the application default. */
export interface ElementTableRequest {
  languages?: string[];
}

/**
 * A table grid read by the local OCR engine from one saved crop. Confidence and
 * uncertainty come from the engine, so weak cells can be flagged without AI.
 */
export interface ElementTableResponse {
  element_id: string;
  page_id: string;
  engine: string;
  engine_version: string | null;
  languages: string[];
  page_width: number | null;
  page_height: number | null;
  rows: number;
  columns: number;
  has_confidence: boolean;
  uncertain_cells: number;
  empty_cells: number;
  warnings: TableProposalWarning[];
  source: TableSourceBox;
  cells: TableProposalCell[];
}

/* -------------------------------------------------------------------------- */
/*                                 Elements                                   */
/* -------------------------------------------------------------------------- */

export type ElementKind = "figure" | "table" | "equation";

export interface ElementSummary {
  id: string;
  page_id: string;
  kind: ElementKind;
  asset_id: string | null;
  /** Source-pixel rectangle on the page image at extraction time. */
  x: number;
  y: number;
  width: number;
  height: number;
  caption: string;
  source: "manual" | "ai" | string;
  verified: boolean;
  /** Locally extracted text. It is a proposal until the user verifies the element. */
  text: string;
  text_confidence: number | null;
  text_engine: string | null;
  text_engine_version: string | null;
  text_languages: string[];
  /** The user changed the text after extraction or typed it manually. */
  text_corrected: boolean;
  text_updated_at: string | null;
  /** The page was re-rendered after this crop was taken. */
  stale: boolean;
  created_at: string;
  updated_at: string;
}

/** Locally derived, reviewable region suggestion. Never persisted on its own. */
export type RegionProposalStatus =
  | "ready"
  | "no_ocr_run"
  | "ocr_not_ready"
  | "ocr_failed"
  | "ocr_stale"
  | "no_geometry";

export type RegionProposalReason =
  | "table_text_grid"
  | "equation_text"
  | "figure_caption_gap"
  | "pdf_image_region"
  | "pdf_drawing_region"
  | "page_artwork_region"
  | "ai_vision";

export interface RegionProposal {
  /** Stable within one response, derived from kind and rectangle. */
  key: string;
  kind: ElementKind;
  /** Source-pixel rectangle, already padded and clamped to the page. */
  x: number;
  y: number;
  width: number;
  height: number;
  /** Caption text taken from the OCR caption block, when available. */
  caption: string;
  reason: RegionProposalReason;
  confidence: "high" | "medium" | "low";
  block_ids: string[];
}

export interface RegionProposals {
  status: RegionProposalStatus;
  page_width: number | null;
  page_height: number | null;
  ocr_run_id: string | null;
  engine: string | null;
  proposals: RegionProposal[];
}

/** One page in a read-only cross-page proposal overview. */
export interface PageRegionProposals {
  page_id: string;
  page_number: number;
  status: RegionProposalStatus;
  page_width: number | null;
  page_height: number | null;
  ocr_run_id: string | null;
  engine: string | null;
  proposal_count: number;
  proposals: RegionProposal[];
}

/**
 * Derived, non-persisted aggregation of the per-page proposals. `truncated`
 * means the scan stopped at the page window; `next_page_number` is the first
 * page not included and can be passed back as `after_page_number`.
 */
export interface ProjectRegionProposals {
  pages: PageRegionProposals[];
  total_proposals: number;
  pages_with_proposals: number;
  truncated: boolean;
  next_page_number: number | null;
}

/**
 * One equation region read from the latest OCR layout. `text` is unverified OCR
 * output used as a LaTeX starting point, never document content on its own.
 */
export interface PageEquationProposal {
  key: string;
  x: number;
  y: number;
  width: number;
  height: number;
  text: string;
  display: boolean;
  confidence: "high" | "medium" | "low";
  reason: "equation_text";
  block_ids: string[];
  /** Zero-based top-to-bottom, left-to-right order within one response. */
  reading_index: number;
}

export interface PageEquationProposals {
  status: RegionProposalStatus;
  page_id: string;
  page_width: number | null;
  page_height: number | null;
  ocr_run_id: string | null;
  engine: string | null;
  proposals: PageEquationProposal[];
}

/* -------------------------------------------------------------------------- */
/*                               Document model                               */
/* -------------------------------------------------------------------------- */

export interface JSONMark {
  type: string;
  attrs?: Record<string, unknown> | null;
}

export interface JSONContent {
  type?: string;
  attrs?: Record<string, unknown> | null;
  content?: JSONContent[];
  marks?: JSONMark[];
  text?: string;
}

export interface DocumentRecord {
  format: "tiptap";
  schema_version: number;
  content: JSONContent;
  plain_text: string;
  updated_at: string | null;
}

/**
 * Per-project page header/footer for Word and PDF export. The text supports
 * `{page}`, `{pages}` and `{title}` placeholders; other braces stay literal.
 */
export interface DocumentLayout {
  header_text: string;
  footer_text: string;
  show_page_numbers: boolean;
  updated_at: string;
}

export type DocumentLayoutInput = Omit<DocumentLayout, "updated_at">;

export interface DocumentRevisionSummary {
  id: string;
  /** How the version was captured. */
  source: "autosave" | "manual";
  /** Whitespace-collapsed start of the stored text, for list display. */
  preview: string;
  character_count: number;
  created_at: string;
}

export interface DocumentRevision extends DocumentRevisionSummary {
  content: JSONContent;
  plain_text: string;
}

/**
 * One local activity entry. `payload` is metadata only (counts, formats, ids);
 * it never contains document text, OCR output or image data.
 */
export interface HistoryEvent {
  id: string;
  event_type: string;
  summary: string;
  payload: Record<string, unknown>;
  created_at: string;
}

/* -------------------------------------------------------------------------- */
/*                              App metadata                                  */
/* -------------------------------------------------------------------------- */

export interface AppCapabilities {
  import_images: boolean;
  import_pdf: boolean;
  image_transform: boolean;
  element_extraction: boolean;
  /** Reviewable region suggestions derived from local OCR layout. */
  region_proposals: boolean;
  ocr: boolean;
  ai: boolean;
  export: boolean;
  /** Local project backup download and restore. */
  backup: boolean;
}

export interface AppMeta {
  name: string;
  version: string;
  capabilities: AppCapabilities;
  /** Upload limit per page image, in megabytes. */
  max_import_mb: number;
  /** Maximum number of files in one import batch. */
  max_upload_batch: number;
  /** Maximum size of a project backup archive, in megabytes. */
  max_backup_mb: number;
  /** Configured source repository URL, if any. */
  repository_url: string | null;
}

export interface HealthStatus {
  status: "ok" | "degraded";
  version: string;
  database: "ok" | "error";
  data_dir: string;
  projects: number;
}

export interface ApiErrorBody {
  detail: {
    code: string;
    message: string;
  };
}
