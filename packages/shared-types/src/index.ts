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

export interface AppSettings {
  language: LanguageCode;
  appearance: AppearanceSettings;
  editor: EditorSettings;
  ai: AiSettings;
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

/** One verified backup archive kept in the local backup vault. */
export interface ProjectBackupSummary {
  filename: string;
  byte_size: number;
  created_at: string;
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
  reason: string | null;
  setup_hint: string | null;
}

/* -------------------------------------------------------------------------- */
/*                                    AI                                      */
/* -------------------------------------------------------------------------- */

export type AiProviderKind = "ollama" | "openai_compatible";

export type AiProbeStatus =
  | "ready"
  | "unreachable"
  | "timeout"
  | "http_error"
  | "invalid_response";

export type AiProbeErrorCode =
  | "ai_unreachable"
  | "ai_timeout"
  | "ai_http_error"
  | "ai_invalid_response";

export type AiTask = "ocr_cleanup";
export type AiSuggestionStatus = "pending" | "accepted" | "rejected";
export type AiUsageOutcome = "success" | "error";

export interface AiProvider {
  id: AiProviderKind;
  default_base_url: string;
}

export interface AiProvidersResponse {
  providers: AiProvider[];
}

export interface AiProbeRequest {
  provider: AiProviderKind;
  base_url?: string;
  allow_remote?: boolean;
}

export interface AiModel {
  id: string;
  family: string | null;
  parameter_size: string | null;
}

export interface AiProbeResponse {
  status: AiProbeStatus;
  provider: AiProviderKind;
  base_url: string;
  models: AiModel[];
  version: string | null;
  error_code: AiProbeErrorCode | null;
  http_status: number | null;
}

export interface AiSuggestionCreate {
  provider?: AiProviderKind;
  base_url?: string;
  model?: string;
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
  provider: AiProviderKind;
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
  created_at: string;
}

export interface AiUsageResponse {
  window_hours: number;
  request_limit: number;
  used: number;
  remaining: number | null;
  successful: number;
  failed: number;
  recent: AiUsageEntry[];
}

/** One local AI server profile. Empty model means AI actions stay disabled. */
export interface AiProfileSettings {
  provider: AiProviderKind;
  base_url: string;
  model: string;
  allow_remote: boolean;
}

export interface AiSettings {
  text: AiProfileSettings;
  /** Model used for page-image region proposals. Empty keeps image AI disabled. */
  vision_model: string;
  /** Rolling 24-hour request cap. Zero means unlimited. */
  request_limit: number;
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

/** Optional per-request overrides for the saved vision connection. */
export interface AiRegionProposalsRequest {
  provider?: AiProviderKind;
  base_url?: string;
  model?: string;
}

/** Vision output is always a proposal: nothing is saved until the user accepts it. */
export interface AiRegionProposalsResponse {
  status: "ready";
  page_width: number;
  page_height: number;
  provider: AiProviderKind;
  model: string;
  proposals: RegionProposal[];
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
