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

export type SourceKind = "image" | "pdf";
export type PageStatus = "imported" | "processing" | "ready" | "failed";

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
  created_at: string;
  updated_at: string;
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
export type OcrBlockKind = "paragraph" | "heading" | "list_item";

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

/* -------------------------------------------------------------------------- */
/*                              App metadata                                  */
/* -------------------------------------------------------------------------- */

export interface AppCapabilities {
  import_images: boolean;
  import_pdf: boolean;
  image_transform: boolean;
  ocr: boolean;
  ai: boolean;
  export: boolean;
}

export interface AppMeta {
  name: string;
  version: string;
  capabilities: AppCapabilities;
  /** Upload limit per page image, in megabytes. */
  max_import_mb: number;
  /** Maximum number of files in one import batch. */
  max_upload_batch: number;
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
